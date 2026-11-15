"""Live voice check (REQ-VOICE-01): one typed invoke against a deployed backend, then play the clip.

Run on a Mac from the repo root after backend/test.sh has built backend/.venv:

    backend/.venv/bin/python backend/scripts/voice_check.py --url wss://<workspace>--metalab-web.modal.run/ws \
        --frame page.jpg [--text "explain this"]

Prints each stage with its time, the card's models, whether audio_url is set and the card time,
then downloads the clip, prints its HTTP status, content type, sample rate and length, plays it
with afplay and deletes it. Never prints the transcript, the answer text or the clip URL.
Exits 1 when the request fails, audio_url is null or the download fails. Not imported by tests.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import wave

import httpx
import websockets


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", required=True, help="backend WebSocket URL, e.g. wss://…/ws")
    parser.add_argument("--frame", required=True, help="JPEG photo of a book page")
    parser.add_argument("--text", default="explain this", help="typed command (default: explain this)")
    parser.add_argument("--timeout", type=float, default=90.0, help="seconds to wait for the card")
    parser.add_argument("--no-play", action="store_true", help="download and check the clip, skip afplay")
    return parser.parse_args(argv)


def read_frame(path: str) -> str:
    with open(path, "rb") as handle:
        data = handle.read()
    if not data.startswith(b"\xff\xd8"):
        raise SystemExit(f"{path} is not a JPEG")
    return base64.b64encode(data).decode()


async def invoke(url: str, frame_b64: str, text: str, timeout: float) -> dict | None:
    """Send one typed invoke and return the card, or None after an error reply."""
    request_id = f"voice-check-{uuid.uuid4().hex[:8]}"
    message = {"type": "invoke", "request_id": request_id, "session_id": f"voice-check-{uuid.uuid4().hex}",
               "frame": {"mime": "image/jpeg", "b64": frame_b64}, "audio": None, "text": text}
    async with websockets.connect(url, max_size=None, open_timeout=30) as ws:
        sent = time.monotonic()
        await ws.send(json.dumps(message))
        print(f"sent invoke {request_id} ({len(frame_b64) * 3 // 4} byte frame)")
        last = sent
        deadline = sent + timeout
        while True:
            raw = await asyncio.wait_for(ws.recv(), max(deadline - time.monotonic(), 0.1))
            reply = json.loads(raw)
            now = time.monotonic()
            if reply.get("type") == "status":
                print(f"  stage {reply.get('stage'):<12} at {now - sent:5.1f} s (+{now - last:.1f} s)")
                last = now
            elif reply.get("type") == "card":
                print(f"card at {now - sent:.1f} s (+{now - last:.1f} s after the last stage)")
                print(f"  models: {json.dumps(reply.get('models'))}")
                print(f"  image_url: {'set' if reply.get('image_url') else 'null'}")
                print(f"  audio_url: {'set' if reply.get('audio_url') else 'null'}")
                return reply
            elif reply.get("type") == "error":
                print(f"error at {now - sent:.1f} s: code={reply.get('code')} retryable={reply.get('retryable')}")
                return None
            else:
                print(f"  unexpected reply type {reply.get('type')!r}, ignored")


def fetch_clip(audio_url: str) -> bytes | None:
    started = time.monotonic()
    try:
        response = httpx.get(audio_url, timeout=30.0)
    except httpx.HTTPError as exc:
        print(f"clip download failed: {type(exc).__name__}")
        return None
    print(f"clip: HTTP {response.status_code}, {response.headers.get('content-type', '?')}, "
          f"{len(response.content)} bytes in {time.monotonic() - started:.1f} s")
    if response.status_code != 200 or not response.content:
        return None
    try:
        with wave.open(io.BytesIO(response.content)) as wav:
            rate, frames, channels = wav.getframerate(), wav.getnframes(), wav.getnchannels()
    except (wave.Error, EOFError) as exc:
        print(f"clip is not a readable WAV: {type(exc).__name__}")
        return None
    print(f"clip: {rate} Hz, {channels} channel(s), {frames / rate if rate else 0:.1f} s")
    return response.content


def play(wav: bytes) -> None:
    handle = tempfile.NamedTemporaryFile(prefix="voice-check-", suffix=".wav", delete=False)
    try:
        handle.write(wav)
        handle.close()
        print("playing with afplay…")
        subprocess.run(["afplay", handle.name], check=False)
    finally:
        os.unlink(handle.name)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.url.startswith(("wss://", "ws://")):
        print("--url must start with wss:// (or ws:// for a local backend)")
        return 2
    frame = read_frame(args.frame)
    try:
        card = asyncio.run(invoke(args.url, frame, args.text, args.timeout))
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
        print(f"request failed: {type(exc).__name__}")
        return 1
    if card is None:
        return 1
    if not card.get("audio_url"):
        print("FAIL: audio_url is null, so the phone would use its own voice. "
              "Check `modal app logs metalab` for 'speech synthesis'.")
        return 1
    wav = fetch_clip(card["audio_url"])
    if wav is None:
        print("FAIL: the clip could not be downloaded")
        return 1
    if not args.no_play:
        play(wav)
    print("OK: check `modal app logs metalab` for 'speech ready: provider=elevenlabs'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
