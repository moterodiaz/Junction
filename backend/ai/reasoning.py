"""Book session and reasoning with Gemini (PRD section 2, section 4 step 3).

Keeps a per-book session in memory and calls Gemini (default: gemini-4-argon)
with the visible page passage plus session history to produce:
- title: play/book title and act/scene/line location
- caption: concise two-line explanation suitable for Ray-Ban Display lens
- speech_text: natural spoken explanation to read aloud
- image_prompt: visual illustration prompt conditioned for additive lens
  (black background #000000, high contrast, bright luminous subjects)
- book: {title, author, location}
- sources: list of source citations

The tenth question must be able to use the first nine.
Tests use a stub client without needing runtime API keys or network.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Protocol, Tuple
import urllib.error
import urllib.request

from .session import BookInfo, BookSession, SessionStore, default_session_store

log = logging.getLogger("metalab.reasoning")

DEFAULT_MODEL_REASON = "gemini-4-argon"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM_INSTRUCTION = (
    "You are MetaLab's literature reading companion for high school students reading assigned texts like Shakespeare. "
    "You receive the book title and current location, earlier questions and answers from this reading session, "
    "the text of the page the student is looking at, and the student's question or command. "
    "You must return ONLY a JSON object with the following fields: "
    "'title' (string: Book title, Act, Scene, or Line), "
    "'caption' (string: concise two-line explanation suitable for Ray-Ban Display glasses), "
    "'speech_text' (string: natural conversational spoken explanation to be read aloud), "
    "'image_prompt' (string: vivid illustration prompt with a pure black background (#000000) and bright, "
    "high-contrast subject suited for Ray-Ban Display additive optical lens), "
    "'book' (object with 'title', 'author', 'location'), "
    "'sources' (array of objects with 'title' and 'url')."
)

DEFAULT_HAMLET_SOURCES = [
    {
        "title": "Hamlet, public-domain text",
        "url": "https://www.gutenberg.org/ebooks/1524",
    }
]


class ReasoningError(RuntimeError):
    """Raised when book reasoning fails."""


class GeminiReasoningClient(Protocol):
    async def generate_reasoning(
        self,
        command: str,
        page_text: str,
        session: BookSession,
        model: str = DEFAULT_MODEL_REASON,
    ) -> Dict[str, Any]:
        """Generate structured reasoning given command, passage, and session context."""
        ...


class HttpGeminiClient:
    """Real client calling Gemini generateContent REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = GEMINI_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate_reasoning(
        self,
        command: str,
        page_text: str,
        session: BookSession,
        model: str = DEFAULT_MODEL_REASON,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ReasoningError("GEMINI_API_KEY is not set")

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"

        # Build contents incorporating session history
        contents: List[Dict[str, Any]] = session.get_gemini_turns()

        current_prompt = (
            f"Book: {session.book.title} ({session.book.author})\n"
            f"Current Position: {session.book.location}\n\n"
            f"Page Passage:\n\"\"\"{page_text}\"\"\"\n\n"
            f"Student Question / Command:\n{command}"
        )
        contents.append({"role": "user", "parts": [{"text": current_prompt}]})

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.4,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        def _execute_http() -> str:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise ReasoningError(f"Gemini API HTTP {exc.code}: {body}") from exc
            except urllib.error.URLError as exc:
                raise ReasoningError(f"Gemini API network error: {exc}") from exc
            except Exception as exc:
                raise ReasoningError(f"Gemini request failed: {exc}") from exc

        raw_response = await asyncio.to_thread(_execute_http)
        return self._parse_gemini_response(raw_response, session)

    def _parse_gemini_response(self, raw_json: str, session: BookSession) -> Dict[str, Any]:
        try:
            data = json.loads(raw_json)
            candidates = data.get("candidates", [])
            if not candidates:
                raise ReasoningError("Gemini returned no candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ReasoningError("Gemini candidate has no parts")
            text = parts[0].get("text", "")
            return parse_reasoning_json(text, session)
        except json.JSONDecodeError as exc:
            raise ReasoningError(f"Invalid JSON from Gemini API: {exc}") from exc


class StubGeminiClient:
    """Stub client for tests that simulates Gemini responses and session memory."""

    def __init__(
        self,
        default_answer: Optional[Dict[str, Any]] = None,
        fail: bool = False,
    ) -> None:
        self.default_answer = default_answer
        self.fail = fail
        self.calls: List[Dict[str, Any]] = []

    async def generate_reasoning(
        self,
        command: str,
        page_text: str,
        session: BookSession,
        model: str = DEFAULT_MODEL_REASON,
    ) -> Dict[str, Any]:
        self.calls.append({
            "command": command,
            "page_text": page_text,
            "session_id": session.session_id,
            "history_count": len(session.history),
            "history_snapshot": [ex.to_dict() for ex in session.history],
            "model": model,
        })

        if self.fail:
            raise ReasoningError("Simulated Gemini failure")

        if self.default_answer:
            return dict(self.default_answer)

        # Contextual response: if earlier history exists, reference it
        q_count = len(session.history) + 1
        location = session.book.location or "Act 3, Scene 1"
        if "act" in command.lower() or "scene" in command.lower():
            # Extract possible scene update from command if mentioned
            m = re.search(r"(Act\s+\d+,\s*Scene\s+\d+)", command, re.IGNORECASE)
            if m:
                location = m.group(1).title()

        if q_count > 1:
            caption = (
                f"Question {q_count} builds on {q_count - 1} prior questions: "
                f"Hamlet continues struggling with grief and duty."
            )
            speech_text = (
                f"Building on our earlier discussion, Hamlet is alone again at {location}. "
                f"He is weighing whether to endure his uncle's cruelty or take action."
            )
        else:
            caption = "Hamlet asks whether enduring pain is nobler than ending it."
            speech_text = "Hamlet is alone, weighing whether to keep living through suffering or end it."

        image_prompt = (
            f"A solitary prince in dark Elizabethan doublet, holding a Yorick skull in dim castle chamber, "
            f"pure black background (#000000), glowing dramatic rim lighting, luminous high contrast."
        )

        return {
            "title": f"{session.book.title}, {location}",
            "caption": caption,
            "speech_text": speech_text,
            "image_prompt": image_prompt,
            "book": {
                "title": session.book.title,
                "author": session.book.author,
                "location": location,
            },
            "sources": list(DEFAULT_HAMLET_SOURCES),
        }


def parse_reasoning_json(text: str, session: BookSession) -> Dict[str, Any]:
    """Parse and clean JSON output from Gemini, handling markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback regex extraction if surrounded by extra text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ReasoningError(f"Could not parse JSON from model output: {text[:200]}")

    if not isinstance(data, dict):
        raise ReasoningError("Model output JSON is not an object")

    title = str(data.get("title") or f"{session.book.title}, {session.book.location}").strip()
    caption = str(data.get("caption") or "").strip()
    if not caption:
        raise ReasoningError("Model output is missing a caption")
    speech_text = str(data.get("speech_text") or caption).strip()
    image_prompt = str(data.get("image_prompt") or f"Illustration of {caption}").strip()

    # Enforce optical lens conditioning on image_prompt if missing
    if "black background" not in image_prompt.lower():
        image_prompt = f"{image_prompt}, pure black background (#000000), high contrast luminous subject"

    raw_book = data.get("book") or {}
    if not isinstance(raw_book, dict):
        raise ReasoningError("Model output 'book' is not an object")
    book = {
        "title": str(raw_book.get("title") or session.book.title).strip(),
        "author": str(raw_book.get("author") or session.book.author).strip(),
        "location": str(raw_book.get("location") or session.book.location).strip(),
    }

    raw_sources = data.get("sources")
    if isinstance(raw_sources, list) and raw_sources:
        sources = [
            {"title": str(s.get("title", "Source")), "url": str(s.get("url", ""))}
            for s in raw_sources if isinstance(s, dict) and s.get("url")
        ]
    else:
        sources = list(DEFAULT_HAMLET_SOURCES)

    return {
        "title": title,
        "caption": caption,
        "speech_text": speech_text,
        "image_prompt": image_prompt,
        "book": book,
        "sources": sources,
    }


_global_client: Optional[GeminiReasoningClient] = None


def set_reasoning_client(client: Optional[GeminiReasoningClient]) -> None:
    """Set global Gemini client override (used for testing)."""
    global _global_client
    _global_client = client


def get_reasoning_client() -> GeminiReasoningClient:
    """Get active Gemini client (injected, environment-based HttpGeminiClient, or StubGeminiClient)."""
    if _global_client is not None:
        return _global_client
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        return HttpGeminiClient(api_key=api_key)
    # Without an API key, use StubGeminiClient so tests and local runs work out of the box
    return StubGeminiClient()


async def think(
    command: str,
    page_text: str,
    session_id: str,
    client: Optional[GeminiReasoningClient] = None,
    session_store: Optional[SessionStore] = None,
    model: str = DEFAULT_MODEL_REASON,
) -> Dict[str, Any]:
    """Execute book reasoning stage (PRD section 4, step 3).

    Takes command, passage, and session_id. Maintains in-memory session history,
    calls Gemini with passage + prior Q&A context, and returns answer card payload.
    """
    store = session_store if session_store is not None else default_session_store
    session = store.get_or_create(session_id)

    active_client = client or get_reasoning_client()
    answer = await active_client.generate_reasoning(
        command=command,
        page_text=page_text,
        session=session,
        model=model,
    )

    # Update session location and record Q&A exchange
    if answer.get("book") and answer["book"].get("location"):
        session.update_location(answer["book"]["location"])

    session.add_exchange(
        question=command,
        answer=answer.get("caption", ""),
        passage=page_text,
    )

    return answer
