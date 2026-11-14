"""Speech to text behind one function, so the engine can be swapped (PRD section 4, Models).

The default engine is faster-whisper, loaded on first use. It is pinned in
backend/stt/requirements.txt, not backend/requirements.txt, so tests and CI never load it;
they swap in a stub with set_engine().
"""

from __future__ import annotations

import io
import threading
from typing import Callable

Engine = Callable[[bytes], str]

WHISPER_MODEL = "small.en"

_engine: Engine | None = None
_engine_lock = threading.Lock()


def set_engine(engine: Engine | None) -> Engine | None:
    """Replace the speech engine (None restores the default); return the one it replaced."""
    global _engine
    with _engine_lock:
        previous, _engine = _engine, engine
    return previous


def warm() -> None:
    """Load the engine now instead of on the first clip (e.g. at server startup)."""
    _loaded()


def transcribe(audio: bytes) -> str:
    """Transcribe one audio clip (any container ffmpeg can decode, e.g. WAV) to text."""
    return _loaded()(audio).strip()


def _loaded() -> Engine:
    global _engine
    engine = _engine
    if engine is None:
        with _engine_lock:  # concurrent first calls must not each build a model
            if _engine is None:
                _engine = _faster_whisper()
            engine = _engine
    return engine


def _faster_whisper() -> Engine:
    from faster_whisper import WhisperModel  # heavy import: only when really transcribing

    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")

    def run(audio: bytes) -> str:
        segments, _ = model.transcribe(io.BytesIO(audio), language="en", beam_size=1)
        return " ".join(s.text.strip() for s in segments)

    return run
