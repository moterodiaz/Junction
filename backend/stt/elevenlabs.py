"""ElevenLabs text to speech (PRD section 4, Models): speech_text -> 16-bit mono PCM at 24 kHz.

Used by stt/speak.py ahead of Gemini when ELEVEN_LABS_API_KEY and ELEVEN_LABS_VOICE_ID are set.
Errors carry the HTTP status_code and the provider's short status, never the key or the text.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DEFAULT_MODEL_TTS_ELEVENLABS = "eleven_flash_v2_5"
SAMPLE_RATE = 24000  # output_format=pcm_24000 is raw 16-bit little-endian mono PCM
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
REQUEST_TIMEOUT_S = 20.0  # speak.py's TTS_TIMEOUT_S bounds the whole attempt as well


class ElevenLabsError(RuntimeError):
    """A failed ElevenLabs request. Shaped for speak.describe_failure: status_code, status, message."""

    def __init__(self, status_code: Optional[int], status: str = "", message: str = ""):
        super().__init__(f"ElevenLabs speech failed ({status_code or 'no audio'})")
        self.status_code, self.status, self.message = status_code, status, message


def _error_from(response: httpx.Response) -> ElevenLabsError:
    """ElevenLabs answers errors as {"detail": {"status": ..., "message": ...}} (or a string)."""
    status, message = "", ""
    try:
        detail: Any = response.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, dict):
        status = str(detail.get("status") or "")
        message = str(detail.get("message") or "")
    elif isinstance(detail, str):
        message = detail
    # Not cut here: speak.describe_failure redacts the key and text first, then cuts to 200.
    return ElevenLabsError(response.status_code, status, " ".join(message.split()))


class ElevenLabsSpeechClient:
    def __init__(self, api_key: str, voice_id: str, model: Optional[str] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.api_key, self.voice_id = api_key, voice_id
        self.model = (model or os.environ.get("MODEL_TTS_ELEVENLABS", "").strip()
                      or DEFAULT_MODEL_TTS_ELEVENLABS)
        self._configured_model = self.model
        self._transport = transport  # tests pass httpx.MockTransport; None means the network

    def __repr__(self) -> str:
        return f"ElevenLabsSpeechClient(model={self.model!r})"

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        """Return (PCM, sample rate). Raises ElevenLabsError on a non-2xx answer or empty audio."""
        # A client per call: speak() may run under different event loops (tests, workers).
        async with httpx.AsyncClient(transport=self._transport, timeout=REQUEST_TIMEOUT_S) as http:
            response = await http.post(
                API_URL.format(voice_id=self.voice_id),
                params={"output_format": f"pcm_{SAMPLE_RATE}"},
                headers={"xi-api-key": self.api_key},
                json={"text": text, "model_id": self.model},
            )
        if not response.is_success:
            raise _error_from(response)
        if not response.content:
            raise ElevenLabsError(None, "", "no audio in speech response")
        return response.content, SAMPLE_RATE
