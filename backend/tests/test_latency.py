"""#33: one latency summary line per request, with the time spent in each stage (PRD section 9)."""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import stt
from app import latency
from app.main import app

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
AUDIO = {"mime": "audio/wav", "b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="}


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


class StageTimerTest(unittest.TestCase):
    def test_each_stage_lasts_until_the_next_one_starts(self):
        ticks = iter([10.0, 10.0, 11.5, 14.0])
        with mock.patch.object(latency, "clock", lambda: next(ticks)):
            timer = latency.StageTimer("r1")
            timer.start("reading")
            timer.start("thinking")
            self.assertEqual(timer.finish(), {"reading": 1.5, "thinking": 2.5, "total": 4.0})


class LatencyLogTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "draw this"))

    def summary_for(self, message):
        with self.assertLogs("metalab.latency", level="INFO") as logs:
            with TestClient(app).websocket_connect("/ws") as ws:
                ws.send_json(message)
                while ws.receive_json()["type"] not in ("card", "error"):
                    pass
        self.assertEqual(len(logs.output), 1, logs.output)
        return logs.output[0]

    def test_spoken_request_logs_all_four_stages(self):
        line = self.summary_for(invoke(text=None, audio=AUDIO))
        for part in ("request=r1", "outcome=card", "transcribing=", "reading=", "thinking=",
                     "drawing=", "total="):
            self.assertIn(part, line)

    def test_typed_request_has_no_transcribing_stage(self):
        line = self.summary_for(invoke())
        self.assertIn("reading=", line)
        self.assertNotIn("transcribing=", line)

    def test_failed_request_still_logs_the_stages_it_reached(self):
        stt.set_engine(lambda audio: "what time is it")
        line = self.summary_for(invoke(text=None, audio=AUDIO))
        self.assertIn("outcome=error", line)
        self.assertIn("transcribing=", line)
        self.assertNotIn("reading=", line)


if __name__ == "__main__":
    unittest.main()
