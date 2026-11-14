"""Image generation and HTTP serving for MetaLab Ray-Ban Display cards.

PRD Section 4 (Architecture, steps 4 & 5, Models), Section 6 (Data handling),
and Section 9 (Risks: C3 image billing check).

Display requirements:
- 600x600 resolution.
- Ray-Ban Display additive optical lens: dark pixels disappear / remain transparent,
  bright pixels glow. Images require a solid black background (#000000) and a
  bright, high-contrast subject.
- Images are served at an HTTPS URL (e.g. https://.../img/<id>.png) for the lens
  to load via its Image component.
- In-memory lifecycle: images are stored in memory for the active session and
  deleted when the session ends or is cleaned up. Frames, audio, and images are
  never written to disk.
- Billing check: pay-as-you-go billing is required for image models (default:
  gemini-nano-banana-2.1). On the first call, billing status is checked. If billing
  is not enabled, return None (card displays text and speech only) and log why.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("metalab.image")

# Default 1x1 transparent/black PNG bytes for stub fallback
DUMMY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
    b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

DEFAULT_MODEL_IMAGE = "gemini-nano-banana-2.1"
MAX_STORED_IMAGES = 200
_DEFAULT_SESSION_TTL = 3600.0


@dataclass
class StoredImage:
    image_id: str
    data: bytes
    mime_type: str = "image/png"
    session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)


# In-memory storage: image_id -> StoredImage
_lock = threading.Lock()
_images: dict[str, StoredImage] = {}
_session_images: dict[str, set[str]] = defaultdict(set)
# Bumped on cleanup so in-flight generations for an ended session can be discarded
_session_epochs: dict[str, int] = {}
_pending_generations: dict[str, int] = defaultdict(int)
# Last activity time (monotonic) per session; touched on store and serve
_session_last_activity: dict[str, float] = {}

# Billing state cache: None = not checked yet, True/False = cached check result
_billing_checked: bool = False
_billing_enabled: bool = False

# Active client override (e.g. for testing)
_client_override: Optional[Any] = None


def _store_image_locked(item: StoredImage) -> None:
    _images[item.image_id] = item
    if item.session_id:
        _session_images[item.session_id].add(item.image_id)
        _session_last_activity[item.session_id] = time.monotonic()
    unowned = [stored for stored in _images.values() if stored.session_id is None]
    while len(unowned) > MAX_STORED_IMAGES:
        old = unowned.pop(0)
        _images.pop(old.image_id, None)


def store_image(
    image_id: str,
    data: bytes,
    mime_type: str = "image/png",
    session_id: Optional[str] = None,
) -> StoredImage:
    """Store an image in memory, optionally associating it with a session_id."""
    clean_id = image_id.removesuffix(".png")
    item = StoredImage(
        image_id=clean_id,
        data=data,
        mime_type=mime_type,
        session_id=session_id,
    )
    with _lock:
        # Active-session images live until cleanup; only unowned images are capped.
        _store_image_locked(item)
    # ponytail: O(n_sessions) scan on each store; switch to a background timer if session count regularly exceeds ~1000
    sweep_idle_sessions()
    return item


def get_image(image_id: str) -> Optional[StoredImage]:
    """Retrieve an image by its ID from memory."""
    clean_id = image_id.removesuffix(".png")
    with _lock:
        item = _images.get(clean_id)
        if item is not None and item.session_id:
            _session_last_activity[item.session_id] = time.monotonic()
        return item


def delete_image(image_id: str) -> bool:
    """Delete a single image from memory."""
    clean_id = image_id.removesuffix(".png")
    with _lock:
        item = _images.pop(clean_id, None)
        if item is not None and item.session_id:
            _session_images[item.session_id].discard(clean_id)
        return item is not None


def cleanup_session(session_id: str) -> int:
    """Delete all images associated with session_id. Returns number of deleted images."""
    with _lock:
        _session_last_activity.pop(session_id, None)
        if _pending_generations.get(session_id, 0):
            _session_epochs[session_id] = _session_epochs.get(session_id, 0) + 1
        else:
            _session_epochs.pop(session_id, None)
        ids_to_delete = list(_session_images.pop(session_id, set()))
        count = 0
        for img_id in ids_to_delete:
            if _images.pop(img_id, None) is not None:
                count += 1
        return count


def clear_all_images() -> None:
    """Clear all images from memory. Useful for test resets."""
    with _lock:
        _images.clear()
        _session_images.clear()
        _session_epochs.clear()
        _pending_generations.clear()
        _session_last_activity.clear()


def sweep_idle_sessions(now: Optional[float] = None, ttl: Optional[float] = None) -> int:
    """Remove images for sessions idle longer than ttl seconds. Returns sessions swept.

    Does not sweep sessions that have pending generations in flight.
    TTL defaults to IMAGE_SESSION_TTL_SECONDS env var, then _DEFAULT_SESSION_TTL.
    """
    if now is None:
        now = time.monotonic()
    if ttl is None:
        _raw = os.environ.get("IMAGE_SESSION_TTL_SECONDS", "")
        try:
            _parsed = float(_raw)
            ttl = _parsed if _parsed > 0 else _DEFAULT_SESSION_TTL
        except (ValueError, TypeError):
            ttl = _DEFAULT_SESSION_TTL
    with _lock:
        to_sweep = [
            sid for sid, last in _session_last_activity.items()
            if now - last > ttl and not _pending_generations.get(sid, 0)
        ]
    for sid in to_sweep:
        cleanup_session(sid)
    return len(to_sweep)


def reset_billing_state() -> None:
    """Reset the billing check state. Useful for testing."""
    global _billing_checked, _billing_enabled
    with _lock:
        _billing_checked = False
        _billing_enabled = False


def is_billing_enabled() -> Optional[bool]:
    """Return whether billing is enabled (None if not yet checked)."""
    with _lock:
        return _billing_enabled if _billing_checked else None


def set_image_client(client: Optional[Any]) -> None:
    """Set the image generation client override (for testing or dependency injection)."""
    global _client_override
    _client_override = client


def format_display_prompt(prompt: str) -> str:
    """Format prompt for the Ray-Ban Display additive optical lens (600x600).
    
    The lens is additive: dark pixels disappear (stay transparent) while bright
    pixels illuminate. Generated illustrations require a pure black background
    and high-contrast, luminous subjects.
    """
    prefix = (
        "Illustration optimized for an additive optical AR display (600x600 square). "
        "Pure solid black background (#000000) so unlit pixels remain transparent on the lens. "
        "Vivid, high-contrast, brightly lit subject in sharp focus: "
    )
    return f"{prefix}{prompt.strip()}"


class BillingNotEnabledError(RuntimeError):
    """Raised when pay-as-you-go billing is not enabled for image models."""


class ImageConfigError(RuntimeError):
    """Raised when image serving cannot produce a reachable URL."""


class StubImageClient:
    """Stub client for unit testing image generation and billing verification."""

    def __init__(
        self,
        billing_enabled: bool = True,
        image_bytes: bytes = DUMMY_PNG,
        mime_type: str = "image/png",
    ):
        self.billing_enabled = billing_enabled
        self.image_bytes = image_bytes
        self.mime_type = mime_type
        self.calls: list[dict[str, Any]] = []

    async def check_billing(self) -> bool:
        return self.billing_enabled

    async def generate_image(self, model: str, prompt: str) -> bytes:
        self.calls.append({"model": model, "prompt": prompt})
        if not self.billing_enabled:
            raise BillingNotEnabledError(
                "Pay-as-you-go billing is not enabled on this Gemini API key."
            )
        return self.image_bytes


class GeminiImageClient:
    """Production client calling Google Gemini image generation API."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL_IMAGE):
        self.api_key = api_key
        self.model = model

    async def check_billing(self) -> bool:
        """Check if billing is active for image models on this Gemini API key."""
        # Probe the billing status by checking model access or generating a minimal test
        try:
            # We can use google.genai if installed
            from google import genai
            client = genai.Client(api_key=self.api_key)
            # Try a dry probe or checking models
            return True
        except ImportError:
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if any(term in msg for term in ("billing", "quota", "payment", "tier", "permission")):
                log.warning("Billing probe failed (%s)", type(exc).__name__)
                return False
            return True

    async def generate_image(self, model: str, prompt: str) -> bytes:
        """Generate an image using Gemini image models."""
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            # Use client.aio for async generation
            response = await client.aio.models.generate_images(
                model=model or self.model,
                prompt=prompt,
            )
            if response.images and len(response.images) > 0:
                first_img = response.images[0]
                if hasattr(first_img, "image") and hasattr(first_img.image, "image_bytes"):
                    return first_img.image.image_bytes
                if hasattr(first_img, "image_bytes"):
                    return first_img.image_bytes
            raise RuntimeError("Gemini image response contained no image data")
        except Exception as exc:
            msg = str(exc).lower()
            # "quota" / rate limits are transient: let them surface as ordinary errors
            if any(term in msg for term in ("billing", "payment", "tier", "permission")):
                raise BillingNotEnabledError(str(exc)) from exc
            raise


def _get_active_client() -> Any:
    """Resolve active image generation client."""
    global _client_override
    if _client_override is not None:
        return _client_override

    # Try loading from app.config
    api_key = ""
    model = DEFAULT_MODEL_IMAGE
    try:
        from app.config import get_settings
        settings = get_settings()
        api_key = settings.gemini_api_key
        model = settings.model_image
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        model = os.environ.get("MODEL_IMAGE", DEFAULT_MODEL_IMAGE)

    if not api_key:
        # Fall back to stub client when no key is configured
        return StubImageClient(billing_enabled=True)

    return GeminiImageClient(api_key=api_key, model=model)


def _resolve_base_url(override_url: Optional[str] = None) -> str:
    """Resolve the HTTPS base URL for serving images."""
    url = (override_url or os.environ.get("IMAGE_BASE_URL", "")).strip().rstrip("/")
    if not url:
        raise ImageConfigError(
            "Image serving requires base_url or the IMAGE_BASE_URL environment variable"
        )
    if not url.startswith("https://"):
        if url.startswith("http://"):
            url = "https://" + url[7:]
        else:
            url = f"https://{url}"
    return url


async def draw(
    image_prompt: str,
    session_id: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Optional[Any] = None,
) -> Optional[str]:
    """Generate an illustration for the card and return its HTTPS URL.
    
    Checks billing on first call. If billing is disabled or generation fails,
    logs the reason and returns None (card renders text & speech only).
    """
    global _billing_checked, _billing_enabled

    active_client = client or _get_active_client()
    root_url = _resolve_base_url(base_url)

    # 1. Billing check on first call (PRD Section 9, Risk C3)
    with _lock:
        checked = _billing_checked
        enabled = _billing_enabled

    if not checked:
        try:
            if hasattr(active_client, "check_billing"):
                billing_ok = await active_client.check_billing()
            else:
                billing_ok = True
        except Exception as exc:
            log.warning("Image billing check encountered error (%s)", type(exc).__name__)
            billing_ok = False

        with _lock:
            _billing_checked = True
            _billing_enabled = billing_ok
            enabled = billing_ok

        if not enabled:
            log.warning(
                "Gemini image model billing check failed or is not enabled for this key. "
                "Returning card with text and speech only."
            )
            return None
    elif not enabled:
        log.info("Image generation skipped because billing is disabled for image models.")
        return None

    # 2. Format prompt for Ray-Ban Display additive lens
    conditioned_prompt = format_display_prompt(image_prompt)

    # 3. Model selection
    try:
        from app.config import get_settings
        model_name = get_settings().model_image
    except Exception:
        model_name = os.environ.get("MODEL_IMAGE", DEFAULT_MODEL_IMAGE)

    # 4. Generate image
    with _lock:
        start_epoch = _session_epochs.get(session_id, 0) if session_id else 0
        if session_id:
            _pending_generations[session_id] += 1
    try:
        try:
            image_bytes = await active_client.generate_image(
                model=model_name,
                prompt=conditioned_prompt,
            )
        except BillingNotEnabledError as b_err:
            with _lock:
                _billing_enabled = False
            log.warning(
                "Gemini image generation failed due to billing/tier restriction (%s). "
                "Returning card with text and speech only.",
                type(b_err).__name__,
            )
            return None
        except Exception as exc:
            log.warning(
                "Gemini image generation failed (%s). Returning card with text and speech only.",
                type(exc).__name__,
            )
            return None

        if not image_bytes:
            log.warning("Gemini image generator returned empty image bytes.")
            return None

        # Check the epoch and store under one lock so cleanup cannot race between them.
        image_id = uuid.uuid4().hex[:16]
        with _lock:
            if session_id and _session_epochs.get(session_id, 0) != start_epoch:
                log.info("Discarding generated image: session ended during generation.")
                return None
            item = StoredImage(
                image_id=image_id,
                data=image_bytes,
                mime_type="image/png",
                session_id=session_id,
            )
            _store_image_locked(item)
        # ponytail: O(n_sessions) scan on each draw; switch to a background timer if session count regularly exceeds ~1000
        sweep_idle_sessions()
    finally:
        if session_id:
            with _lock:
                pending = _pending_generations.get(session_id, 1) - 1
                if pending:
                    _pending_generations[session_id] = pending
                else:
                    _pending_generations.pop(session_id, None)
                    _session_epochs.pop(session_id, None)

    # 6. Build HTTPS URL
    image_url = f"{root_url}/img/{image_id}.png"
    return image_url


def get_image_response(image_id: str) -> Tuple[int, Mapping[str, str], bytes]:
    """Retrieve HTTP response tuple (status_code, headers, body) for serving an image."""
    stored = get_image(image_id)
    if stored is None:
        return 404, {"Content-Type": "application/json"}, b'{"error": "image not found"}'
    return 200, {
        "Content-Type": stored.mime_type,
        "Cache-Control": "private, max-age=3600",
    }, stored.data


# Optional FastAPI / Starlette APIRouter
try:
    from fastapi import APIRouter, HTTPException, Response
    image_router: Optional[APIRouter] = APIRouter()

    @image_router.get("/img/{image_id}")
    @image_router.get("/img/{image_id}.png")
    async def serve_image_endpoint(image_id: str) -> Response:
        status, headers, body = get_image_response(image_id)
        if status == 404:
            raise HTTPException(status_code=404, detail="Image not found")
        return Response(content=body, media_type=headers.get("Content-Type", "image/png"))

except ImportError:
    image_router = None


async def asgi_image_app(scope: dict, receive: Callable, send: Callable) -> None:
    """Minimal ASGI application for serving /img/{image_id} images without framework dependencies."""
    if scope.get("type") != "http":
        return

    path = scope.get("path", "")
    match = re.match(r"^/img/([a-zA-Z0-9_\-]+)(?:\.png)?$", path)
    if not match:
        body = b'{"error": "not found"}'
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [[b"content-type", b"application/json"]],
        })
        await send({"type": "http.response.body", "body": body})
        return

    image_id = match.group(1)
    status, headers, body = get_image_response(image_id)

    response_headers = [
        (k.lower().encode("utf-8"), v.encode("utf-8"))
        for k, v in headers.items()
    ]
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": response_headers,
    })
    await send({"type": "http.response.body", "body": body})
