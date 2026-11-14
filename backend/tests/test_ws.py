import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import stt
from app import pipeline
from app.main import app

FRAME = {"mime": "image/jpeg", "b64": "AAAA"}


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


def exchange(message, expect):
    """Send one message, return the next `expect` replies."""
    with TestClient(app).websocket_connect("/ws") as ws:
        if isinstance(message, str):
            ws.send_text(message)
        else:
            ws.send_json(message)
        return [ws.receive_json() for _ in range(expect)]


class WsTest(unittest.TestCase):
    def test_text_command_streams_stages_then_card(self):
        replies = exchange(invoke(), 4)
        self.assertEqual([r["stage"] for r in replies[:3]], ["reading", "thinking", "drawing"])
        self.assertTrue(all(r["type"] == "status" and r["request_id"] == "r1" for r in replies[:3]))
        card = replies[3]
        self.assertEqual(card["type"], "card")
        self.assertEqual(card["request_id"], "r1")
        self.assertEqual(card["book"]["title"], "Hamlet")
        self.assertIsNone(card["audio_url"])

    def test_binary_frame_invoke_is_accepted(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_bytes(json.dumps(invoke()).encode())
            replies = [ws.receive_json() for _ in range(4)]
        self.assertEqual(replies[3]["type"], "card")

    def test_audio_command_adds_transcribing_stage(self):
        stt.set_engine(lambda audio: "explain")
        self.addCleanup(stt.set_engine, None)
        replies = exchange(invoke(text=None, audio={"mime": "audio/wav", "b64": "AAAA"}), 5)
        self.assertEqual([r.get("stage") for r in replies[:4]],
                         ["transcribing", "reading", "thinking", "drawing"])
        self.assertEqual(replies[4]["type"], "card")

    def test_audio_and_text_together_is_rejected(self):
        [reply] = exchange(invoke(audio={"mime": "audio/wav", "b64": "AAAA"}), 1)
        self.assertEqual(reply["type"], "error")
        self.assertEqual(reply["request_id"], "r1")
        self.assertFalse(reply["retryable"])

    def test_missing_frame_is_rejected(self):
        msg = invoke()
        del msg["frame"]
        [reply] = exchange(msg, 1)
        self.assertEqual(reply["type"], "error")

    def test_non_json_is_rejected_without_closing(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_text("not json")
            self.assertEqual(ws.receive_json()["type"], "error")
            ws.send_json(invoke())
            self.assertEqual(ws.receive_json()["type"], "status")

    def test_non_string_request_id_is_rejected_without_closing(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json(invoke(request_id={}))
            reply = ws.receive_json()
            self.assertEqual(reply["type"], "error")
            self.assertIsNone(reply["request_id"])
            ws.send_json(invoke())
            self.assertEqual(ws.receive_json()["type"], "status")

    def test_stage_failure_returns_retryable_error(self):
        with mock.patch.object(pipeline, "read_page", side_effect=RuntimeError("boom")):
            replies = exchange(invoke(), 2)
        self.assertEqual(replies[1]["type"], "error")
        self.assertEqual(replies[1]["code"], "internal")
        self.assertTrue(replies[1]["retryable"])
        self.assertNotIn("boom", json.dumps(replies[1]))

    def test_health(self):
        self.assertEqual(TestClient(app).get("/health").json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
