"""Speech to text behind one function, so the engine can be swapped (PRD section 4, Models).

The default engine is faster-whisper, loaded on first use. It is pinned in
backend/stt/requirements.txt, not backend/requirements.txt, so tests and CI never load it;
they swap in a stub with set_engine().

An alternative engine is gemini-3.5-transcribe, selected via STT_ENGINE=gemini.
"""

from __future__ import annotations

import io
import logging
import os
import threading
from typing import Any, Callable

_log = logging.getLogger("metalab")

Engine = Callable[[bytes], str]

DEFAULT_ENGINE = "whisper"
WHISPER_MODEL = "small.en"
GEMINI_MODEL = "gemini-3.5-transcribe"
# Biases Whisper toward the L0 command words, which a short headset clip often loses (#260).
WHISPER_COMMAND_PROMPT = "Explain this. Draw this. Who is this?"

SHAKESPEARE_VOCABULARY_PROMPT = (
    "Transcribe the spoken audio accurately and verbatim. "
    "The speaker is reading or discussing Shakespeare and classic literature. "
    "Bias vocabulary recognition toward Shakespearean terms, Elizabethan and early modern English, "
    "literary terminology, and character names from Shakespeare plays (such as Hamlet, Horatio, "
    "Ophelia, Claudius, Gertrude, Polonius, Macbeth, Othello, Romeo, Juliet, thou, thee, thine, thy). "
    "Output only the exact transcribed speech text without commentary, explanation, or timestamps. "
    "Return an empty string if there is no clear speech in the audio."
)

_engine: Engine | None = None
_engine_lock = threading.Lock()
_gemini_client: Any = None
_fallback_engine: Engine | None = None
_fallback_lock = threading.Lock()
_run_info = threading.local()  # what the last transcription on this thread used (debug log)
GEMINI_TIMEOUT_MS = 15_000  # below the 25 s stage deadline, leaving time for the Whisper fallback


def _get_gemini_timeout_ms() -> int:
    """Read GEMINI_TIMEOUT_MS from env; fall back to the module default if unset or invalid."""
    raw = os.environ.get("GEMINI_TIMEOUT_MS", "").strip()
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return GEMINI_TIMEOUT_MS


def _whisper_fallback() -> Engine:
    """One shared Whisper model for every fallback, built once behind a lock."""
    global _fallback_engine
    with _fallback_lock:
        if _fallback_engine is None:
            _fallback_engine = _faster_whisper()
        return _fallback_engine


def set_engine(engine: Engine | None) -> Engine | None:
    """Replace the speech engine (None restores the default); return the one it replaced."""
    global _engine, _fallback_engine
    with _engine_lock:
        previous, _engine = _engine, engine
        _fallback_engine = None
    return previous


def set_gemini_client(client: Any) -> Any:
    """Set custom Gemini client for dependency injection / stub testing; return previous."""
    global _gemini_client
    previous, _gemini_client = _gemini_client, client
    return previous


def _set_run_info(engine: str, model: str, fallback_reason: str | None = None) -> None:
    _run_info.value = {
        "engine": engine,
        "model": model,
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
    }


def last_run_info() -> dict[str, Any]:
    """Engine, model and fallback of the last transcription on this thread. A swapped-in engine
    (set_engine) reports nothing, so it shows as engine "custom"."""
    info = getattr(_run_info, "value", None)
    if info is None:
        return {"engine": "custom", "model": None, "fallback_used": False, "fallback_reason": None}
    return dict(info)


def warm() -> None:
    """Load the engine now instead of on the first clip (e.g. at server startup)."""
    _loaded()


def transcribe(audio: bytes) -> str:
    """Transcribe one audio clip (any container ffmpeg can decode, e.g. WAV) to text."""
    return _loaded()(audio).strip()


def transcribe_detailed(audio: bytes) -> tuple[str, dict[str, Any]]:
    """transcribe(), plus which engine and model produced the text (see last_run_info)."""
    _run_info.value = None
    text = _loaded()(audio).strip()
    return text, last_run_info()


def _loaded() -> Engine:
    global _engine
    engine = _engine
    if engine is None:
        with _engine_lock:  # concurrent first calls must not each build a model
            if _engine is None:
                engine_type = os.environ.get("STT_ENGINE", DEFAULT_ENGINE).strip().lower()
                if engine_type == "gemini":
                    _engine = _gemini_engine()
                else:
                    _engine = _faster_whisper()
            engine = _engine
    return engine


def _faster_whisper() -> Engine:
    from faster_whisper import WhisperModel  # heavy import: only when really transcribing

    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")

    def run(audio: bytes) -> str:
        _set_run_info("whisper", WHISPER_MODEL)
        segments, _ = model.transcribe(io.BytesIO(audio), language="en", beam_size=1,
                                        initial_prompt=WHISPER_COMMAND_PROMPT)
        return " ".join(s.text.strip() for s in segments)

    return run


def _detect_mime_type(audio: bytes) -> str | None:
    if audio.startswith(b"RIFF"):
        return "audio/wav"
    if audio.startswith(b"ID3") or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mp3"
    if audio.startswith(b"OggS"):
        return "audio/ogg"
    if audio.startswith(b"fLaC"):
        return "audio/flac"
    if audio.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    return None


def _gemini_engine(
    client: Any = None,
    api_key: str | None = None,
    model: str | None = None,
    fallback_to_whisper: bool = True,
) -> Engine:
    """Create a speech transcription engine backed by Gemini (gemini-3.5-transcribe)."""
    target_model = model or os.environ.get("MODEL_TRANSCRIBE", "").strip() or GEMINI_MODEL

    owned: list[Any] = []  # one lazily built client, reused across clips

    def fallback(audio: bytes, reason: str) -> str:
        _set_run_info("gemini", WHISPER_MODEL, reason)
        try:
            return _whisper_fallback()(audio)
        finally:
            _set_run_info("gemini", WHISPER_MODEL, reason)  # the Whisper run records itself as "whisper"

    def run(audio: bytes) -> str:
        _set_run_info("gemini", target_model)
        if not audio or not audio.strip(b"\x00 \t\r\n"):
            raise ValueError("Empty or invalid audio clip")

        resolved_client = client if client is not None else _gemini_client
        if resolved_client is None:
            resolved_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "").strip()
            if not resolved_key:
                _log.debug("taking whisper fallback: GEMINI_API_KEY is not set")
                if fallback_to_whisper:
                    try:
                        return fallback(audio, "no_key")
                    except Exception as fb_exc:
                        _log.debug("whisper fallback also failed: %s: %s", type(fb_exc).__name__, fb_exc)
                raise RuntimeError("GEMINI_API_KEY is not set for Gemini transcription")
            if not owned:
                from google import genai
                from google.genai import types as genai_types

                owned.append(
                    genai.Client(
                        api_key=resolved_key,
                        http_options=genai_types.HttpOptions(timeout=_get_gemini_timeout_ms()),
                    )
                )
            resolved_client = owned[0]

        mime = _detect_mime_type(audio)
        if mime is None:
            _log.debug("taking whisper fallback: unsupported audio format for Gemini")
            if fallback_to_whisper:
                try:
                    return fallback(audio, "bad_format")
                except Exception as fb_exc:
                    _log.debug("whisper fallback also failed: %s: %s", type(fb_exc).__name__, fb_exc)
            raise ValueError("Unsupported audio format for Gemini transcription")

        try:
            from google.genai import types

            audio_part = types.Part.from_bytes(data=audio, mime_type=mime)
            response = resolved_client.models.generate_content(
                model=target_model,
                contents=[SHAKESPEARE_VOCABULARY_PROMPT, audio_part],
            )
        except Exception as exc:
            _log.debug("taking whisper fallback: Gemini call failed: %s: %s", type(exc).__name__, exc)
            if fallback_to_whisper:
                try:
                    return fallback(audio, "gemini_error")
                except Exception as fb_exc:
                    _log.debug("whisper fallback also failed: %s: %s", type(fb_exc).__name__, fb_exc)
            # REQ-PRIV-02: Never log or echo audio bytes or user speech in the exception message
            raise RuntimeError(f"Gemini transcription failed: {type(exc).__name__}") from exc

        text = ""
        if hasattr(response, "text") and response.text:
            text = response.text
        elif getattr(response, "candidates", None):
            for candidate in response.candidates:
                if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                    for part in candidate.content.parts:
                        if getattr(part, "text", None):
                            text += part.text
        if not text.strip():
            _log.debug("taking whisper fallback: Gemini returned empty/blocked response")
            if fallback_to_whisper:
                try:
                    return fallback(audio, "empty_response")
                except Exception as fb_exc:
                    _log.debug("whisper fallback after empty response failed: %s: %s", type(fb_exc).__name__, fb_exc)
            raise RuntimeError("Gemini transcription returned no speech")
        return text.strip()

    return run
