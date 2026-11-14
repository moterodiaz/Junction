"""Spoken answer (PRD section 3 step 6, section 4 Models): speech_text -> WAV at card.audio_url.

Any failure returns None, so the card ships with audio_url null and the phone speaks
speech_text with the system voice (PRD section 7). Clips live only in memory, belong to the
session that asked, and are deleted with it or after CLIP_TTL_S (section 6).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time
import uuid
import wave
from collections import OrderedDict
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response

log = logging.getLogger("metalab.speak")

DEFAULT_MODEL_TTS = "gemini-3.8-flash-tts"
VOICE = "Kore"
SAMPLE_RATE = 24000  # Gemini TTS returns 16-bit mono PCM at 24 kHz
TTS_TIMEOUT_S = 20
MAX_CLIPS = 50  # oldest clips are dropped first; nothing is written to disk
CLIP_TTL_S = 3600.0  # same as generated images (ai/image.py _DEFAULT_SESSION_TTL)
clock = time.monotonic

# clip id -> (session id, wav, stored at); oldest first
_clips: OrderedDict[str, tuple[Optional[str], bytes, float]] = OrderedDict()
_client: Any = None
_gemini: Optional["GeminiSpeechClient"] = None


class GeminiSpeechClient:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self._genai: Any = None

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        """Return (16-bit mono PCM, sample rate) for text."""
        from google import genai
        from google.genai import types

        if self._genai is None:
            self._genai = genai.Client(api_key=self.api_key)
        response = await self._genai.aio.models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
            ),
        )
        part = next(p for p in response.candidates[0].content.parts if p.inline_data)
        rate = re.search(r"rate=(\d+)", part.inline_data.mime_type or "")
        return part.inline_data.data, int(rate.group(1)) if rate else SAMPLE_RATE


def set_speech_client(client: Any) -> None:
    """Replace the TTS client (None restores the Gemini client from env)."""
    global _client
    _client = client


def _expire() -> None:
    now = clock()
    while _clips and (len(_clips) > MAX_CLIPS or now - next(iter(_clips.values()))[2] > CLIP_TTL_S):
        _clips.popitem(last=False)


def store(wav: bytes, session_id: Optional[str] = None) -> str:
    clip_id = uuid.uuid4().hex
    _clips[clip_id] = (session_id, wav, clock())
    _expire()
    return clip_id


def get(clip_id: str) -> Optional[bytes]:
    _expire()
    clip = _clips.get(clip_id)
    return clip[1] if clip else None


def discard(url: Optional[str]) -> None:
    """Drop the clip behind an audio_url that will never reach the phone."""
    if url:
        _clips.pop(url.rsplit("/", 1)[-1].removesuffix(".wav"), None)


def cleanup_session(session_id: str) -> int:
    """Delete a session's clips (call when the session ends). Returns how many were deleted."""
    _expire()
    ids = [clip_id for clip_id, (sid, _, _) in _clips.items() if sid == session_id]
    for clip_id in ids:
        del _clips[clip_id]
    return len(ids)


def clear() -> None:
    _clips.clear()


def to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return out.getvalue()


async def speak(text: str, session_id: Optional[str] = None) -> Optional[str]:
    """Return an https URL for the spoken text, or None to let the phone speak it."""
    # Same public base as generated images (backend/ai/image.py); the contract needs https.
    base = os.environ.get("IMAGE_BASE_URL", "").strip().rstrip("/")
    client = _client or _gemini_client()
    if client is None or not base.startswith("https://"):
        return None
    try:
        result = await asyncio.wait_for(client.synthesize(text), TTS_TIMEOUT_S)
    except Exception as exc:
        log.warning("speech synthesis failed, the phone will use its own voice: %s",
                    type(exc).__name__)
        return None
    pcm, rate = (result, SAMPLE_RATE) if isinstance(result, bytes) else result
    return f"{base}/audio/{store(to_wav(pcm, rate), session_id)}.wav"


def _gemini_client() -> Optional[GeminiSpeechClient]:
    """One client per key and model, reused across requests; None without a key."""
    global _gemini
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("MODEL_TTS", "").strip() or DEFAULT_MODEL_TTS
    if not key:
        return None
    if _gemini is None or (_gemini.api_key, _gemini.model) != (key, model):
        _gemini = GeminiSpeechClient(key, model)
    return _gemini


audio_router = APIRouter()


@audio_router.get("/audio/{clip_id}.wav")
async def serve_clip(clip_id: str) -> Response:
    wav = get(clip_id)
    if wav is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    return Response(content=wav, media_type="audio/wav")
