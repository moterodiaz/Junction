"""Pipeline stages (PRD section 3, step 4). Stubs that later tasks replace:
read_page -> #28, think -> #30, draw -> #31. Speech to text lives in backend/stt/ (#27).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

import stt
from stt.speak import speak
from ai import image
from ai import page_reader
from ai.reasoning import resolve_reason_model
from ai import think as _ai_think

from .messages import Book, Card, ErrorCode, Invoke, Media, Source, Stage

SendStage = Callable[[Stage], Awaitable[None]]
T = TypeVar("T")
log = logging.getLogger("metalab.pipeline")


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
        log.exception("speech engine failed on a %d byte %s clip", len(clip), audio.mime)
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

    return await page_reader.read_page(frame)


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
        log.warning("Image generation unavailable: %s", exc)
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

    _read_model = (
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
            return await asyncio.wait_for(speak(answer["speech_text"]), STAGE_TIMEOUT_S)
        except Exception as exc:
            log.warning("Speech unavailable: %s", exc)
            return None

    image_url, audio_url = await asyncio.gather(
        timed(draw(answer["image_prompt"], invoke.session_id)), _speak()
    )

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
