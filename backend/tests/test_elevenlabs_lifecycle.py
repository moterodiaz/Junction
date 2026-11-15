"""#156 (REQ-VOICE-01, REQ-TTS-01, REQ-PRIV-03): the ElevenLabs voice is bounded, session-owned
and optional. Every failure leaves BASE (audio_url null, the phone's own voice) working."""

import asyncio
import os
import time
import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from app.main import app
from stt import speak
from stt.elevenlabs import ElevenLabsSpeechClient
from tests.test_speak import SpeakBase

BASE = "https://metalab.example"
KEY = "xi-KEY-do-not-log-156"
VOICE = "voice-156"
PCM = b"\x01\x00\x02\x00" * 600


class ElevenLabsLifecycleBase(SpeakBase):
    """ElevenLabs configured, no Gemini key: an ElevenLabs failure goes straight to BASE."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"ELEVEN_LABS_API_KEY": KEY, "ELEVEN_LABS_VOICE_ID": VOICE,
                                           "MODEL_TTS_ELEVENLABS": ""})
        env.start()
        self.addCleanup(env.stop)
        speak.set_speech_client(None)
        speak._elevenlabs = None
        speak._gemini = None
        self.addCleanup(setattr, speak, "_elevenlabs", None)
        self.addCleanup(setattr, speak, "_gemini", None)
        self.requests: list[httpx.Request] = []

    def eleven(self, handler=None):
        async def ok(request):
            return httpx.Response(200, content=PCM)

        async def record(request):
            self.requests.append(request)
            return await (handler or ok)(request)

        client = speak._elevenlabs_client()
        client._transport = httpx.MockTransport(record)
        return client

    def wait_for(self, n):
        """Block a handler until n requests are in flight, so tests act mid-synthesis."""
        async def until():
            while len(self.requests) < n:
                await asyncio.sleep(0.005)
        return until()


class MissingKeyTest(ElevenLabsLifecycleBase):
    def test_missing_key_or_voice_makes_no_request_and_speaks_with_the_phone(self):
        self.eleven()
        for name in ("ELEVEN_LABS_API_KEY", "ELEVEN_LABS_VOICE_ID"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: ""}):
                self.assertIsNone(speak._elevenlabs_client())
                self.assertIsNone(asyncio.run(speak.speak("hello", "s1")))
        self.assertEqual(self.requests, [])
        self.assertEqual(len(speak._clips), 0)


class TimeoutTest(ElevenLabsLifecycleBase):
    def test_a_hanging_request_is_cut_at_the_deadline_and_leaves_nothing(self):
        never = asyncio.Event()

        async def hang(request):
            await never.wait()

        self.eleven(hang)
        with mock.patch.object(speak, "TTS_TIMEOUT_S", 0.2), \
                self.assertLogs("metalab.speak", level="INFO") as captured:
            start = time.monotonic()
            self.assertIsNone(asyncio.run(speak.speak("hello", "s1")))
            self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(len(self.requests), 1)
        self.assertIn("TimeoutError", " ".join(captured.output))
        self.assertEqual(len(speak._clips), 0)
        self.assertNotIn("s1", speak._epochs_inflight)


class BadAnswerTest(ElevenLabsLifecycleBase):
    def test_bad_answers_give_null_audio_and_never_log_key_or_text(self):
        secret = "words only the reader said"
        answers = {
            "empty audio": httpx.Response(200, content=b""),
            "non-json error": httpx.Response(502, content=b"<html>bad gateway</html>"),
            "json list error": httpx.Response(500, json=["unexpected", KEY]),
            "echoing error": httpx.Response(400, json={"detail": {"status": "bad", "message": f"{KEY} {secret}"}}),
        }
        for label, response in answers.items():
            with self.subTest(label=label):
                async def answer(request, response=response):
                    return response

                self.eleven(answer)
                with self.assertLogs("metalab.speak", level="DEBUG") as captured:
                    self.assertIsNone(asyncio.run(speak.speak(secret, "s1")))
                out = " ".join(captured.output)
                self.assertIn("ElevenLabsError", out)
                self.assertNotIn(KEY, out)
                self.assertNotIn(secret, out)
        self.assertEqual(len(speak._clips), 0)

    def test_a_failing_voice_still_gives_a_base_card(self):
        async def down(request):
            return httpx.Response(503, json={"detail": "busy"})

        self.eleven(down)
        reply = self.card()
        self.assertEqual(reply["type"], "card")
        self.assertIsNone(reply["audio_url"])
        self.assertTrue(reply["speech_text"])
        self.assertEqual(len(self.requests), 1)


class CancellationTest(ElevenLabsLifecycleBase):
    def test_cancelling_mid_request_stores_nothing_and_the_session_can_speak_again(self):
        release = asyncio.Event()

        async def slow(request):
            await release.wait()
            return httpx.Response(200, content=PCM)

        self.eleven(slow)

        async def go():
            task = asyncio.create_task(speak.speak("hello", "s1"))
            await self.wait_for(1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            release.set()

        asyncio.run(go())
        self.assertEqual(len(speak._clips), 0)
        self.assertNotIn("s1", speak._epochs_inflight)
        release.set()
        self.assertIsNotNone(asyncio.run(speak.speak("again", "s1")))


class SessionIsolationTest(ElevenLabsLifecycleBase):
    def test_ending_one_session_mid_synthesis_keeps_the_other_sessions_voice(self):
        release = asyncio.Event()

        async def slow(request):
            await release.wait()
            return httpx.Response(200, content=PCM)

        self.eleven(slow)

        async def go():
            a = asyncio.create_task(speak.speak("for A", "A"))
            b = asyncio.create_task(speak.speak("for B", "B"))
            await self.wait_for(2)
            speak.cleanup_session("A")
            release.set()
            return await a, await b

        url_a, url_b = asyncio.run(go())
        self.assertIsNone(url_a)
        self.assertIsNotNone(url_b)
        self.assertEqual([sid for sid, _, _ in speak._clips.values()], ["B"])
        self.assertEqual(speak.cleanup_session("A"), 0)
        self.assertEqual(speak.cleanup_session("B"), 1)


class CleanupTest(ElevenLabsLifecycleBase):
    def clip_id(self, url):
        return url.rsplit("/", 1)[-1].removesuffix(".wav")

    def test_session_end_deletes_its_elevenlabs_audio(self):
        self.eleven()
        url = asyncio.run(speak.speak("hello", "s1"))
        self.assertIsInstance(speak.client_for(url), ElevenLabsSpeechClient)
        path = url.removeprefix(BASE)
        self.assertEqual(TestClient(app).get(path).status_code, 200)
        self.assertEqual(speak.cleanup_session("s1"), 1)
        self.assertEqual(TestClient(app).get(path).status_code, 404)

    def test_elevenlabs_audio_expires_after_the_bounded_ttl(self):
        self.eleven()
        now = [1000.0]
        with mock.patch.object(speak, "clock", lambda: now[0]):
            clip = self.clip_id(asyncio.run(speak.speak("hello", "s1")))
            now[0] += speak.CLIP_TTL_S - 1
            self.assertIsNotNone(speak.get(clip))
            now[0] += 2
            self.assertIsNone(speak.get(clip))
        self.assertEqual(len(speak._clips), 0)


if __name__ == "__main__":
    unittest.main()
