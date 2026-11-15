"""Spoken answer (PRD section 3 step 6, section 4 Models): speech_text -> WAV at card.audio_url.

ElevenLabs speaks when ELEVEN_LABS_API_KEY and ELEVEN_LABS_VOICE_ID are set; if it fails, Gemini
tries once (with GEMINI_API_KEY) inside the same TTS_TIMEOUT_S.

Any failure returns None, so the card ships with audio_url null and the phone speaks
speech_text with the system voice (PRD section 7). Clips live only in memory, belong to the
session that asked, and are deleted with it or after CLIP_TTL_S (section 6).
"""

from __future__ import annotations

import base64
import asyncio
import io
import logging
import os
import re
import threading
import time
import uuid
import wave
from collections import OrderedDict
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response

from .elevenlabs import DEFAULT_MODEL_TTS_ELEVENLABS, ElevenLabsSpeechClient

log = logging.getLogger("metalab.speak")

DEFAULT_MODEL_TTS = "gemini-3.8-flash-tts"
VOICE = "Kore"
SAMPLE_RATE = 24000  # Gemini TTS returns 16-bit mono PCM at 24 kHz
TTS_TIMEOUT_S = 20
MAX_CLIPS = 50  # oldest clips are dropped first; nothing is written to disk
CLIP_TTL_S = 3600.0  # same as generated images (ai/image.py _DEFAULT_SESSION_TTL)
SWEEP_EVERY_S = 60.0  # expiry runs on its own, not only when more audio is requested
clock = time.monotonic

# clip id -> (session id, wav, stored at); oldest first
_clips: OrderedDict[str, tuple[Optional[str], bytes, float]] = OrderedDict()
_epochs: OrderedDict[str, int] = OrderedDict()  # bumped when a session ends; speech started before is dropped
_MAX_EPOCH_ENTRIES = 1000  # ponytail: LRU cap; switch to TTL-based pruning if sessions exceed 1000 at peak
_epochs_inflight: dict[str, int] = {}  # session_id -> count of active speak() calls
_lock = threading.Lock()  # the sweeper thread and the event loop both touch _clips
_sweeper: Optional[threading.Thread] = None
_sweep_now = threading.Event()  # wakes the sweeper early (tests)
_client: Any = None
_gemini: Optional["GeminiSpeechClient"] = None
_elevenlabs: Optional[ElevenLabsSpeechClient] = None
_served_by: OrderedDict[str, Any] = OrderedDict()  # clip id -> client that made it, for model attribution


def is_not_found(exc: BaseException) -> bool:
    """True for a provider 404 (model not found). The generateContent client sets .code and
    .status; the Interactions client raises NotFoundError with only .status_code."""
    return (getattr(exc, "code", None) == 404 or getattr(exc, "status_code", None) == 404
            or getattr(exc, "status", None) == "NOT_FOUND")


class GeminiSpeechClient:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model, self._configured_model = api_key, model, model
        self._genai: Any = None

    async def list_tts_models(self) -> list[str]:
        """Names of the models this key can use for speech, for diagnosing a wrong MODEL_TTS."""
        from google import genai

        if self._genai is None:
            self._genai = genai.Client(api_key=self.api_key)
        names = []
        async for m in await self._genai.aio.models.list():
            name = (getattr(m, "name", "") or "").removeprefix("models/")
            if "tts" in name.lower():
                names.append(name)
        return sorted(names)

    async def _generate(self, text: str) -> Any:
        """Gemini 3.8 TTS takes speech through the Interactions API; generateContent with
        SpeechConfig is rejected (400 'Unknown name speechConfig'), per the Gemini TTS docs."""
        return await self._genai.aio.interactions.create(
            model=self.model,
            input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
            response_format={"type": "audio", "mime_type": "audio/l16", "sample_rate": SAMPLE_RATE},
            generation_config={"speech_config": [{"voice": VOICE}]},
        )

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        """Return (16-bit mono PCM, sample rate) for text.

        If the configured model does not exist for this key (HTTP 404), switch once to the best
        TTS model the key can use (Flash before Pro, stable before preview) and retry, so a
        wrong MODEL_TTS in the secret costs one slower request instead of every spoken answer."""
        from google import genai

        if self._genai is None:
            self._genai = genai.Client(api_key=self.api_key)
        failed_model = self.model
        try:
            response = await self._generate(text)
        except Exception as exc:
            if not is_not_found(exc):
                raise
            _orig_exc = exc
            try:
                names = await self.list_tts_models()
            except Exception as lookup_exc:
                log.warning("TTS model list failed during fallback: %s", type(lookup_exc).__name__)
                raise _orig_exc from None
            best = min(names, key=lambda n: ("flash" not in n.lower(), "preview" in n.lower(), n), default=None)
            if best is None or best == failed_model:
                exc.tts_models = names
                raise
            if self.model == failed_model:
                log.warning("TTS model %s not found; using %s from now on", failed_model, best)
                self.model = best
            response = await self._generate(text)
        audio = getattr(response, "output_audio", None)
        data = getattr(audio, "data", None) if audio is not None else None
        if not data:
            raise RuntimeError("no audio in speech response")
        if isinstance(data, str):  # the API returns base64 text
            data = base64.b64decode(data)
        return data, getattr(audio, "sample_rate", None) or SAMPLE_RATE


def set_speech_client(client: Any) -> None:
    """Replace the TTS client (None restores the ElevenLabs or Gemini client from env)."""
    global _client
    _client = client
    _served_by.clear()


def _expire() -> None:
    now = clock()
    with _lock:
        while _clips and (len(_clips) > MAX_CLIPS or now - next(iter(_clips.values()))[2] > CLIP_TTL_S):
            _clips.popitem(last=False)


def _sweep_forever() -> None:
    while True:
        _sweep_now.wait(SWEEP_EVERY_S)
        _sweep_now.clear()
        _expire()


def _start_sweeper() -> None:
    global _sweeper
    with _lock:
        if _sweeper is None:
            _sweeper = threading.Thread(target=_sweep_forever, name="tts-clip-sweeper", daemon=True)
            _sweeper.start()


def store(wav: bytes, session_id: Optional[str] = None) -> str:
    _start_sweeper()
    clip_id = uuid.uuid4().hex
    with _lock:
        _clips[clip_id] = (session_id, wav, clock())
    _expire()
    return clip_id


def get(clip_id: str) -> Optional[bytes]:
    _expire()
    with _lock:
        clip = _clips.get(clip_id)
    return clip[1] if clip else None


def discard(url: Optional[str]) -> None:
    """Drop the clip behind an audio_url that will never reach the phone."""
    if url:
        with _lock:
            _clips.pop(url.rsplit("/", 1)[-1].removesuffix(".wav"), None)


def cleanup_session(session_id: str) -> int:
    """Delete a session's clips (call when the session ends), including speech still being
    made for it. Returns how many stored clips were deleted."""
    _expire()
    with _lock:
        _epochs[session_id] = _epochs.get(session_id, 0) + 1
        _epochs.move_to_end(session_id)  # LRU: most recently touched → last to be pruned
        if len(_epochs) > _MAX_EPOCH_ENTRIES:
            # Prune the least-recently-used entry that has no in-flight speak() call.
            # A session reusing a saved id may still be speaking; pruning its entry would
            # reset its epoch to 0 and cause valid speech to be dropped as stale.
            for sid in list(_epochs.keys()):
                if not _epochs_inflight.get(sid, 0):
                    _epochs.pop(sid)
                    break
        ids = [clip_id for clip_id, (sid, _, _) in _clips.items() if sid == session_id]
        for clip_id in ids:
            del _clips[clip_id]
    return len(ids)


def clear() -> None:
    with _lock:
        _clips.clear()
        _epochs.clear()
        _epochs_inflight.clear()


def to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return out.getvalue()


def _resolve_base_url() -> Optional[str]:
    """Resolve public HTTPS base URL for audio clips (PRD section 4, section 7)."""
    base = os.environ.get("IMAGE_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("https://"):
        if base.startswith("http://"):
            base = "https://" + base[7:]
        else:
            base = f"https://{base}"
    return base


def describe_failure(exc: BaseException, text: str = "", key: str = "") -> str:
    """What to log about a failed synthesis: the exception type, the provider's HTTP code and
    status name, and a short single-line reason. Never the answer text or the API key."""
    parts = [type(exc).__name__]
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = getattr(exc, "status", None)
    if isinstance(code, int):
        parts.append(f"code={code}")
    if isinstance(status, str) and status:
        parts.append(f"status={status}")
    raw = " ".join(str(getattr(exc, "message", "") or "").split())
    for secret in (" ".join(key.split()), " ".join(text.split())):
        if secret and secret in raw:
            raw = raw.replace(secret, "[redacted]")
    reason = raw[:200]
    if reason:
        parts.append(f"reason={reason}")
    return " ".join(parts)


_listed_models = False


async def log_tts_models(client: Any, exc: Any = None) -> None:
    """After a model-not-found error, log which TTS models this key can use (names only, once per
    process), so a wrong MODEL_TTS can be fixed from the log. Reuses names already fetched by
    synthesize() (attached as exc.tts_models) to avoid a second network round-trip."""
    global _listed_models
    if _listed_models or not hasattr(client, "list_tts_models"):
        return
    _listed_models = True
    cached = getattr(exc, "tts_models", None) if exc is not None else None
    if cached is not None:
        log.warning("TTS models available to this key: %s", ", ".join(cached[:12]) or "none")
        return
    try:
        names = await asyncio.wait_for(client.list_tts_models(), 10)
        log.warning("TTS models available to this key: %s", ", ".join(names[:12]) or "none")
    except Exception as exc:
        log.warning("could not list TTS models: %s", type(exc).__name__)


def provider_name(client: Any) -> str:
    """elevenlabs, gemini, or custom (a client set with set_speech_client, e.g. a test stub)."""
    if isinstance(client, ElevenLabsSpeechClient):
        return "elevenlabs"
    if isinstance(client, GeminiSpeechClient):
        return "gemini"
    return "custom"


def log_speech_ready(first: Any, served: Any, synth_s: float, pcm: bytes, rate: int, wav_bytes: int) -> None:
    """One line per stored clip naming the voice that spoke, so a live test can tell the
    ElevenLabs voice from the Gemini fallback. Never the answer text or the key."""
    model = getattr(served, "model", None) or "unknown"
    audio_s = len(pcm) / (2 * rate) if rate else 0.0
    log.info("speech ready: provider=%s model=%s fallback=%s synth_s=%.1f audio_s=%.1f bytes=%d",
             provider_name(served), model, "true" if served is not first else "false",
             synth_s, audio_s, wav_bytes)


async def speak(text: str, session_id: Optional[str] = None) -> Optional[str]:
    """Return an https URL for the spoken text, or None to let the phone speak it."""
    # Same public base as generated images (backend/ai/image.py); the contract needs https.
    base = _resolve_base_url()
    client = _client or _elevenlabs_client() or _gemini_client()
    if client is None:
        log.info("speech synthesis skipped: no TTS client, ElevenLabs and GEMINI_API_KEY unset")
        return None
    if base is None:
        log.info("speech synthesis skipped: IMAGE_BASE_URL unset")
        return None
    if not text or not text.strip():
        log.info("speech synthesis skipped: empty speech_text")
        return None
    epoch = _epochs.get(session_id, 0) if session_id is not None else None
    if session_id is not None:
        if session_id in _epochs:
            _epochs.move_to_end(session_id)  # LRU: active session stays at the back
        _epochs_inflight[session_id] = _epochs_inflight.get(session_id, 0) + 1
    # The ElevenLabs attempt and its one Gemini fallback share a single TTS_TIMEOUT_S budget.
    attempt = {"client": client}
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(_synthesize(client, text, attempt), TTS_TIMEOUT_S)
    except Exception as exc:
        failed = attempt["client"]
        log.warning("speech synthesis failed, the phone will use its own voice: %s",
                    describe_failure(exc, text, getattr(failed, "api_key", "")))
        if is_not_found(exc):
            await log_tts_models(failed, exc)
        return None
    finally:
        if session_id is not None:
            count = _epochs_inflight.get(session_id, 0) - 1
            if count <= 0:
                _epochs_inflight.pop(session_id, None)
            else:
                _epochs_inflight[session_id] = count
    if session_id is not None:
        if _epochs.get(session_id, 0) != epoch:
            log.info("speech synthesis dropped: session ended during synthesis")
            return None  # the session ended while this speech was being made
    pcm, rate = (result, SAMPLE_RATE) if isinstance(result, bytes) else result
    if not pcm:
        log.warning("speech synthesis returned empty audio")
        return None
    synth_s = time.monotonic() - started
    wav = to_wav(pcm, rate)
    clip_id = store(wav, session_id)
    log_speech_ready(client, attempt["client"], synth_s, pcm, rate, len(wav))
    _served_by[clip_id] = attempt["client"]  # tied to this clip, not to the latest request
    while len(_served_by) > MAX_CLIPS:
        _served_by.popitem(last=False)
    return f"{base}/audio/{clip_id}.wav"


def client_for(audio_url: Optional[str]) -> Optional[Any]:
    """The client that made the clip behind audio_url; the active client if unknown."""
    if _client:
        return _client
    clip_id = audio_url.rsplit("/", 1)[-1].removesuffix(".wav") if audio_url else ""
    return _served_by.get(clip_id) or active_speech_client()


async def _synthesize(client: Any, text: str, attempt: dict) -> Any:
    """client.synthesize(text); if ElevenLabs fails and a Gemini key is set, Gemini once.
    attempt["client"] names the client that made (or last failed to make) the audio."""
    try:
        return await client.synthesize(text)
    except Exception as exc:
        fallback = _gemini_client() if isinstance(client, ElevenLabsSpeechClient) else None
        if fallback is None:
            raise
        log.warning("ElevenLabs speech failed, trying Gemini: %s",
                    describe_failure(exc, text, client.api_key))
    attempt["client"] = fallback
    return await fallback.synthesize(text)


def _elevenlabs_client() -> Optional[ElevenLabsSpeechClient]:
    """One client per key, voice and model; None unless both ElevenLabs variables are set."""
    global _elevenlabs
    key = os.environ.get("ELEVEN_LABS_API_KEY", "").strip()
    voice = os.environ.get("ELEVEN_LABS_VOICE_ID", "").strip()
    model = os.environ.get("MODEL_TTS_ELEVENLABS", "").strip() or DEFAULT_MODEL_TTS_ELEVENLABS
    if not key or not voice:
        return None
    if _elevenlabs is None or (_elevenlabs.api_key, _elevenlabs.voice_id, _elevenlabs._configured_model) != (key, voice, model):
        _elevenlabs = ElevenLabsSpeechClient(key, voice, model)
    return _elevenlabs


def _gemini_client() -> Optional[GeminiSpeechClient]:
    """One client per key and model, reused across requests; None without a key."""
    global _gemini
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("MODEL_TTS", "").strip() or DEFAULT_MODEL_TTS
    if not key:
        return None
    if _gemini is None or (_gemini.api_key, _gemini._configured_model) != (key, model):
        _gemini = GeminiSpeechClient(key, model)
    return _gemini


def active_speech_client() -> Optional[Any]:
    """Return the current TTS client without creating one; None if no client or key. For the
    client that made a given clip (Gemini after an ElevenLabs failure), use client_for()."""
    return _client or _elevenlabs or _gemini


audio_router = APIRouter()


@audio_router.get("/audio/{clip_id}.wav")
async def serve_clip(clip_id: str) -> Response:
    wav = get(clip_id)
    if wav is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    return Response(content=wav, media_type="audio/wav")
