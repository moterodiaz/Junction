"""Pipeline stages (PRD section 3, step 4). Each stage is a stub that later tasks replace:
transcribe -> #27 (backend/stt/), read_page -> #28, think -> #30, draw -> #31.
"""

from __future__ import annotations

import os
from typing import Awaitable, Callable

from ai import page_reader

from .messages import Book, Card, Invoke, Media, Stage

SendStage = Callable[[Stage], Awaitable[None]]


async def transcribe(audio: Media) -> str:
    return "explain"


async def read_page(frame: Media) -> str:
    # Offline/test path: preserve deterministic contract fixtures without an API key.
    if not os.environ.get("NVIDIA_API_KEY", "").strip():
        return "To be, or not to be, that is the question."

    return await page_reader.read_page(frame)


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
    """Run every stage in order, reporting each one before it starts."""
    if invoke.text is not None:
        command = invoke.text.strip()
    else:
        await send_stage("transcribing")
        command = await transcribe(invoke.audio)

    await send_stage("reading")
    page_text = await read_page(invoke.frame)

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
