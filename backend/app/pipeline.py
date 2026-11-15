"""Pipeline stages (PRD section 3, step 4): transcribe (backend/stt/), read the page,
think and draw (backend/ai/), plus the spoken answer. Offline stubs run when keys are absent.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import inspect
import logging
import os
import re
import threading
import time
import traceback
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

import stt
from stt import debug_log as stt_debug_log, engine as stt_engine
from stt.speak import discard as discard_clip, speak
import ai.decision
import ai.reasoning
from ai import image
from ai import page_reader
from ai.reasoning import default_session_store, ground_passage, resolve_reason_model, PassageMatch
from ai import think as _ai_think

from . import latency
from .messages import Book, Card, ErrorCode, Invoke, Media, Source, Stage

SendStage = Callable[[Stage], Awaitable[None]]
T = TypeVar("T")
log = logging.getLogger("metalab.pipeline")


def log_failure(what: str, exc: BaseException, *args: object) -> None:
    """Log a failure's type and stack, never its message: upstream errors can quote page
    text or model output, and logs must not hold user text (PRD section 6)."""
    frames = "".join(traceback.format_tb(exc.__traceback__))
    log.error(what + ": %s\n%s", *args, type(exc).__name__, frames)


class PipelineError(Exception):
    """A failure the phone should see as a contract error with this code."""

    def __init__(self, code: ErrorCode, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


# Both limits sit inside the phone's deadlines (ios/.../Deadline.swift: 30 s without a server
# message, 90 s overall), so the phone always receives model_timeout instead of hanging up.
STAGE_TIMEOUT_S = float(os.environ.get("STAGE_TIMEOUT_S", "25"))
REQUEST_TIMEOUT_S = float(os.environ.get("REQUEST_TIMEOUT_S", "85"))

# A timed-out transcription cannot be stopped, so cap how many can run (and hold audio) at once.
_STT_WORKERS = 2
_STT_THREADS = ThreadPoolExecutor(max_workers=_STT_WORKERS, thread_name_prefix="stt")
_STT_SLOTS = threading.BoundedSemaphore(_STT_WORKERS)
STT_SLOT_POLL_S = 0.05  # how often a waiting request checks for a free slot


def _transcribe_in_slot(clip: bytes, mime: str | None = None, session_id: str | None = None) -> str:
    try:
        if not stt_debug_log.enabled():
            return stt.transcribe(clip)
        return _transcribe_and_record(clip, mime, session_id)
    finally:
        _STT_SLOTS.release()


def _transcribe_and_record(clip: bytes, mime: str | None, session_id: str | None) -> str:
    """Transcribe and append one STT debug log line (REQ-OBS-02), written in the worker before
    the slot is released so a timed-out request still leaves its record."""
    started = time.monotonic()
    text, error = "", None
    try:
        text, _ = stt_engine.transcribe_detailed(clip)
        return text
    except BaseException as exc:
        error = exc
        raise
    finally:
        info = stt_engine.last_run_info()
        stt_debug_log.record(
            ts=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
            session_id=session_id,
            engine=info["engine"],
            model=info["model"],
            latency_ms=round((time.monotonic() - started) * 1000),
            fallback_used=info["fallback_used"],
            fallback_reason=info["fallback_reason"],
            clip_bytes=len(clip),
            mime=mime,
            transcript=text,
            ok=error is None,
            error_type=type(error).__name__ if error is not None else None,
        )

UNKNOWN_COMMAND = "Sorry, I didn't catch that. Say explain, draw, or who is this."
# Whisper over a Bluetooth headset mic often hears the question but not the command word, and
# failing those requests felt random to students (#260), so anything heard counts as explain.
DEFAULT_COMMAND: stt.Command = "explain"


async def transcribe(audio: Media, session_id: str | None = None) -> str:
    # Take a slot before decoding or queueing so a stuck engine or a burst of waiters cannot pile
    # up decoded clips; the slot is released only when the worker really finishes, not when the
    # request times out. With both slots busy, wait for one: timed() bounds the wait, and polling
    # (rather than blocking a thread on the semaphore) means a cancelled waiter never takes a
    # slot (#110).
    while not _STT_SLOTS.acquire(blocking=False):
        await asyncio.sleep(STT_SLOT_POLL_S)
    try:
        clip = base64.b64decode(audio.b64)  # Invoke validation (#85) guarantees valid base64
        future = _STT_THREADS.submit(_transcribe_in_slot, clip, audio.mime, session_id)
    except BaseException:
        _STT_SLOTS.release()
        raise
    # A job cancelled before a worker picked it up never runs, so free its slot here.
    future.add_done_callback(lambda f: _STT_SLOTS.release() if f.cancelled() else None)
    try:
        return await asyncio.wrap_future(future)
    except TimeoutError:
        raise  # timed() turns it into model_timeout
    except Exception as exc:
        log_failure("speech engine failed on a %d byte %s clip", exc, len(clip), audio.mime)
        raise PipelineError("stt_failed", "Speech recognition failed. Try again.", True) from exc


def command_from(utterance: str) -> stt.Command:
    """The L0 command heard; explain when no command word was heard. Only an empty transcript
    fails (stt_failed), because then nothing was heard at all."""
    if not utterance or not utterance.strip():
        raise PipelineError("stt_failed", UNKNOWN_COMMAND, True)
    return stt.match_command(utterance) or DEFAULT_COMMAND


async def timed(stage: Awaitable[T]) -> T:
    """Await one stage under STAGE_TIMEOUT_S. Running out of time, or a stage reporting
    a timeout (built-in or httpx, which the model SDKs use), becomes model_timeout."""
    try:
        return await asyncio.wait_for(stage, STAGE_TIMEOUT_S)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise PipelineError("model_timeout", "That took too long. Try again.", True) from exc


async def read_page(frame: Media) -> str:
    # Offline/test path: preserve deterministic contract fixtures without an API key.
    if not os.environ.get("NVIDIA_API_KEY", "").strip():
        return "To be, or not to be, that is the question."

    try:
        return await page_reader.read_page_with_fallback(frame)
    except page_reader.NoTextFoundError as exc:
        raise PipelineError("no_text_found", "No readable text was found on the page.", True) from exc


def _accepts_param(fn: Any, param_name: str) -> bool:
    try:
        sig = inspect.signature(fn)
        return param_name in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        return False


NO_SOURCE_TEXT = "No source text"


def _mark_ungrounded(answer: dict) -> dict:
    """A card without a verified source passage says so (PRD §2) instead of carrying the
    model's act/scene/line guess. The reasoning stage empties `sources` exactly when no
    passage was verified."""
    if answer.get("sources"):
        return answer
    book = dict(answer.get("book")) if isinstance(answer.get("book"), dict) else {}
    book["location"] = NO_SOURCE_TEXT
    title = _text(book.get("title")) or "Your page"
    return {**answer, "title": title, "book": book, "sources": []}


async def think(
    command: str,
    page_text: str,
    session_id: str,
    *,
    model: Optional[str] = None,
    passage_match: Optional[PassageMatch] = None,
    spoiler_guard: bool = False,
) -> dict:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        # offline/test path: byte-identical stub so CI and conformance exchanges are unaffected
        try:
            session = default_session_store.get_or_create(session_id)
            match = passage_match
            if match is None and page_text and page_text.strip():
                book_title = session.book.title if session.book and session.book.title else "Hamlet"
                match = ground_passage(page_text, min_score=0.6, play=book_title)
            if match is not None:
                session.record_seen_passage(
                    passage_text=page_text or match.text,
                    act=match.act,
                    scene=match.scene,
                    line=match.line_end,
                )
            elif page_text and page_text.strip():
                session.record_seen_passage(passage_text=page_text)
        except Exception:
            pass
        return {
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
            "speech_text": "Hamlet is alone, weighing whether to keep living.",
            "image_prompt": "A lone prince on a dark stage, bright outline on black",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
        }
    ai_kwargs: dict[str, Any] = {}
    if _accepts_param(_ai_think, "model"):
        ai_kwargs["model"] = model
    if _accepts_param(_ai_think, "passage_match"):
        ai_kwargs["passage_match"] = passage_match
    if _accepts_param(_ai_think, "spoiler_guard"):
        ai_kwargs["spoiler_guard"] = spoiler_guard
    answer = await _ai_think(command, page_text, session_id, **ai_kwargs)
    return _mark_ungrounded(answer)


def _draw_accepts_style_preset(fn: Any) -> bool:
    return _accepts_param(fn, "style_preset")


async def draw(
    image_prompt: str,
    session_id: str,
    style_preset: Optional[str] = None,
    image_id: Optional[str] = None,
) -> str | None:
    # Offline/test path: preserve deterministic contract fixtures without an API key.
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        if image_id:
            image.release(image_id)
        return None
    kwargs: dict[str, Any] = {"session_id": session_id}
    if style_preset is not None:
        kwargs["style_preset"] = style_preset
    if image_id is not None:
        kwargs["image_id"] = image_id
    try:
        return await image.draw(image_prompt, **kwargs)
    except Exception as exc:
        log.warning("Image generation unavailable: %s", type(exc).__name__)
        if image_id:
            image.release(image_id)
        return None


# Pictures still drawing for cards already sent. They outlive run(), and asyncio keeps only
# weak references to tasks, so hold them here until done; end_session cancels them.
_PENDING_DRAWS: dict[str, set[asyncio.Task]] = {}
_MAX_PENDING_DRAWS = 2  # per session; beyond this a card waits for its picture as before


def _reserve_image(session_id: str) -> tuple[str, str] | None:
    """Reserve an image id and its URL so the card can ship before the picture (REQ-IMG-01).
    None when no picture can be made here (no key, no public URL, or a draw that cannot take
    the id): the card must not carry a link that can only 404."""
    if not os.environ.get("GEMINI_API_KEY", "").strip() or not _accepts_param(draw, "image_id"):
        return None
    try:
        base_url = image._resolve_base_url()
    except Exception:
        return None
    image_id = image.reserve(session_id)
    return image_id, f"{base_url}/img/{image_id}.png"


def _hold_draw(session_id: str, task: asyncio.Task, image_id: str) -> None:
    tasks = _PENDING_DRAWS.setdefault(session_id, set())
    tasks.add(task)

    def _done(finished: asyncio.Task) -> None:
        tasks.discard(finished)
        if not tasks and _PENDING_DRAWS.get(session_id) is tasks:
            _PENDING_DRAWS.pop(session_id, None)
        if finished.cancelled():
            image.release(image_id)
            return
        exc = finished.exception()
        if exc is not None:
            log.warning("Image generation failed after the card: %s", type(exc).__name__)
        if exc is not None or finished.result() is None:
            # The phone already has the URL: release it so its fetch gets a fast 404.
            image.release(image_id)

    task.add_done_callback(_done)


def _image_model() -> str:
    """Resolve the image model name the same way image.draw does, never blank."""
    try:
        from .config import get_settings

        name = get_settings().model_image
    except Exception:
        name = os.environ.get("MODEL_IMAGE", "")
    return name.strip() or image.DEFAULT_MODEL_IMAGE


def _is_dynamic_routing_active() -> bool:
    val = os.environ.get("DYNAMIC_MODEL_ROUTING")
    if val is not None and val.strip().lower() in ("0", "false", "no", "off"):
        return False

    try:
        client = ai.decision.get_decision_client()
        if not isinstance(client, ai.decision.GeminiDecisionClient):
            return True
    except Exception:
        pass

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return False

    if val is not None and val.strip().lower() in ("1", "true", "yes", "on"):
        return True

    try:
        from .config import get_settings

        cfg_val = get_settings().dynamic_model_routing
        if str(cfg_val).strip().lower() in ("1", "true", "yes", "on"):
            return True
    except Exception:
        pass

    return False


_SESSION_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

# A book session that no one has touched for this long is ended (#139, REQ-PRIV-03).
SESSION_IDLE_TTL_S = float(os.environ.get("SESSION_IDLE_TTL_S", "3600"))


_SESSION_SEEN: dict[str, float] = {}  # session id -> last time a request touched it (monotonic)


def _touch(session_id: str) -> None:
    _SESSION_SEEN[session_id] = time.monotonic()


def end_session(session_id: str) -> None:
    """End a session: forget its book, history and reading horizon, and delete its spoken clips
    and generated images. Called on expiry; the one place that knows every per-session store."""
    import ai.image as image_module
    import stt.speak as speak_module

    for task in list(_PENDING_DRAWS.pop(session_id, ())):
        task.cancel()
    default_session_store.delete(session_id)
    speak_module.cleanup_session(session_id)
    image_module.cleanup_session(session_id)
    pass
    _SESSION_SEEN.pop(session_id, None)


def sweep_expired(now: float | None = None) -> list[str]:
    """Expire every session idle past SESSION_IDLE_TTL_S. A session with a request in flight is
    never expired, so a slow answer cannot be wiped mid-request. Returns the ended session ids."""
    now = time.monotonic() if now is None else now
    expired = []
    for session_id, seen in list(_SESSION_SEEN.items()):
        lock = _SESSION_LOCKS.get(session_id)
        if now - seen > SESSION_IDLE_TTL_S and not (lock is not None and lock.locked()):
            expired.append(session_id)
    for session_id in expired:
        end_session(session_id)
    return expired


# The anti-spoiler reading horizon (#197): a failed request must not advance it either.
# is_default_book rides along: a failed request must not leave a default-Hamlet session "selected".
_HORIZON_FIELDS = ("max_position", "seen_passages", "_horizon_by_book", "is_default_book")


def _session_state(session) -> tuple:
    """What a request may change in its book session: the history, which book is active, the
    candidate list, each book's fields (set_active_book and update_location edit them in place),
    the pending book question and, where the session tracks it, the reading horizon."""
    books = {id(b): b for b in (session.book, *session.candidate_books)}
    horizon = {name: copy.copy(getattr(session, name)) for name in _HORIZON_FIELDS if hasattr(session, name)}
    return (list(session.history), session.book, list(session.candidate_books),
            [(b, b.title, b.author, b.location) for b in books.values()],
            getattr(session, "awaiting_book_clarification", False), horizon)


def _restore_session_state(session, state: tuple) -> None:
    history, book, candidates, fields, clarifying, horizon = state
    session.history[:] = history
    for b, title, author, location in fields:
        b.title, b.author, b.location = title, author, location
    session.book = book
    session.candidate_books[:] = candidates
    session.awaiting_book_clarification = clarifying
    for name, value in horizon.items():
        setattr(session, name, value)


async def run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Run the request under REQUEST_TIMEOUT_S; running out of time becomes model_timeout."""
    sweep_expired()
    _touch(invoke.session_id)
    session = default_session_store.get_or_create(invoke.session_id)
    lock = _SESSION_LOCKS.get(invoke.session_id)
    if lock is None:
        lock = _SESSION_LOCKS[invoke.session_id] = asyncio.Lock()
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_S):
            # One request per session at a time, so a failure only ever undoes its own changes.
            async with lock:
                # Snapshot while holding the lock, so a request that never ran cannot undo one that did.
                before = _session_state(session)
                try:
                    return await _run(invoke, send_stage)
                except BaseException:
                    # No card reaches the phone (error, timeout or hang-up): forget everything this
                    # request recorded (think saves before drawing), so follow-ups never build on
                    # an answer the student did not see.
                    _restore_session_state(session, before)
                    raise
                finally:
                    # Refresh last-seen after the request so time spent answering is not counted as
                    # idle time (a 65 s answer with SESSION_IDLE_TTL_S=60 must not look expired).
                    _touch(invoke.session_id)
    except TimeoutError as exc:
        raise PipelineError("model_timeout", "That took too long. Try again.", True) from exc


_HTTPS_URL = re.compile(r"^https://[^\s/?#]+[^\s]*$")  # the contract's httpsUrl pattern

_CLARIFY_BOOK_PREFIXES = (
    "i am reading ",
    "i'm reading ",
    "we are reading ",
    "we're reading ",
    "the book is ",
    "the play is ",
    "this book is ",
    "this play is ",
    "book is ",
    "play is ",
    "this is ",
    "it is ",
    "it's ",
)
_NON_BOOK_REPLIES = {"", "unknown", "unknown book", "i don't know", "not sure", "no idea", "skip"}


def _apply_book_clarification_reply(session: ai.session.BookSession, utterance: str, has_passage_match: bool) -> bool:
    """Resolve a pending book-clarification turn by selecting or adding the named book."""
    if not getattr(session, "awaiting_book_clarification", False):
        return False
    session.awaiting_book_clarification = False
    if has_passage_match:
        return True

    cleaned = utterance.strip()
    for prefix in _CLARIFY_BOOK_PREFIXES:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    cleaned = cleaned.strip(" \t\r\n\"'.,!?:;")
    if cleaned.lower() in _NON_BOOK_REPLIES or len(cleaned) > 120:
        return False

    cleaned_lower = cleaned.lower()
    for candidate in getattr(session, "candidate_books", ()):
        title = getattr(candidate, "title", "").strip()
        if title and title.lower() not in ("unknown", "unknown book") and title.lower() == cleaned_lower:
            session.set_active_book(title, candidate.author, candidate.location)
            return True

    session.set_active_book(cleaned)
    return True


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _https(value: object) -> str | None:
    return value if isinstance(value, str) and _HTTPS_URL.fullmatch(value) else None  # $ alone allows a final "\n"


def _safe_record(stage: str, model_id: str, fallback: bool = False) -> None:
    try:
        latency.record_model_choice(stage, model_id, fallback=fallback)
    except Exception:
        log.debug("record_model_choice skipped: stage=%s model=%r", stage, model_id)


def contract_card(request_id: str, answer: dict, image_url: str | None, audio_url: str | None,
                  models: dict[str, str]) -> Card:
    """Build a card whose text and sources meet the contract (#112): blank text gets a plain
    default and sources without a valid https URL are dropped. Model ids are passed through."""
    speech = _text(answer.get("speech_text")) or _text(answer.get("caption")) or "Here is what this passage is about."
    book = answer.get("book") if isinstance(answer.get("book"), dict) else {}
    sources = [
        Source(title=_text(s.get("title")) or "Source", url=s["url"])
        for s in answer.get("sources") or []
        if isinstance(s, dict) and _https(s.get("url"))
    ]
    return Card(
        request_id=request_id,
        title=_text(answer.get("title")) or _text(book.get("title")) or "Your page",
        caption=_text(answer.get("caption")) or speech,
        image_url=image_url,
        speech_text=speech,
        audio_url=audio_url,
        book=Book(title=_text(book.get("title")) or "Unknown book",
                  author=_text(book.get("author")) or "Unknown author",
                  location=_text(book.get("location")) or "Unknown location"),
        sources=sources,
        models=models,
    )


async def _run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Run every stage in order, reporting each one before it starts.

    An unknown command fails before the page is read, so no model call is wasted on it.
    When dynamic routing is active, the student utterance is preserved and evaluated
    via Gemini Decisions API before thinking.
    """
    dynamic_routing = _is_dynamic_routing_active()

    if invoke.text is not None:
        utterance = invoke.text
    else:
        await send_stage("transcribing")
        utterance = await timed(transcribe(invoke.audio, session_id=invoke.session_id))
        latency.note_stt_words(len(utterance.split()))

    if not dynamic_routing:
        command = command_from(utterance)

    await send_stage("reading")
    page_text = await timed(read_page(invoke.frame))

    passage_match = ground_passage(page_text)
    passage_score = float(passage_match.score) if passage_match is not None else 0.0
    session = default_session_store.get_or_create(invoke.session_id)
    if passage_match is not None:
        session.set_active_book(
            passage_match.play_title,
            passage_match.author,
            passage_match.location,
        )
    clarification_resolved = _apply_book_clarification_reply(session, utterance, passage_match is not None)

    _read_model = getattr(page_text, "model", None) or (
        page_reader._resolve_config()[2]
        if os.environ.get("NVIDIA_API_KEY", "").strip()
        else "stub"
    )

    decision = None
    clarify = False
    if dynamic_routing:
        decision = await timed(ai.decision.decide(utterance, page_text, session, passage_score=passage_score))
        if decision.fallback_used:
            # Only an empty utterance fails. Otherwise fallback_decide's natural-intent keywords
            # (backend/ai/decision.py) pick the action; the L0 default applies outside this mode.
            command_from(utterance)

        if (
            not decision.fallback_used
            and decision.book_changed
            and decision.book_match
            and decision.book_match != "unknown"
            and decision.book_match_confidence >= 0.70
        ):
            session.set_active_book(decision.book_match)

        if (
            not clarification_resolved
            and not decision.fallback_used
            and decision.action == "clarify"
            and ai.decision.should_clarify_book(decision, passage_score)
        ):
            clarify = True

        client = ai.decision.get_decision_client()
        if os.environ.get("GEMINI_API_KEY", "").strip() or not isinstance(client, ai.decision.GeminiDecisionClient):
            _reason_model = decision.recommended_model
        else:
            _reason_model = "stub"
        think_prompt = utterance
    else:
        _reason_model = (
            resolve_reason_model()
            if os.environ.get("GEMINI_API_KEY", "").strip()
            else "stub"
        )
        think_prompt = command

    await send_stage("thinking")
    if clarify:
        clarification_text = "Which book are you reading right now? Please name the play or book."
        answer = {
            "title": "Which book are you reading?",
            "caption": clarification_text,
            "speech_text": clarification_text,
            "image_prompt": "",
            "book": {
                "title": session.book.title or "Unknown book",
                "author": session.book.author or "Unknown author",
                "location": session.book.location or "Unknown location",
            },
            "sources": [],
        }
    else:
        spoiler_guard = bool(
            (decision is not None and getattr(decision, "spoiler_risk", False))
            or ai.decision.is_spoiler_check_enabled()
        )
        think_kwargs: dict[str, Any] = {}
        reason_model_val = _reason_model if _reason_model != "stub" else None
        if _accepts_param(think, "model"):
            think_kwargs["model"] = reason_model_val
        if _accepts_param(think, "passage_match") and passage_match is not None:
            think_kwargs["passage_match"] = passage_match
        if _accepts_param(think, "spoiler_guard"):
            think_kwargs["spoiler_guard"] = spoiler_guard
        answer = await timed(think(
            think_prompt,
            page_text,
            invoke.session_id,
            **think_kwargs,
        ))

    await send_stage("drawing")
    # Speech runs alongside drawing so it adds no wait the phone's 30 s silence limit
    # would see. It is optional: None on any failure or timeout, and the phone speaks the text.
    async def _speak() -> str | None:
        try:
            speech_text = answer.get("speech_text") or answer.get("caption") or ""
            return await asyncio.wait_for(speak(speech_text, invoke.session_id), STAGE_TIMEOUT_S)
        except Exception as exc:
            log.warning("Speech unavailable: %s", type(exc).__name__)
            return None

    # A slow image costs only the picture: the card still ships with text and speech (PRD section 9).
    async def _draw(style_preset: Optional[str] = None, image_id: Optional[str] = None) -> str | None:
        kwargs: dict[str, Any] = {}
        if style_preset is not None and _draw_accepts_style_preset(draw):
            kwargs["style_preset"] = style_preset
        if image_id is not None:
            kwargs["image_id"] = image_id
        try:
            return await timed(draw(answer["image_prompt"], invoke.session_id, **kwargs))
        except PipelineError as exc:
            if exc.code != "model_timeout":
                raise
            log.warning("Image generation timed out; sending the card without a picture")
            return None

    speaking = asyncio.create_task(_speak())
    drawing: asyncio.Task | None = None
    try:
        skip_draw = clarify or (decision is not None and (decision.speak_only or not decision.needs_image))
        image_url = None
        if not skip_draw:
            style_preset = getattr(decision, "style_preset", None) if decision is not None else None
            # At the cap, draw inline under the session lock so repeated requests cannot pile
            # up paid background draws.
            at_cap = len(_PENDING_DRAWS.get(invoke.session_id, ())) >= _MAX_PENDING_DRAWS
            reserved = None if at_cap else _reserve_image(invoke.session_id)
            if reserved is None:
                image_url = await _draw(style_preset)
            else:
                # The card waits only for speech; the lens loads the picture from the reserved
                # URL, which the image route holds open until the draw lands (REQ-LAT-02).
                image_id, reserved_url = reserved
                drawing = asyncio.create_task(_draw(style_preset, image_id))
                _hold_draw(invoke.session_id, drawing, image_id)
        audio_url = await speaking
        if drawing is not None:
            if not drawing.done():
                image_url = reserved_url
            elif not drawing.cancelled() and drawing.exception() is None:
                image_url = drawing.result()
        if clarify:
            session.awaiting_book_clarification = True
        models = {"read": _read_model, "reason": _reason_model,
                  "image": _image_model() if image_url else "stub"}
        card = contract_card(invoke.request_id, answer, image_url, audio_url, models)

        if dynamic_routing and decision is not None:
            client = ai.decision.get_decision_client()
            if decision.fallback_used:
                decision_model = "fallback"
            elif isinstance(client, ai.decision.StubDecisionClient):
                decision_model = "stub"
            else:
                decision_model = os.environ.get("MODEL_DECISION", "").strip() or ai.decision.DEFAULT_MODEL_DECISION
            _safe_record("decision", decision_model, fallback=bool(decision.fallback_used))

        _primary_read = page_reader._resolve_config()[2]
        _safe_record("read", _read_model or "stub",
                     fallback=bool(_read_model == "stub" or _read_model != _primary_read))
        if not clarify:
            _safe_record("reason", _reason_model or "stub", fallback=bool(_reason_model == "stub"))
        _safe_record("image", models["image"],
                     fallback=bool(models["image"] == "stub") and not clarify)

        if audio_url:
            _speech_client = stt.speak.client_for(audio_url)
            tts_model = getattr(_speech_client, "model", None)
            if tts_model:
                _configured = getattr(_speech_client, "_configured_model", tts_model)
                _safe_record("tts", tts_model, fallback=bool(tts_model != _configured))
            else:
                try:
                    from .config import get_settings
                    tts_model_name = get_settings().model_tts
                except Exception:
                    tts_model_name = os.environ.get("MODEL_TTS", "")
                tts_model = (tts_model_name or "").strip() or getattr(stt.speak, "DEFAULT_MODEL_TTS", "gemini-3.8-flash-tts")
                _safe_record("tts", tts_model, fallback=False)
        else:
            _safe_record("tts", "stub", fallback=True)

        return card
    except BaseException:
        # No card, so the clip would never reach the phone: stop it, or delete it if it is
        # already stored (#109). Covers a draw failure, the request timeout or a hang-up while
        # waiting for speech, and a card that fails to build. A picture for that card is stopped
        # too, which releases its reserved id.
        if drawing is not None:
            drawing.cancel()
        speaking.cancel()
        if speaking.done() and not speaking.cancelled() and speaking.exception() is None:
            clip = speaking.result()
            if clip:
                discard_clip(clip)
        raise
