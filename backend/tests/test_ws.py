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


def exchange_bytes(payload, expect):
    """Send one binary frame, return the next `expect` replies."""
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_bytes(payload)
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

    def test_binary_frame_invoke_streams_stages_then_card(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_bytes(json.dumps(invoke()).encode())
            replies = [ws.receive_json() for _ in range(4)]
        self.assertEqual([r.get("stage") for r in replies[:3]], ["reading", "thinking", "drawing"])
        self.assertTrue(all(r["type"] == "status" and r["request_id"] == "r1" for r in replies[:3]))
        self.assertEqual(replies[3]["type"], "card")
        self.assertEqual(replies[3]["request_id"], "r1")

    def test_non_utf8_binary_is_rejected_without_closing(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_bytes(b"\xff\xfe\x00{")
            reply = ws.receive_json()
            self.assertEqual(reply["type"], "error")
            self.assertEqual(reply["code"], "internal")
            self.assertFalse(reply["retryable"])
            ws.send_bytes(json.dumps(invoke()).encode())
            self.assertEqual(ws.receive_json()["type"], "status")

    def test_utf16_binary_is_rejected(self):
        # json.loads would sniff UTF-16 from bytes; the contract is UTF-8 only.
        [reply] = exchange_bytes(json.dumps(invoke()).encode("utf-16"), 1)
        self.assertEqual(reply["type"], "error")

    def test_deeply_nested_json_is_rejected_without_closing(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_text("[" * 100000)
            reply = ws.receive_json()
            self.assertEqual(reply["type"], "error")
            self.assertFalse(reply["retryable"])
            ws.send_json(invoke())
            self.assertEqual(ws.receive_json()["type"], "status")

    def test_invalid_invoke_error_does_not_echo_input(self):
        secret = "SECRET-USER-TEXT"
        msg = invoke(text=secret, audio={"mime": "audio/wav", "b64": "SECRETAUDIO"},
                     frame={"mime": "image/jpeg", "b64": 12345})
        with self.assertLogs("metalab", level="INFO") as logs:
            [reply] = exchange(msg, 1)
        self.assertEqual(reply["type"], "error")
        self.assertEqual(reply["message"], "Invalid request.")
        self.assertNotIn(secret, json.dumps(reply))
        logged = "\n".join(logs.output)
        for fragment in (secret, "SECRETAUDIO", "12345"):
            self.assertNotIn(fragment, logged)

    def test_non_json_error_does_not_echo_input(self):
        [reply] = exchange("SECRET-NOT-JSON", 1)
        self.assertEqual(reply["message"], "Invalid request.")

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

    def test_empty_request_id_is_not_echoed(self):
        [reply] = exchange(invoke(request_id="", frame=None), 1)
        self.assertEqual(reply["type"], "error")
        self.assertIsNone(reply["request_id"])

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
