"""#91: the spoken answer as a WAV at card.audio_url, or null so the phone uses its own voice."""

import asyncio
import io
import json
import os
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import stt
from app import pipeline
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


class SpeakBase(unittest.TestCase):
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


class SpeakTest(SpeakBase):
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


class SessionClipsTest(SpeakBase):
    """#109: clips belong to the session that asked, and never outlive it (PRD section 6)."""

    def test_ending_a_session_deletes_only_its_clips(self):
        a1, a2, b1 = speak.store(b"a1", "A"), speak.store(b"a2", "A"), speak.store(b"b1", "B")
        self.assertEqual(speak.cleanup_session("A"), 2)
        self.assertIsNone(speak.get(a1))
        self.assertIsNone(speak.get(a2))
        self.assertEqual(speak.get(b1), b"b1")
        self.assertEqual(TestClient(app).get(f"/audio/{a1}.wav").status_code, 404)
        self.assertEqual(speak.cleanup_session("A"), 0)

    def test_a_request_clip_is_filed_under_its_session(self):
        speak.set_speech_client(StubSpeech())
        url = self.card()["audio_url"]
        self.assertEqual(speak.cleanup_session("s1"), 1)
        self.assertEqual(TestClient(app).get(url.removeprefix(BASE)).status_code, 404)

    def test_clips_expire(self):
        with mock.patch.object(speak, "clock", lambda: 1000.0):
            clip = speak.store(b"old", "A")
        with mock.patch.object(speak, "clock", lambda: 1000.0 + speak.CLIP_TTL_S + 1):
            self.assertIsNone(speak.get(clip))
            self.assertEqual(speak.cleanup_session("A"), 0)

    def test_a_failed_request_leaves_no_clip_behind(self):
        speak.set_speech_client(StubSpeech())

        async def broken_draw(*args, **kwargs):
            await asyncio.sleep(0.05)  # speech finishes and stores its clip first
            raise RuntimeError("draw broke")

        stored = []
        real_store = speak.store
        with mock.patch.object(pipeline, "draw", broken_draw), \
                mock.patch.object(speak, "store", lambda *a: stored.append(real_store(*a)) or stored[-1]):
            self.assertEqual(self.card()["type"], "error")
        self.assertEqual(len(stored), 1)  # a clip was made...
        self.assertIsNone(speak.get(stored[0]))  # ...and deleted with the failed request


class ClipLifetimeTest(SpeakBase):
    """Greptile on #171: expiry without audio traffic, and no clip from speech that outlives its session."""

    def test_expired_clips_go_without_any_more_audio_requests(self):
        now = [1000.0]
        with mock.patch.object(speak, "clock", lambda: now[0]):
            speak.store(b"old", "A")  # starts the sweeper thread if it is not running yet
            now[0] += speak.CLIP_TTL_S + 1
            speak._sweep_now.set()  # what SWEEP_EVERY_S does on its own, without waiting a minute
            deadline = time.monotonic() + 2
            while speak._clips and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(len(speak._clips), 0)  # read directly: get() would expire it itself

    def test_speech_finishing_after_its_session_ended_is_dropped(self):
        release = asyncio.Event()

        class SlowSpeech:
            async def synthesize(self, text):
                await release.wait()
                return b"\x01\x00" * 8

        speak.set_speech_client(SlowSpeech())

        async def go():
            speaking = asyncio.create_task(speak.speak("hi", "A"))
            await asyncio.sleep(0.01)
            speak.cleanup_session("A")  # the session ends while speech is still being made
            release.set()
            return await speaking

        self.assertIsNone(asyncio.run(go()))
        self.assertEqual(len(speak._clips), 0)


class GeminiResponseTest(unittest.TestCase):
    """The real client: audio part found among others, rate read from its mime type, one Client."""

    def test_audio_part_and_rate_and_one_client(self):
        made = []

        class FakeModels:
            async def generate_content(self, **kwargs):
                text = SimpleNamespace(inline_data=None, text="hi")
                audio = SimpleNamespace(inline_data=SimpleNamespace(
                    data=b"\x01\x00" * 8, mime_type="audio/L16;codec=pcm;rate=16000"))
                return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[text, audio]))])

        def fake_client(api_key):
            made.append(api_key)
            return SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))

        client = speak.GeminiSpeechClient("key", "tts-model")
        with mock.patch("google.genai.Client", fake_client):
            pcm, rate = asyncio.run(client.synthesize("one"))
            asyncio.run(client.synthesize("two"))
        self.assertEqual((pcm, rate), (b"\x01\x00" * 8, 16000))
        self.assertEqual(made, ["key"])
        with wave.open(io.BytesIO(speak.to_wav(pcm, rate))) as wav:
            self.assertEqual(wav.getframerate(), 16000)


if __name__ == "__main__":
    unittest.main()
