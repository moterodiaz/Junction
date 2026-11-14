"""#112: every card validates against the contract, whatever odd fields a model returns."""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import stt
from app import pipeline
from app.main import app

SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "ws-messages.schema.json").read_text()))
FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}


def card_for(answer):
    async def think(*args, **kwargs):
        return answer

    async def draw(*args, **kwargs):
        return None

    with mock.patch.object(pipeline, "think", think), mock.patch.object(pipeline, "draw", draw), \
            TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json({"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
                      "audio": None, "text": "explain"})
        while (reply := ws.receive_json())["type"] == "status":
            pass
    return reply


class CardTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": "", "IMAGE_BASE_URL": ""})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "explain"))

    def assert_valid_card(self, reply):
        self.assertEqual(reply["type"], "card", reply)
        self.assertEqual([e.message for e in SCHEMA.iter_errors(reply)], [])

    def test_empty_and_missing_text_get_safe_defaults(self):
        reply = card_for({"title": "", "caption": "   ", "speech_text": "He wonders whether to live.",
                          "image_prompt": "p", "book": {"title": "Hamlet", "author": "", "location": None}})
        self.assert_valid_card(reply)
        self.assertEqual(reply["caption"], "He wonders whether to live.")  # falls back to the spoken text
        self.assertEqual(reply["book"]["title"], "Hamlet")  # real values are kept
        self.assertTrue(reply["title"] and reply["book"]["author"] and reply["book"]["location"])

    def test_only_valid_https_sources_survive(self):
        good = {"title": "Hamlet, public-domain text", "url": "https://www.gutenberg.org/ebooks/1524"}
        reply = card_for({"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                          "book": {"title": "Hamlet", "author": "Shakespeare", "location": "Act 3"},
                          "sources": [good, {"title": "x", "url": "https://"}, {"title": "y", "url": "https://exa mple.com"},
                                      {"title": "z", "url": "http://insecure.example"}, "not a dict",
                                      {"title": "", "url": "https://untitled.example/a"}]})
        self.assert_valid_card(reply)
        self.assertEqual(reply["sources"][0], good)
        self.assertEqual(len(reply["sources"]), 2)  # the untitled one keeps its URL with a default title
        self.assertTrue(reply["sources"][1]["title"])

    def test_a_url_with_a_trailing_newline_is_dropped_not_fatal(self):
        # Python's $ matches before a final newline; the schema (and pydantic's regex) do not.
        reply = card_for({"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                          "book": {"title": "b", "author": "a", "location": "l"},
                          "sources": [{"title": "n", "url": "https://example.com\n"}]})
        self.assert_valid_card(reply)
        self.assertEqual(reply["sources"], [])

    def test_model_ids_are_reported_as_they_are(self):
        reply = card_for({"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
                          "book": {"title": "b", "author": "a", "location": "l"}})
        self.assert_valid_card(reply)
        self.assertEqual(reply["models"], {"read": "stub", "reason": "stub", "image": "stub"})


if __name__ == "__main__":
    unittest.main()
