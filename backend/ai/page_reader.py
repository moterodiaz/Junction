"""Nemotron 3.5 Super VL page reading client and stage implementation.

PRD reference: section 4 Architecture, Models; section 9 Risks (C1).
Issue #28: backend: page reading with Nemotron 3.5 Super VL.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Mapping

log = logging.getLogger("metalab.ai.page_reader")

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL_READ = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_PROMPT = (
    "Transcribe all readable text from this page image verbatim. "
    "Do not add any preamble, commentary, or markdown formatting. "
    "If the image is blank, blurry, unreadable, or contains no readable text, "
    "respond with NO_TEXT_FOUND."
)

NO_TEXT_SIGNALS = {
    "NO_TEXT_FOUND",
    "NO TEXT FOUND",
    "NO_TEXT",
    "NO TEXT",
    "NO READABLE TEXT",
    "NO READABLE TEXT FOUND",
    "NO TEXT DETECTED",
    "THERE IS NO TEXT",
    "THERE IS NO READABLE TEXT",
    "BLANK PAGE",
    "EMPTY PAGE",
}


class PageReadError(Exception):
    """Base exception for page reading failures."""

    def __init__(self, message: str, code: str = "internal", retryable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class NoTextFoundError(PageReadError):
    """Raised when no readable text is found in the frame (frame discarded)."""

    def __init__(self, message: str = "No readable text was found on the page.") -> None:
        super().__init__(message, code="no_text_found", retryable=True)


class PageReadTimeoutError(PageReadError):
    """Raised when page reading exceeds timeout."""

    def __init__(self, message: str = "Page reading timed out.") -> None:
        super().__init__(message, code="model_timeout", retryable=True)


def extract_frame_data(frame: Any) -> tuple[str, str]:
    """Extract mime type and base64 string from frame input.

    Accepts:
    - dict with keys 'b64' (or 'data') and optional 'mime'
    - object with attributes 'b64' and optional 'mime' (e.g. Media model)
    - base64 string or data URL ('data:image/jpeg;base64,...')
    - raw image bytes
    """
    if frame is None:
        raise NoTextFoundError("Frame is empty or missing.")

    mime = "image/jpeg"
    b64 = ""

    if isinstance(frame, dict):
        mime = frame.get("mime", mime)
        b64 = frame.get("b64") or frame.get("data") or ""
    elif hasattr(frame, "b64"):
        b64 = getattr(frame, "b64", "")
        mime = getattr(frame, "mime", mime)
    elif isinstance(frame, bytes):
        mime = "image/jpeg"
        b64 = base64.b64encode(frame).decode("ascii")
    elif isinstance(frame, str):
        cleaned = frame.strip()
        if cleaned.startswith("data:"):
            parts = cleaned.split(",", 1)
            if len(parts) == 2:
                header, b64 = parts
                if ";base64" in header:
                    mime = header[5:].split(";")[0] or mime
            else:
                b64 = cleaned
        else:
            b64 = cleaned
    else:
        raise NoTextFoundError(f"Unsupported frame type: {type(frame)}")

    b64 = b64.strip() if isinstance(b64, str) else ""
    if not b64:
        raise NoTextFoundError("Frame is empty or contains no image data.")

    return mime, b64


def _is_no_text_response(text: str) -> bool:
    """Check if model response indicates absence of readable text."""
    stripped = text.strip()
    if not stripped:
        return True

    clean = stripped.strip("'\"`*._").strip()
    upper = clean.upper()
    if upper in NO_TEXT_SIGNALS or upper.startswith("NO_TEXT_FOUND"):
        return True

    lower = clean.lower()
    if lower in {"no text", "no readable text", "no text on page", "empty page", "blank page"}:
        return True

    return False


def _resolve_config() -> tuple[str, str, str]:
    """Resolve API key, base URL, and model name from env or config module."""
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    base_url = os.environ.get("NVIDIA_BASE_URL", "").strip()
    model = os.environ.get("MODEL_READ", "").strip()

    if not (nvidia_key and base_url and model):
        try:
            from app.config import load_settings
            settings = load_settings()
            nvidia_key = nvidia_key or settings.nvidia_api_key
            base_url = base_url or settings.nvidia_base_url
            model = model or settings.model_read
        except Exception:
            pass

    base_url = base_url or DEFAULT_NVIDIA_BASE_URL
    model = model or DEFAULT_MODEL_READ
    return nvidia_key, base_url, model


class NemotronClient:
    """Client for Nemotron 3.5 Super VL via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        default_key, default_base_url, default_model = _resolve_config()
        self.api_key = api_key or default_key
        self.base_url = (base_url or default_base_url).rstrip("/")
        self.model = model or default_model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "NVIDIA_API_KEY is required to call Nemotron 3.5 Super VL. "
                "In tests, pass client=StubNemotronClient(...)."
            )

    async def complete(
        self,
        frame_b64: str,
        mime: str = "image/jpeg",
        prompt: str | None = None,
    ) -> str:
        """Call Nemotron 3.5 Super VL with the frame and return transcribed page text."""
        prompt_text = prompt or DEFAULT_PROMPT
        data_url = f"data:{mime};base64,{frame_b64}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                    ],
                }
            ],
            "chat_template_kwargs": {
                "enable_thinking": False,
            },
        }

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = await self._send_request(endpoint, headers, payload)
        return self._parse_response(data)

    async def _send_request(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send HTTP request asynchronously using httpx if available, else urllib in thread."""
        try:
            import httpx
            has_httpx = True
        except ImportError:
            has_httpx = False

        if has_httpx:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.is_error:
                        raise PageReadError(
                            f"Nemotron API returned HTTP {resp.status_code}: {resp.text}",
                            code="internal",
                        )
                    return resp.json()
            except httpx.TimeoutException as exc:
                raise PageReadTimeoutError(f"Nemotron API request timed out: {exc}") from exc
            except (httpx.RequestError, ConnectionError) as exc:
                raise PageReadError(f"Nemotron API network error: {exc}", code="internal") from exc

        def _sync_call() -> dict[str, Any]:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise PageReadError(
                    f"Nemotron API returned HTTP {exc.code}: {body}",
                    code="internal",
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                raise PageReadTimeoutError(f"Nemotron API request failed: {exc}") from exc

        return await asyncio.to_thread(_sync_call)

    def _parse_response(self, data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if not choices:
            raise NoTextFoundError("Nemotron returned no choices in response.")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content) if content is not None else ""

        if _is_no_text_response(content):
            raise NoTextFoundError()

        return content.strip()


class StubNemotronClient:
    """Stub client for offline testing and accuracy benchmarking."""

    def __init__(
        self,
        responses: Mapping[str, str | Exception] | None = None,
        default_response: str | Exception = "To be, or not to be, that is the question.",
    ) -> None:
        self.responses = dict(responses or {})
        self.default_response = default_response
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        frame_b64: str,
        mime: str = "image/jpeg",
        prompt: str | None = None,
    ) -> str:
        self.calls.append({
            "frame_b64": frame_b64,
            "mime": mime,
            "prompt": prompt,
        })

        resp = self.responses.get(frame_b64)
        if resp is None:
            for key, val in self.responses.items():
                if frame_b64.startswith(key) or key.startswith(frame_b64[:30]):
                    resp = val
                    break

        if resp is None:
            resp = self.default_response

        if isinstance(resp, Exception):
            raise resp

        if _is_no_text_response(resp):
            raise NoTextFoundError()

        return resp.strip()


async def read_page(
    frame: Any,
    *,
    client: Any | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Read and transcribe text from a page frame using Nemotron 3.5 Super VL.

    Parameters:
    - frame: Media model, dict with 'b64' / 'mime', raw base64 string, or bytes.
    - client: Optional pre-configured client (e.g. StubNemotronClient or NemotronClient).
    - api_key, base_url, model, prompt, timeout: Optional overrides if client is not provided.

    Returns:
    - Transcribed page text.

    Raises:
    - NoTextFoundError: If frame contains no readable text (discarding the frame).
    - PageReadTimeoutError: If the model request times out.
    - PageReadError: If model API fails.
    """
    mime, b64 = extract_frame_data(frame)

    if client is None:
        client = NemotronClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    return await client.complete(b64, mime=mime, prompt=prompt)
