"""#95: the phone always gets model_timeout before its own deadlines (PRD sections 6, 9)."""

import asyncio
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import pipeline
from app.main import app

# ios/MetaLabCore/Sources/MetaLabCore/Deadline.swift
PHONE_IDLE_S = 30
PHONE_OVERALL_S = 90
FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}


class DefaultsTest(unittest.TestCase):
    def test_defaults_sit_inside_the_phone_deadlines(self):
        # A clean process, so neither the shell's env nor other tests' patches leak in.
        env = {k: v for k, v in os.environ.items() if k not in ("STAGE_TIMEOUT_S", "REQUEST_TIMEOUT_S")}
        out = subprocess.run(
            [sys.executable, "-c", "from app import pipeline as p; print(p.STAGE_TIMEOUT_S, p.REQUEST_TIMEOUT_S)"],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=True)
        stage, request = map(float, out.stdout.split())
        self.assertLess(stage, PHONE_IDLE_S)
        self.assertLess(request, PHONE_OVERALL_S)


class RequestBudgetTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_request_over_the_overall_budget_is_model_timeout(self):
        async def slowish(*args, **kwargs):  # each stage is under its own limit...
            await asyncio.sleep(0.04)
            return {"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                    "book": {"title": "b", "author": "a", "location": "l"}}

        with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 1.0), \
                mock.patch.object(pipeline, "REQUEST_TIMEOUT_S", 0.06), \
                mock.patch.object(pipeline, "think", slowish), \
                mock.patch.object(pipeline, "draw", slowish):  # ...but together they are not
            with TestClient(app).websocket_connect("/ws") as ws:
                ws.send_json({"type": "invoke", "request_id": "r1", "session_id": "s1",
                              "frame": FRAME, "audio": None, "text": "explain"})
                while (reply := ws.receive_json())["type"] == "status":
                    pass
        self.assertEqual((reply["type"], reply["code"], reply["retryable"]), ("error", "model_timeout", True))


class EarlyCardBudgetTest(unittest.TestCase):
    """#261: the card waits only for speech, so a picture slower than the whole request budget
    no longer turns the reply into model_timeout; the lens loads it from the reserved URL."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": "dummy",
                                               "IMAGE_BASE_URL": "https://example.com"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_picture_slower_than_the_request_budget_still_gets_the_card(self):
        async def think(*args, **kwargs):
            return {"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                    "book": {"title": "b", "author": "a", "location": "l"}}

        async def slow_draw(image_prompt, session_id, image_id=None, **kwargs):
            await asyncio.sleep(2)
            return None

        with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 5.0), \
                mock.patch.object(pipeline, "REQUEST_TIMEOUT_S", 0.5), \
                mock.patch.object(pipeline, "_is_dynamic_routing_active", return_value=False), \
                mock.patch.object(pipeline, "think", think), \
                mock.patch.object(pipeline, "speak", mock.AsyncMock(return_value=None)), \
                mock.patch.object(pipeline, "draw", slow_draw):
            with TestClient(app).websocket_connect("/ws") as ws:
                ws.send_json({"type": "invoke", "request_id": "r2", "session_id": "s2",
                              "frame": FRAME, "audio": None, "text": "draw this"})
                while (reply := ws.receive_json())["type"] == "status":
                    pass
        self.assertEqual(reply["type"], "card", reply)
        self.assertRegex(reply["image_url"], r"^https://example\.com/img/[0-9a-f]{16}\.png$")


if __name__ == "__main__":
    unittest.main()
