"""Canned Macbeth demo path (DEMO_CANNED=on): one fixed card, no model calls."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app import demo, pipeline
from app.main import app

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "ws-messages.schema.json").read_text()))
FRAME = {"mime": "image/jpeg", "b64": "AAAA"}
AUDIO = {"mime": "audio/wav", "b64": "AAAA"}
BASE = "https://demo.example.modal.run"


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain this"}
    msg.update(overrides)
    return msg


def exchange(message, expect):
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json(message)
        return [ws.receive_json() for _ in range(expect)]


class DemoTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {
            "DEMO_CANNED": "on", "DEMO_DELAY_S": "0", "IMAGE_BASE_URL": BASE,
            "NVIDIA_API_KEY": "", "GEMINI_API_KEY": "",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        # The canned path must never reach the real pipeline.
        real = mock.patch.object(pipeline, "run", side_effect=AssertionError("the real pipeline ran"))
        real.start()
        self.addCleanup(real.stop)

    def test_off_unless_asked_for(self):
        for value in ("", "off", "0", "false", "no"):
            with mock.patch.dict(os.environ, {"DEMO_CANNED": value}):
                self.assertFalse(demo.enabled(), value)
        for value in ("on", "1", "true", "yes", " ON "):
            with mock.patch.dict(os.environ, {"DEMO_CANNED": value}):
                self.assertTrue(demo.enabled(), value)
        with mock.patch.dict(os.environ):
            os.environ.pop("DEMO_CANNED")
            self.assertFalse(demo.enabled())

    def test_text_invoke_streams_stages_then_the_dagger_card(self):
        replies = exchange(invoke(), 4)
        self.assertEqual([r["stage"] for r in replies[:3]], ["reading", "thinking", "drawing"])
        card = replies[3]
        self.assertEqual(card["type"], "card")
        self.assertEqual(card["request_id"], "r1")
        self.assertEqual(card["book"], {"title": "Macbeth", "author": "William Shakespeare",
                                        "location": "Act 2, Scene 1"})
        self.assertIn("dagger", card["caption"].lower())
        for reply in replies:
            self.assertEqual(list(SCHEMA.iter_errors(reply)), [], reply)

    def test_audio_invoke_starts_with_transcribing(self):
        replies = exchange(invoke(audio=AUDIO, text=None), 5)
        self.assertEqual([r["stage"] for r in replies[:4]],
                         ["transcribing", "reading", "thinking", "drawing"])
        self.assertEqual(replies[4]["type"], "card")

    def test_card_says_it_is_canned(self):
        card = exchange(invoke(), 4)[3]
        self.assertEqual(card["models"], {"read": "demo-canned", "reason": "demo-canned",
                                          "image": "demo-canned"})

    def test_image_is_served_from_this_backend(self):
        card = exchange(invoke(), 4)[3]
        self.assertEqual(card["image_url"], f"{BASE}/demo/macbeth_dagger.png")
        response = TestClient(app).get("/demo/macbeth_dagger.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_without_a_public_url_the_card_has_no_image(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("IMAGE_BASE_URL")
            card = demo.card("r1")
        self.assertIsNone(card.image_url)
        self.assertIsNone(card.audio_url)

    def test_audio_is_offered_only_when_a_clip_is_dropped_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "macbeth_dagger.png").write_bytes(b"\x89PNG")
            with mock.patch.object(demo, "ASSET_DIR", Path(tmp)):
                self.assertIsNone(demo.card("r1").audio_url)
                (Path(tmp) / "macbeth_dagger.wav").write_bytes(b"RIFF")
                self.assertEqual(demo.card("r1").audio_url, f"{BASE}/demo/macbeth_dagger.wav")
                self.assertEqual(TestClient(app).get("/demo/macbeth_dagger.wav").status_code, 200)

    def test_only_known_assets_are_served(self):
        client = TestClient(app)
        for name in ("secret.png", "demo.py", "..%2Fdemo.py", "macbeth_quotes.json"):
            self.assertEqual(client.get(f"/demo/{name}").status_code, 404, name)

    def test_delay_is_spread_over_the_stages(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with mock.patch.dict(os.environ, {"DEMO_DELAY_S": "3"}), \
                mock.patch.object(demo.asyncio, "sleep", fake_sleep):
            exchange(invoke(), 4)
        self.assertEqual(sleeps, [1.0, 1.0, 1.0])

    def test_a_bad_delay_falls_back_to_the_default(self):
        for value in ("abc", "-1", "nan", "inf", "999"):
            with mock.patch.dict(os.environ, {"DEMO_DELAY_S": value}):
                self.assertEqual(demo.delay_s(), demo.DEFAULT_DELAY_S, value)
        with mock.patch.dict(os.environ, {"DEMO_DELAY_S": "0.5"}):
            self.assertEqual(demo.delay_s(), 0.5)


class DemoOffTest(unittest.TestCase):
    def test_the_real_pipeline_runs_when_the_flag_is_off(self):
        with mock.patch.dict(os.environ, {"DEMO_CANNED": "off", "NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""}):
            card = exchange(invoke(), 4)[3]
        self.assertEqual(card["book"]["title"], "Hamlet")
        self.assertNotEqual(card["models"]["read"], "demo-canned")


if __name__ == "__main__":
    unittest.main()
