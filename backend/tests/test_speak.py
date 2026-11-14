"""#91: the spoken answer as a WAV at card.audio_url, or null so the phone uses its own voice."""

import io
import json
import os
import unittest
import wave
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import stt
from app.main import app
from stt import speak

SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "ws-messages.schema.json").read_text()))
FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
BASE = "https://metalab.example"


class StubSpeech:
    def __init__(self, pcm=b"\x01\x00" * 2400, error=None):
        self.pcm, self.error, self.texts = pcm, error, []

    async def synthesize(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        return self.pcm


class SpeakTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": "", "IMAGE_BASE_URL": BASE})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "explain"))
        self.addCleanup(speak.set_speech_client, None)
        self.addCleanup(speak.clear)

    def card(self):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json({"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
                          "audio": None, "text": "explain"})
            while True:
                reply = ws.receive_json()
                if reply["type"] in ("card", "error"):
                    self.assertEqual([e.message for e in SCHEMA.iter_errors(reply)], [])
                    return reply

    def test_speech_is_served_as_wav_at_audio_url(self):
        client = StubSpeech()
        speak.set_speech_client(client)
        card = self.card()
        self.assertEqual(client.texts, [card["speech_text"]])
        self.assertTrue(card["audio_url"].startswith(BASE + "/audio/"))
        response = TestClient(app).get(card["audio_url"].removeprefix(BASE))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        with wave.open(io.BytesIO(response.content)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
            self.assertEqual(wav.readframes(wav.getnframes()), client.pcm)

    def test_tts_failure_still_gives_a_card_with_null_audio(self):
        speak.set_speech_client(StubSpeech(error=RuntimeError("quota")))
        card = self.card()
        self.assertEqual(card["type"], "card")
        self.assertIsNone(card["audio_url"])

    def test_no_gemini_key_means_no_tts_call(self):
        card = self.card()
        self.assertIsNone(card["audio_url"])

    def test_no_public_https_base_means_null_audio(self):
        speak.set_speech_client(StubSpeech())
        with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": ""}):
            self.assertIsNone(self.card()["audio_url"])

    def test_unknown_clip_is_404(self):
        self.assertEqual(TestClient(app).get("/audio/nope.wav").status_code, 404)

    def test_only_recent_clips_are_kept(self):
        ids = [speak.store(b"\x00\x00") for _ in range(speak.MAX_CLIPS + 5)]
        self.assertIsNone(speak.get(ids[0]))
        self.assertIsNotNone(speak.get(ids[-1]))


if __name__ == "__main__":
    unittest.main()
