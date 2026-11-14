"""Spoken answer (PRD section 3 step 6, section 4 Models): speech_text -> WAV at card.audio_url.

Any failure returns None, so the card ships with audio_url null and the phone speaks
speech_text with the system voice (PRD section 7). Clips live only in memory (section 6).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
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

_clips: OrderedDict[str, bytes] = OrderedDict()
_client: Any = None


class GeminiSpeechClient:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def synthesize(self, text: str) -> bytes:
        from google import genai
        from google.genai import types

        response = await genai.Client(api_key=self.api_key).aio.models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
            ),
        )
        return response.candidates[0].content.parts[0].inline_data.data


def set_speech_client(client: Any) -> None:
    """Replace the TTS client (None restores the Gemini client from env)."""
    global _client
    _client = client


def store(wav: bytes) -> str:
    clip_id = uuid.uuid4().hex
    _clips[clip_id] = wav
    while len(_clips) > MAX_CLIPS:
        _clips.popitem(last=False)
    return clip_id


def get(clip_id: str) -> Optional[bytes]:
    return _clips.get(clip_id)


def clear() -> None:
    _clips.clear()


def to_wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return out.getvalue()


async def speak(text: str) -> Optional[str]:
    """Return an https URL for the spoken text, or None to let the phone speak it."""
    # Same public base as generated images (backend/ai/image.py); the contract needs https.
    base = os.environ.get("IMAGE_BASE_URL", "").strip().rstrip("/")
    client = _client
    if client is None and os.environ.get("GEMINI_API_KEY", "").strip():
        client = GeminiSpeechClient(os.environ["GEMINI_API_KEY"].strip(),
                                    os.environ.get("MODEL_TTS", "").strip() or DEFAULT_MODEL_TTS)
    if client is None or not base.startswith("https://"):
        return None
    try:
        pcm = await asyncio.wait_for(client.synthesize(text), TTS_TIMEOUT_S)
    except Exception as exc:
        log.warning("speech synthesis failed, the phone will use its own voice: %s",
                    type(exc).__name__)
        return None
    return f"{base}/audio/{store(to_wav(pcm))}.wav"


audio_router = APIRouter()


@audio_router.get("/audio/{clip_id}.wav")
async def serve_clip(clip_id: str) -> Response:
    wav = get(clip_id)
    if wav is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    return Response(content=wav, media_type="audio/wav")
