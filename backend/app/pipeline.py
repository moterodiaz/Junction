"""Pipeline stages (PRD section 3, step 4). Stubs that later tasks replace:
read_page -> #28, think -> #30, draw -> #31. Speech to text lives in backend/stt/ (#27).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from typing import Awaitable, Callable

import stt

from .messages import Book, Card, ErrorCode, Invoke, Media, Stage

SendStage = Callable[[Stage], Awaitable[None]]

log = logging.getLogger("metalab")


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
    return "To be, or not to be, that is the question."


async def think(command: str, page_text: str, session_id: str) -> dict:
    return {
        "title": "Hamlet, Act 3, Scene 1",
        "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
        "speech_text": "Hamlet is alone, weighing whether to keep living.",
        "image_prompt": "A lone prince on a dark stage, bright outline on black",
        "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
    }


async def draw(image_prompt: str) -> str | None:
    return None


async def run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Run every stage, reporting each one before the phone waits on it.

    Transcribing and reading the page run at the same time; reading is cancelled
    if the spoken command is not one we know, or anything else fails before it is used.
    """
    if invoke.text is not None:
        command = command_from(invoke.text)
        await send_stage("reading")
        page_text = await read_page(invoke.frame)
    else:
        await send_stage("transcribing")
        reading = asyncio.create_task(read_page(invoke.frame))
        try:
            command = command_from(await transcribe(invoke.audio))
            await send_stage("reading")
            page_text = await reading
        finally:
            if not reading.done():  # any early exit: do not leave the page read running
                reading.cancel()

    await send_stage("thinking")
    answer = await think(command, page_text, invoke.session_id)

    await send_stage("drawing")
    image_url = await draw(answer["image_prompt"])

    return Card(
        request_id=invoke.request_id,
        title=answer["title"],
        caption=answer["caption"],
        image_url=image_url,
        speech_text=answer["speech_text"],
        book=Book(**answer["book"]),
        sources=[],
        models={"read": "stub", "reason": "stub", "image": "stub"},
    )
