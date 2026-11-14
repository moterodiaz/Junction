"""Pipeline stages (PRD section 3, step 4). Stubs that later tasks replace:
read_page -> #28, think -> #30, draw -> #31. Speech to text lives in backend/stt/ (#27).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
from typing import Awaitable, Callable, Optional

import stt
from ai import image
from ai import page_reader
from ai.reasoning import resolve_reason_model
from ai import think as _ai_think

from .messages import Book, Card, ErrorCode, Invoke, Media, Source, Stage

SendStage = Callable[[Stage], Awaitable[None]]
log = logging.getLogger("metalab.pipeline")


class PipelineError(Exception):
    """A failure the phone should see as a contract error with this code."""

    def __init__(self, code: ErrorCode, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


UNKNOWN_COMMAND = "Sorry, I didn't catch that. Say explain, draw, or who is this."


async def transcribe(audio: Media) -> str:
    try:
        clip = base64.b64decode(audio.b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PipelineError("stt_failed", "The audio clip could not be decoded.", True) from exc
    try:
        return await asyncio.to_thread(stt.transcribe, clip)
    except Exception as exc:
        log.exception("speech engine failed on a %d byte %s clip", len(clip), audio.mime)
        raise PipelineError("stt_failed", "Speech recognition failed. Try again.", True) from exc


def command_from(utterance: str) -> stt.Command:
    command = stt.match_command(utterance)
    if command is None:
        raise PipelineError("stt_failed", UNKNOWN_COMMAND, True)
    return command


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
    """Run every stage in order, reporting each one before it starts.

    An unknown command fails before the page is read, so no model call is wasted on it.
    """
    if invoke.text is not None:
        command = command_from(invoke.text)
    else:
        await send_stage("transcribing")
        command = command_from(await transcribe(invoke.audio))

    await send_stage("reading")
    page_text = await read_page(invoke.frame)

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
    answer = await think(
        command, page_text, invoke.session_id,
        model=_reason_model if _reason_model != "stub" else None,
    )

    raw_sources = answer.get("sources") or []
    sources = [
        Source(title=s.get("title") or "Source", url=s["url"])
        for s in raw_sources
        if isinstance(s, dict) and str(s.get("url") or "").startswith("https://")
    ]

    await send_stage("drawing")
    image_url = await draw(answer["image_prompt"], invoke.session_id)

    return Card(
        request_id=invoke.request_id,
        title=answer["title"],
        caption=answer["caption"],
        image_url=image_url,
        speech_text=answer["speech_text"],
        book=Book(**answer["book"]),
        sources=sources,
        models={
            "read": _read_model,
            "reason": _reason_model,
            "image": _image_model() if image_url else "stub",
        },
    )
