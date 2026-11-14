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
import inspect
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Protocol, Tuple
import urllib.error
import urllib.request

from .session import BookInfo, BookSession, SessionStore, default_session_store
from .source_loader import PassageMatch, find_passage

log = logging.getLogger("metalab.reasoning")

DEFAULT_MODEL_REASON = "gemini-4-argon"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def ground_passage(
    page_text: str,
    min_score: float = 0.6,
    play: Optional[str] = "Hamlet",
    min_words: int = 5,
) -> Optional[PassageMatch]:
    """Locate recognized page text in structured play texts using find_passage.

    Returns PassageMatch if score >= min_score, else None.
    Millisecond local lookup.
    Requires at least min_words distinct words to avoid matching common phrases.
    """
    if not page_text or not page_text.strip():
        return None
    # ponytail: word-count guard prevents single common words like "He." from matching
    from .source_loader import normalize_text as _norm
    if len(_norm(page_text).split()) < min_words:
        return None
    try:
        return find_passage(query=page_text, play=play, min_score=min_score)
    except Exception as exc:
        log.warning("ground_passage lookup failed: %s", type(exc).__name__)
        return None

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

# ponytail: whole-word spoiler keywords; inflections added for die/kill/end only
_SPOILER_RE = re.compile(
    r"\b(?:die[sd]?|dying|death|kill(?:s|ed|ing)?|fate|end(?:s|ed|ing)?|"
    r"spoiler|what\s+happens\s+to|act\s+[45]|act\s+iv|act\s+v)\b",
    re.IGNORECASE,
)


def is_spoiler_guard_enabled(spoiler_guard: bool = False) -> bool:
    """Check if spoiler guard is enabled via parameter or environment variable."""
    if spoiler_guard:
        return True
    return os.environ.get("DECISION_ENABLE_SPOILER_CHECK", "").strip().lower() in ("1", "true", "yes", "on")


class ReasoningError(RuntimeError):
    """Raised when book reasoning fails."""


class GeminiReasoningClient(Protocol):
    async def generate_reasoning(
        self,
        command: str,
        page_text: str,
        session: BookSession,
        model: str = DEFAULT_MODEL_REASON,
        passage_match: Optional[PassageMatch] = None,
        spoiler_guard: bool = False,
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
        passage_match: Optional[PassageMatch] = None,
        spoiler_guard: bool = False,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ReasoningError("GEMINI_API_KEY is not set")

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"

        # Build contents incorporating session history
        contents: List[Dict[str, Any]] = session.get_gemini_turns()

        grounding_info = ""
        if passage_match:
            grounding_info = (
                f"\nCanonical Grounding (Act/Scene/Line coordinates verified from source text):\n"
                f"- Play: {passage_match.play_title}\n"
                f"- Location: {passage_match.location}\n"
                f"- Speaker: {passage_match.speaker or 'Unknown'}\n"
                f"- Matched Text: \"\"\"{passage_match.text}\"\"\"\n"
                f"You MUST use this exact title, location ('{passage_match.location}'), and source citation.\n"
            )
        else:
            grounding_info = (
                "\nNo verified local source passage matched this page text. "
                "Do NOT fabricate or invent Act, Scene, or Line coordinates. "
                "Do NOT fabricate source URLs or citations; return an empty 'sources' array if ungrounded.\n"
            )

        spoiler_instruction = ""
        use_spoiler_guard = is_spoiler_guard_enabled(spoiler_guard)
        if use_spoiler_guard:
            reading_horizon = (
                session.get_reading_horizon_summary()
                or "only the currently visible passage (exact book position unknown)"
            )
            spoiler_instruction = (
                f"\nAnti-Spoiler Guard ACTIVE:\n"
                f"- Reading Horizon: {reading_horizon}\n"
                f"- Instruction: Do NOT spoil plot events, fates, or reveals occurring AFTER the student's current reading horizon. "
                f"Keep explanations strictly within or before the student's current reading position.\n"
            )

        current_prompt = (
            f"Book: {session.book.title} ({session.book.author})\n"
            f"Current Position: {session.book.location}\n"
            f"{grounding_info}\n"
            f"{spoiler_instruction}"
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
                raise ReasoningError(f"Gemini API HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, TimeoutError):
                    raise TimeoutError("Gemini request timed out") from exc
                raise ReasoningError(
                    f"Gemini API network error: {type(exc.reason).__name__}"
                ) from exc
            except TimeoutError as exc:
                raise TimeoutError("Gemini request timed out") from exc
            except Exception as exc:
                raise ReasoningError(
                    f"Gemini request failed: {type(exc).__name__}"
                ) from exc

        raw_response = await asyncio.to_thread(_execute_http)
        return self._parse_gemini_response(raw_response, session, passage_match=passage_match)

    def _parse_gemini_response(
        self,
        raw_json: str,
        session: BookSession,
        passage_match: Optional[PassageMatch] = None,
    ) -> Dict[str, Any]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ReasoningError("Invalid JSON from Gemini API") from exc

        candidates = data.get("candidates", [])
        if not candidates:
            raise ReasoningError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ReasoningError("Gemini candidate has no parts")
        text = parts[0].get("text", "")
        return parse_reasoning_json(text, session, passage_match=passage_match)


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
        passage_match: Optional[PassageMatch] = None,
        spoiler_guard: bool = False,
    ) -> Dict[str, Any]:
        use_spoiler_guard = is_spoiler_guard_enabled(spoiler_guard)
        self.calls.append({
            "command": command,
            "page_text": page_text,
            "session_id": session.session_id,
            "history_count": len(session.history),
            "history_snapshot": [ex.to_dict() for ex in session.history],
            "model": model,
            "passage_match": passage_match.to_dict() if passage_match else None,
            "spoiler_guard": use_spoiler_guard,
        })

        if self.fail:
            raise ReasoningError("Simulated Gemini failure")

        if self.default_answer:
            return dict(self.default_answer)

        is_hamlet = session.book.title.strip().lower() == "hamlet" or (
            passage_match is not None and passage_match.play_title.strip().lower() == "hamlet"
        )

        if passage_match is not None:
            location = passage_match.location
            book_title = passage_match.play_title
            book_author = passage_match.author
            sources = [dict(passage_match.source)] if passage_match.source else []
        else:
            book_title = session.book.title
            book_author = session.book.author
            location = session.book.location or ("Act 3, Scene 1" if is_hamlet else "")
            sources = list(DEFAULT_HAMLET_SOURCES) if is_hamlet else []

        if is_hamlet and ("act" in command.lower() or "scene" in command.lower()):
            # Extract possible scene update from command if mentioned
            m = re.search(r"(Act\s+\d+,\s*Scene\s+\d+)", command, re.IGNORECASE)
            if m and passage_match is None:
                location = m.group(1).title()

        cmd_lower = command.lower()
        asks_future_spoiler = bool(_SPOILER_RE.search(cmd_lower))

        q_count = len(session.history) + 1
        if is_hamlet:
            if asks_future_spoiler:
                if use_spoiler_guard:
                    horizon = (
                        session.get_reading_horizon_summary()
                        or "only the currently visible passage (exact book position unknown)"
                    )
                    caption = f"Avoiding spoilers beyond {horizon}."
                    speech_text = (
                        f"Without spoiling events after {horizon}, Hamlet is focused on his current dilemma "
                        f"and suspicions at {location}."
                    )
                    image_prompt = (
                        f"A solitary prince in dark Elizabethan doublet, holding a Yorick skull in dim castle chamber, "
                        f"pure black background (#000000), glowing dramatic rim lighting, luminous high contrast."
                    )
                else:
                    caption = "In Act 5, Hamlet avenges his father and dies of poison."
                    speech_text = (
                        "In Act 5, Scene 2, Hamlet kills Claudius with the poisoned blade and cup, "
                        "avenging his father before dying from Laertes's poisoned rapier."
                    )
                    image_prompt = (
                        "Tragic final scene of Hamlet in the royal hall of Elsinore, "
                        "pure black background (#000000), glowing dramatic rim lighting, luminous high contrast."
                    )
            elif q_count > 1:
                caption = (
                    f"Question {q_count} builds on {q_count - 1} prior questions: "
                    f"Hamlet continues struggling with grief and duty."
                )
                speech_text = (
                    f"Building on our earlier discussion, Hamlet is alone again at {location}. "
                    f"He is weighing whether to endure his uncle's cruelty or take action."
                )
                image_prompt = (
                    f"A solitary prince in dark Elizabethan doublet, holding a Yorick skull in dim castle chamber, "
                    f"pure black background (#000000), glowing dramatic rim lighting, luminous high contrast."
                )
            else:
                caption = "Hamlet asks whether enduring pain is nobler than ending it."
                speech_text = "Hamlet is alone, weighing whether to keep living through suffering or end it."
                image_prompt = (
                    f"A solitary prince in dark Elizabethan doublet, holding a Yorick skull in dim castle chamber, "
                    f"pure black background (#000000), glowing dramatic rim lighting, luminous high contrast."
                )
        else:
            caption = f"Discussion of {book_title}."
            speech_text = f"Discussion of {book_title} at {location}." if location else f"Discussion of {book_title}."
            image_prompt = (
                f"Illustration for {book_title}, pure black background (#000000), "
                f"glowing dramatic rim lighting, luminous high contrast."
            )

        title = f"{book_title}, {location}" if location else book_title

        return {
            "title": title,
            "caption": caption,
            "speech_text": speech_text,
            "image_prompt": image_prompt,
            "book": {
                "title": book_title,
                "author": book_author,
                "location": location,
            },
            "sources": sources,
        }


def parse_reasoning_json(
    text: str,
    session: BookSession,
    passage_match: Optional[PassageMatch] = None,
) -> Dict[str, Any]:
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
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ReasoningError("Could not parse JSON from model output") from exc
        else:
            raise ReasoningError("Could not parse JSON from model output")

    if not isinstance(data, dict):
        raise ReasoningError("Model output JSON is not an object")

    raw_book = data.get("book") or {}
    if not isinstance(raw_book, dict):
        raise ReasoningError("Model output 'book' is not an object")

    if passage_match is not None:
        book_title = passage_match.play_title
        book_author = passage_match.author
        book_location = passage_match.location
    else:
        book_title = str(raw_book.get("title") or session.book.title).strip()
        book_author = str(raw_book.get("author") or session.book.author).strip()
        book_location = str(raw_book.get("location") or session.book.location).strip()

    book = {
        "title": book_title,
        "author": book_author,
        "location": book_location,
    }

    if passage_match is not None:
        title = f"{passage_match.play_title}, {passage_match.location}"
    else:
        title = str(data.get("title") or (f"{book_title}, {book_location}" if book_location else book_title)).strip()

    caption = str(data.get("caption") or "").strip()
    speech_text = str(data.get("speech_text") or "").strip()
    if not caption and not speech_text:
        raise ReasoningError("Model output is missing both caption and speech text")
    if not caption:
        caption = speech_text
    elif not speech_text:
        speech_text = caption
    image_prompt = str(data.get("image_prompt") or f"Illustration of {caption or speech_text}").strip()

    # Enforce optical lens conditioning on image_prompt if missing
    if "black background" not in image_prompt.lower():
        image_prompt = f"{image_prompt}, pure black background (#000000), high contrast luminous subject"

    raw_sources = data.get("sources")
    sources: List[Dict[str, str]] = []
    if isinstance(raw_sources, list) and raw_sources:
        for s in raw_sources:
            if isinstance(s, dict) and s.get("url"):
                sources.append({
                    "title": str(s.get("title", "Source")),
                    "url": str(s.get("url", "")),
                })

    if passage_match is not None:
        if passage_match.source and not any(s.get("url") == passage_match.source.get("url") for s in sources):
            sources.insert(0, dict(passage_match.source))
    else:
        # No verified passage: never emit unverified source citations
        sources = []

    return {
        "title": title,
        "caption": caption,
        "speech_text": speech_text,
        "image_prompt": image_prompt,
        "book": book,
        "sources": sources,
    }


def resolve_reason_model() -> str:
    """Reasoning model from MODEL_REASON, falling back to the default."""
    return os.environ.get("MODEL_REASON", "").strip() or DEFAULT_MODEL_REASON


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
    model: Optional[str] = None,
    passage_match: Optional[PassageMatch] = None,
    spoiler_guard: bool = False,
) -> Dict[str, Any]:
    """Execute book reasoning stage (PRD section 4, step 3).

    Takes command, passage, and session_id. Maintains in-memory session history,
    calls Gemini with passage + prior Q&A context, and returns answer card payload.
    """
    model = model or resolve_reason_model()
    store = session_store if session_store is not None else default_session_store
    session = store.get_or_create(session_id)

    # Local grounding via source_loader.find_passage if omitted and page_text present
    if passage_match is None and page_text and page_text.strip():
        book_title = session.book.title if session.book and session.book.title else "Hamlet"
        passage_match = ground_passage(page_text, min_score=0.6, play=book_title)

    # When passage_match is found, update session.book before reasoning
    if passage_match is not None:
        session.set_active_book(
            title=passage_match.play_title,
            author=passage_match.author,
            location=passage_match.location,
        )

    # Advance reading horizon with seen passage
    if passage_match is not None:
        session.record_seen_passage(
            passage_text=page_text or passage_match.text,
            act=passage_match.act,
            scene=passage_match.scene,
            line=passage_match.line_end,
        )
    elif page_text and page_text.strip():
        session.record_seen_passage(passage_text=page_text)

    active_client = client or get_reasoning_client()
    _sig = inspect.signature(active_client.generate_reasoning)
    _has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in _sig.parameters.values())
    gen_kwargs: Dict[str, Any] = {
        "command": command,
        "page_text": page_text,
        "session": session,
        "model": model,
    }
    if _has_varkw or "passage_match" in _sig.parameters:
        gen_kwargs["passage_match"] = passage_match
    if _has_varkw or "spoiler_guard" in _sig.parameters:
        gen_kwargs["spoiler_guard"] = spoiler_guard
    answer = await active_client.generate_reasoning(**gen_kwargs)

    # Ensure answer reflects passage_match coordinates and sources
    if passage_match is not None:
        if "book" not in answer or not isinstance(answer["book"], dict):
            answer["book"] = {}
        answer["book"]["title"] = passage_match.play_title
        answer["book"]["author"] = passage_match.author
        answer["book"]["location"] = passage_match.location
        if "sources" not in answer or not isinstance(answer["sources"], list):
            answer["sources"] = []
        has_custom_default = getattr(active_client, "default_answer", None) is not None
        if not has_custom_default:
            if passage_match.source and not any(
                isinstance(s, dict) and s.get("url") == passage_match.source.get("url")
                for s in answer["sources"]
            ):
                answer["sources"].insert(0, dict(passage_match.source))
    else:
        # No verified passage: never emit unverified source citations
        answer["sources"] = []

    # Update session metadata (only record location when grounded to avoid trusting model guesses)
    book = answer.get("book")
    if isinstance(book, dict):
        title = book.get("title")
        author = book.get("author") or ""
        raw_location = book.get("location") or ""
        trusted_location = raw_location.strip() if (passage_match is not None and isinstance(raw_location, str)) else ""
        if isinstance(title, str) and title.strip():
            session.set_active_book(
                title=title.strip(),
                author=author.strip() if isinstance(author, str) else "",
                location=trusted_location,
            )
        elif trusted_location:
            session.update_location(trusted_location)

    session.add_exchange(
        question=command,
        answer=answer.get("speech_text") or answer.get("caption", ""),
        passage=page_text,
    )

    return answer
