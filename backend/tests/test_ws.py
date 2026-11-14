import asyncio
import json
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from ai.page_reader import DEFAULT_MODEL_READ, NoTextFoundError, PageReadTimeoutError, StubNemotronClient
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
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_real_page_reader_text_reaches_card(self):
        reader = StubNemotronClient(default_response="Text read by Nemotron")

        async def think_with_page_text(command, page_text, session_id):
            return {
                "title": "Read page",
                "caption": page_text,
                "speech_text": page_text,
                "image_prompt": "page",
                "book": {"title": "Book", "author": "Author", "location": "Page"},
            }

        with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}), \
                mock.patch("ai.page_reader.NemotronClient", return_value=reader), \
                mock.patch.object(pipeline, "think", side_effect=think_with_page_text):
            replies = exchange(invoke(), 4)
        self.assertEqual(replies[3]["caption"], "Text read by Nemotron")
        self.assertEqual(len(reader.calls), 1)

    def test_models_read_is_stub_on_offline_path(self):
        # setUp already clears NVIDIA_API_KEY
        replies = exchange(invoke(), 4)
        self.assertEqual(replies[3]["models"]["read"], "stub")

    def test_models_read_is_model_name_on_real_reader_path(self):
        reader = StubNemotronClient(default_response="some text")
        with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key", "MODEL_READ": DEFAULT_MODEL_READ}), \
                mock.patch("ai.page_reader.NemotronClient", return_value=reader):
            replies = exchange(invoke(), 4)
        self.assertEqual(replies[3]["models"]["read"], DEFAULT_MODEL_READ)

    def test_no_text_error_keeps_socket_open(self):
        with mock.patch.object(pipeline, "read_page", side_effect=[NoTextFoundError(), "page text"]):
            with TestClient(app).websocket_connect("/ws") as ws:
                ws.send_json(invoke())
                self.assertEqual(ws.receive_json()["stage"], "reading")
                error = ws.receive_json()
                self.assertEqual(error["code"], "no_text_found")
                self.assertTrue(error["retryable"])

                ws.send_json(invoke(request_id="r2"))
                replies = [ws.receive_json() for _ in range(4)]
        self.assertEqual(replies[3]["type"], "card")
        self.assertEqual(replies[3]["request_id"], "r2")

    def test_page_reader_timeout_returns_model_timeout(self):
        with mock.patch.object(pipeline, "read_page", side_effect=PageReadTimeoutError()):
            replies = exchange(invoke(), 2)
        self.assertEqual(replies[1]["type"], "error")
        self.assertEqual(replies[1]["code"], "model_timeout")
        self.assertTrue(replies[1]["retryable"])

    def test_health(self):
        self.assertEqual(TestClient(app).get("/health").json(), {"ok": True})

    def test_image_route_is_mounted(self):
        from ai.image import store_image

        store_image("mounted", b"image-data", session_id="s1")
        response = TestClient(app).get("/img/mounted.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"image-data")

    def test_pipeline_draw_uses_generator_and_session_when_configured(self):
        generator = mock.AsyncMock(return_value="https://x/img/1.png")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}), mock.patch.object(
            pipeline.image, "draw", new=generator
        ) as generate:
            result = asyncio.run(pipeline.draw("prompt", "session-7"))
        self.assertEqual(result, "https://x/img/1.png")
        generate.assert_awaited_once_with("prompt", session_id="session-7")

    def test_pipeline_draw_returns_none_without_key_or_on_failure(self):
        generate = mock.AsyncMock(side_effect=RuntimeError("unavailable"))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            pipeline.image, "draw", new=generate
        ):
            self.assertIsNone(asyncio.run(pipeline.draw("prompt", "session")))
        generate.assert_not_awaited()

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}), mock.patch.object(
            pipeline.image, "draw", new=generate
        ):
            self.assertIsNone(asyncio.run(pipeline.draw("prompt", "session")))


if __name__ == "__main__":
    unittest.main()
