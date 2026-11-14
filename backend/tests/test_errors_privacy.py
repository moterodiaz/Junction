"""#32: every failure maps to a contract error, and requests leave no frame or audio behind (PRD section 6)."""

import asyncio
import base64
import gc
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

import stt
from app import pipeline
from app.main import app
from app.messages import Invoke, Media

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
AUDIO = {"mime": "audio/wav", "b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="}


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


def replies_to(message, until=("card", "error")):
    """Send one message; collect replies up to and including the first card or error."""
    out = []
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json(message) if not isinstance(message, str) else ws.send_text(message)
        while True:
            out.append(ws.receive_json())
            if out[-1]["type"] in until:
                return out



class OfflineKeysMixin:
    """Keep tests offline: no live model keys, whatever the shell exports."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)


class ErrorMappingTest(OfflineKeysMixin, unittest.TestCase):
    def last_reply_with(self, stage, replacement, **env):
        with mock.patch.object(pipeline, stage, replacement), \
                mock.patch.dict(os.environ, env):
            return replies_to(invoke())[-1]

    def test_slow_stage_is_model_timeout(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(5)

        with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 0.05):
            reply = self.last_reply_with("think", slow)
        self.assertEqual((reply["type"], reply["code"], reply["retryable"]),
                         ("error", "model_timeout", True))

    def test_stage_raising_timeout_error_is_model_timeout(self):
        async def times_out(*args):
            raise TimeoutError("upstream read timed out")

        reply = self.last_reply_with("read_page", times_out)
        self.assertEqual((reply["code"], reply["retryable"]), ("model_timeout", True))
        self.assertNotIn("upstream", reply["message"])

    def test_http_client_timeout_is_model_timeout(self):
        async def http_timeout(*args, **kwargs):
            raise httpx.ReadTimeout("read timed out")

        reply = self.last_reply_with("think", http_timeout)
        self.assertEqual((reply["code"], reply["retryable"]), ("model_timeout", True))

    def test_speech_engine_timeout_is_model_timeout(self):
        def slow_engine(audio):
            raise TimeoutError("engine timed out")

        self.addCleanup(stt.set_engine, stt.set_engine(slow_engine))
        reply = replies_to(invoke(text=None, audio=AUDIO))[-1]
        self.assertEqual((reply["code"], reply["retryable"]), ("model_timeout", True))

    def test_stage_raising_pipeline_error_keeps_its_code(self):
        async def blank_page(*args):
            raise pipeline.PipelineError("no_text_found", "I can't see any text on this page.", True)

        reply = self.last_reply_with("read_page", blank_page)
        self.assertEqual((reply["code"], reply["message"]),
                         ("no_text_found", "I can't see any text on this page."))

    def test_unexpected_exception_is_internal_and_retryable(self):
        async def boom(*args):
            raise KeyError("secret detail")

        reply = self.last_reply_with("draw", boom)
        self.assertEqual((reply["code"], reply["retryable"]), ("internal", True))
        self.assertNotIn("secret", reply["message"])


_audit = {"writes": None}


def _audit_hook(event, args):
    # Sees every open in the process (open, io.open, Path.write_bytes, os.open, tempfile...).
    if event == "open" and _audit["writes"] is not None:
        path, mode, flags = args
        writing = (mode is not None and any(c in mode for c in "wax+")) or \
            (mode is None and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        if writing:
            _audit["writes"].append(path)


sys.addaudithook(_audit_hook)  # audit hooks cannot be removed; it is inert outside writes_during()


def writes_during(fn):
    _audit["writes"] = []
    try:
        fn()
        return _audit["writes"]
    finally:
        _audit["writes"] = None


def private_request():
    """Run one spoken request with random frame and audio; return markers to search memory for."""
    frame_marker, audio_marker = os.urandom(24), os.urandom(24)
    frame_b64 = base64.b64encode(frame_marker + os.urandom(48)).decode()
    audio_b64 = base64.b64encode(audio_marker + os.urandom(48)).decode()
    replies = replies_to(invoke(text=None, frame={"mime": "image/jpeg", "b64": frame_b64},
                                audio={"mime": "audio/wav", "b64": audio_b64}))
    assert replies[-1]["type"] == "card", replies[-1]
    # 24 marker bytes encode to exactly 32 base64 chars, so these prefixes are stable.
    return [base64.b64encode(frame_marker).decode(), base64.b64encode(audio_marker).decode(),
            frame_marker, audio_marker]


def kept_in_memory(markers):
    """Live containers still holding the request's frame/audio (as base64 text or raw bytes)."""
    gc.collect()
    hits = []
    # gc.get_objects() skips dicts holding only strings/bytes, so also walk module globals,
    # where a cache such as CACHE = {"frame": frame.b64} would live.
    roots = [vars(m) for name, m in list(sys.modules.items())
             if m is not None and name.split(".")[0] in ("app", "ai", "stt")]
    for obj in list(gc.get_objects()) + roots + [v for r in roots for v in r.values()
                                                 if isinstance(v, dict)]:
        if obj is markers:  # the search terms themselves
            continue
        if isinstance(obj, (Invoke, Media)):
            hits.append(type(obj).__name__)
            continue
        if isinstance(obj, dict):
            items = list(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            items = list(obj)
        else:
            continue
        for item in items:
            if isinstance(item, (str, bytes, bytearray)) and \
                    any(type(m) is type(item) and m in item for m in markers):
                hits.append(type(item).__name__)
    return hits


class PrivacyTest(OfflineKeysMixin, unittest.TestCase):
    """PRD section 6: frames and audio are processed in memory, never written, never kept."""

    def setUp(self):
        super().setUp()
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "explain"))

    def test_a_request_writes_nothing_to_disk(self):
        self.assertEqual(writes_during(private_request), [])

    def test_no_frame_or_audio_is_kept_after_the_card(self):
        self.assertEqual(kept_in_memory(private_request()), [])

    # The detectors must catch real leaks, or the two tests above prove nothing.
    def test_detectors_catch_a_leaky_stage(self):
        kept = []

        async def leaky_read(frame):
            Path(tempfile.gettempdir(), "metalab-privacy-probe.jpg").write_bytes(b"x")
            kept.append(frame.b64)
            return "page"

        with mock.patch.object(pipeline, "read_page", leaky_read):
            writes = writes_during(lambda: kept.append(private_request()))
        Path(tempfile.gettempdir(), "metalab-privacy-probe.jpg").unlink()
        self.assertTrue(writes)
        self.assertTrue(kept_in_memory(kept.pop()))

    def test_detector_catches_a_string_only_cache(self):
        async def caching_read(frame):
            pipeline.LEAK_CACHE = {"frame": frame.b64}
            return "page"

        self.addCleanup(lambda: vars(pipeline).pop("LEAK_CACHE", None))
        with mock.patch.object(pipeline, "read_page", caching_read):
            markers = private_request()
        self.assertTrue(kept_in_memory(markers))


class SttSlotTest(unittest.TestCase):
    def test_stuck_engine_cannot_queue_more_audio(self):
        import threading

        release = threading.Event()
        calls = []

        def stuck(audio):
            calls.append(audio)
            release.wait(5)
            return "explain"

        self.addCleanup(stt.set_engine, stt.set_engine(stuck))
        self.addCleanup(release.set)
        media = Media(mime="audio/wav", b64=AUDIO["b64"])

        async def go():
            tasks = [asyncio.ensure_future(pipeline.transcribe(media)) for _ in range(2)]
            await asyncio.sleep(0.1)
            with self.assertRaises(pipeline.PipelineError) as ctx:
                await pipeline.transcribe(media)
            release.set()
            await asyncio.gather(*tasks)
            return ctx.exception.code

        self.assertEqual(asyncio.run(go()), "model_timeout")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
