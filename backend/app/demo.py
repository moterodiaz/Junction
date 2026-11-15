"""Canned demo path for the Macbeth dagger page (DEMO_CANNED=on).

A proof of concept for the demo video: every invoke gets the same Macbeth card, with no speech to
text, page reading, reasoning or drawing. The status stages still stream, spread over DEMO_DELAY_S
seconds, so the phone and lens show the progress a real request shows. Off by default.
The card's models say "demo-canned", so nothing claims a model produced it.
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Response

from stt.speak import _resolve_base_url

from .config import ON
from .messages import Book, Card, Invoke, Source, Stage

SendStage = Callable[[Stage], Awaitable[None]]

ASSET_DIR = Path(__file__).resolve().parent / "demo_assets"
IMAGE_NAME = "macbeth_dagger.png"
AUDIO_NAME = "macbeth_dagger.wav"  # optional: drop a spoken clip here and the card offers it
MEDIA = {IMAGE_NAME: "image/png", AUDIO_NAME: "audio/wav"}

DEFAULT_DELAY_S = 2.0
MAX_DELAY_S = 20.0

TITLE = "The Air-Drawn Dagger"
CAPTION = "Macbeth sees a floating dagger, its handle toward his hand. Is it real, or is his guilty mind painting it?"
SPEECH = (
    "Just before he murders King Duncan, Macbeth sees a dagger floating in the air, with its handle "
    "pointing at his hand. He asks whether it is real, or only a trick of his guilty, overheated mind. "
    "The vision shows his conscience and his ambition pulling against each other, right before he goes through with it."
)
BOOK = Book(title="Macbeth", author="William Shakespeare", location="Act 2, Scene 1")
SOURCE = Source(title="Macbeth, Act 2 Scene 1 (MIT Shakespeare)",
                url="https://shakespeare.mit.edu/macbeth/macbeth.2.1.html")


def enabled() -> bool:
    return os.environ.get("DEMO_CANNED", "").strip().lower() in ON


def delay_s() -> float:
    """Total pause across the stages. A missing, malformed or out-of-range value means the default."""
    try:
        value = float(os.environ.get("DEMO_DELAY_S", ""))
    except ValueError:
        return DEFAULT_DELAY_S
    return value if math.isfinite(value) and 0 <= value <= MAX_DELAY_S else DEFAULT_DELAY_S


def _url(name: str) -> str | None:
    base = _resolve_base_url()
    return f"{base}/demo/{name}" if base and (ASSET_DIR / name).is_file() else None


def card(request_id: str) -> Card:
    return Card(
        request_id=request_id,
        title=TITLE,
        caption=CAPTION,
        image_url=_url(IMAGE_NAME),
        speech_text=SPEECH,
        audio_url=_url(AUDIO_NAME),
        book=BOOK,
        sources=[SOURCE],
        models={"read": "demo-canned", "reason": "demo-canned", "image": "demo-canned"},
    )


async def run(invoke: Invoke, send_stage: SendStage) -> Card:
    """Stream the same stages a real request does, then return the fixed card."""
    stages: list[Stage] = ["reading", "thinking", "drawing"]
    if invoke.audio is not None:
        stages.insert(0, "transcribing")
    pause = delay_s() / len(stages)
    for stage in stages:
        await send_stage(stage)
        await asyncio.sleep(pause)
    return card(invoke.request_id)


demo_router = APIRouter()


@demo_router.get("/demo/{name}")
async def serve_asset(name: str) -> Response:
    media_type = MEDIA.get(name)
    path = ASSET_DIR / name
    if media_type is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=path.read_bytes(), media_type=media_type)
