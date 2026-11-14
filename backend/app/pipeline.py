"""Pipeline stages (PRD section 3, step 4): transcribe (backend/stt/), read the page,
think and draw (backend/ai/), plus the spoken answer. Offline stubs run when keys are absent.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

import stt
from stt.speak import discard as discard_clip, speak
from ai import image
from ai import page_reader
from ai.reasoning import resolve_reason_model
from ai import think as _ai_think

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


def _transcribe_in_slot(clip: bytes) -> str:
    try:
        return stt.transcribe(clip)
    finally:
        _STT_SLOTS.release()

UNKNOWN_COMMAND = "Sorry, I didn't catch that. Say explain, draw, or who is this."


async def transcribe(audio: Media) -> str:
    clip = base64.b64decode(audio.b64)  # Invoke validation (#85) guarantees valid base64
    # Take a slot before queueing so a stuck engine cannot pile up decoded clips; the slot is
    # released only when the worker really finishes, not when the request times out.
    if not _STT_SLOTS.acquire(blocking=False):
        raise PipelineError("model_timeout", "That took too long. Try again.", True)
    try:
        future = _STT_THREADS.submit(_transcribe_in_slot, clip)
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
    command = stt.match_command(utterance)
    if command is None:
        raise PipelineError("stt_failed", UNKNOWN_COMMAND, True)
    return command


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


async def think(
    command: str,
    page_text: str,
    session_id: str,
    *,
    model: Optional[str] = None,
) -> dict:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        # offline/test path: byte-identical stub so CI and conformance exchanges are unaffected
        return {
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
            "speech_text": "Hamlet is alone, weighing whether to keep living.",
            "image_prompt": "A lone prince on a dark stage, bright outline on black",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
        }
    return await _ai_think(command, page_text, session_id, model=model)


async def draw(image_prompt: str, session_id: str) -> str | None:
    # Offline/test path: preserve deterministic contract fixtures without an API key.
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return None
    try:
        return await image.draw(image_prompt, session_id=session_id)
    except Exception as exc:
        log.warning("Image generation unavailable: %s", type(exc).__name__)
        return None


def _image_model() -> str:
    """Resolve the image model name the same way image.draw does, never blank."""
    try:
        from .config import get_settings

        name = get_settings().model_image
    except Exception:
        name = os.environ.get("MODEL_IMAGE", "")
    return name.strip() or image.DEFAULT_MODEL_IMAGE


async def run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Run the request under REQUEST_TIMEOUT_S; running out of time becomes model_timeout."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_S):
            return await _run(invoke, send_stage)
    except TimeoutError as exc:
        raise PipelineError("model_timeout", "That took too long. Try again.", True) from exc


async def _run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Run every stage in order, reporting each one before it starts.

    An unknown command fails before the page is read, so no model call is wasted on it.
    """
    if invoke.text is not None:
        command = command_from(invoke.text)
    else:
        await send_stage("transcribing")
        command = command_from(await timed(transcribe(invoke.audio)))

    await send_stage("reading")
    page_text = await timed(read_page(invoke.frame))

    _read_model = getattr(page_text, "model", None) or (
        page_reader._resolve_config()[2]
        if os.environ.get("NVIDIA_API_KEY", "").strip()
        else "stub"
    )

    _reason_model = (
        resolve_reason_model()
        if os.environ.get("GEMINI_API_KEY", "").strip()
        else "stub"
    )

    await send_stage("thinking")
    answer = await timed(think(
        command, page_text, invoke.session_id,
        model=_reason_model if _reason_model != "stub" else None,
    ))

    raw_sources = answer.get("sources") or []
    sources = [
        Source(title=s.get("title") or "Source", url=s["url"])
        for s in raw_sources
        if isinstance(s, dict) and str(s.get("url") or "").startswith("https://")
    ]

    await send_stage("drawing")
    # Speech runs alongside drawing so it adds no wait the phone's 30 s silence limit
    # would see. It is optional: None on any failure or timeout, and the phone speaks the text.
    async def _speak() -> str | None:
        try:
            return await asyncio.wait_for(speak(answer["speech_text"], invoke.session_id), STAGE_TIMEOUT_S)
        except Exception as exc:
            log.warning("Speech unavailable: %s", type(exc).__name__)
            return None

    # A slow image costs only the picture: the card still ships with text and speech (PRD section 9).
    async def _draw() -> str | None:
        try:
            return await timed(draw(answer["image_prompt"], invoke.session_id))
        except PipelineError as exc:
            if exc.code != "model_timeout":
                raise
            log.warning("Image generation timed out; sending the card without a picture")
            return None

    speaking = asyncio.create_task(_speak())
    try:
        image_url = await _draw()
    except BaseException:
        # The request fails, so its clip would never reach the phone: stop or delete it (#109).
        speaking.cancel()
        if speaking.done() and not speaking.cancelled():
            discard_clip(speaking.result())
        raise
    audio_url = await speaking

    return Card(
        request_id=invoke.request_id,
        title=answer["title"],
        caption=answer["caption"],
        image_url=image_url,
        speech_text=answer["speech_text"],
        audio_url=audio_url,
        book=Book(**answer["book"]),
        sources=sources,
        models={
            "read": _read_model,
            "reason": _reason_model,
            "image": _image_model() if image_url else "stub",
        },
    )
