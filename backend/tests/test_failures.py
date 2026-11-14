"""#102: a slow image never costs the card, failures never log user text, odd codes stay mapped."""

import asyncio
import contextlib
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import stt
from ai.page_reader import PageReadError
from app import pipeline
from app.main import app

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
AUDIO = {"mime": "audio/wav", "b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="}
SECRET = "To be, or not to be SECRET-PAGE-TEXT"


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


def final_reply(message):
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json(message)
        while (reply := ws.receive_json())["type"] == "status":
            pass
    return reply


class OfflineTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "explain"))


class SlowImageTest(OfflineTest):
    def test_slow_image_still_sends_the_card_without_a_picture(self):
        async def slow_draw(*args, **kwargs):
            await asyncio.sleep(1)
            return "https://metalab.example/img/late.png"

        with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 0.05), \
                mock.patch.object(pipeline, "draw", slow_draw):
            reply = final_reply(invoke())
        self.assertEqual(reply["type"], "card")
        self.assertIsNone(reply["image_url"])


class NoUserTextInLogsTest(OfflineTest):
    def logs_for(self, message, **patches):
        with self.assertLogs("metalab", level="DEBUG") as logs, contextlib.ExitStack() as stack:
            if patches:
                stack.enter_context(mock.patch.multiple(pipeline, **patches))
            reply = final_reply(message)
        return reply, "\n".join(logs.output)

    def assert_type_but_not_text(self, logged, exc_type):
        self.assertNotIn("SECRET-PAGE-TEXT", logged)
        self.assertIn(exc_type, logged)

    def test_failing_stage(self):
        async def think(*args, **kwargs):
            raise RuntimeError(SECRET)

        reply, logged = self.logs_for(invoke(), think=think)
        self.assertEqual((reply["type"], reply["code"]), ("error", "internal"))
        self.assert_type_but_not_text(logged, "RuntimeError")

    def test_failing_page_reader(self):
        async def read_page(frame):
            raise PageReadError(SECRET, code="internal")

        reply, logged = self.logs_for(invoke(), read_page=read_page)
        self.assertEqual(reply["code"], "internal")
        self.assert_type_but_not_text(logged, "PageReadError")

    def test_failing_image_and_speech(self):
        async def boom(*args, **kwargs):
            raise RuntimeError(SECRET)

        async def think(*args, **kwargs):  # a key turns on real reasoning too; keep it offline
            return {"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                    "book": {"title": "b", "author": "a", "location": "l"}}

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "key"}), \
                mock.patch("ai.image.draw", boom):
            reply, logged = self.logs_for(invoke(), speak=boom, think=think)
        self.assertEqual(reply["type"], "card")
        self.assert_type_but_not_text(logged, "RuntimeError")

    def test_failing_speech_engine(self):
        def engine(audio):
            raise RuntimeError(SECRET)

        stt.set_engine(engine)
        reply, logged = self.logs_for(invoke(text=None, audio=AUDIO))
        self.assertEqual(reply["code"], "stt_failed")
        self.assert_type_but_not_text(logged, "RuntimeError")


class UnknownPageReadCodeTest(OfflineTest):
    def test_unknown_code_still_reaches_the_phone_as_internal(self):
        async def read_page(frame):
            raise PageReadError("new failure", code="quota_exceeded")

        with mock.patch.object(pipeline, "read_page", read_page):
            reply = final_reply(invoke())
        self.assertEqual((reply["type"], reply["code"], reply["retryable"]), ("error", "internal", True))


if __name__ == "__main__":
    unittest.main()
