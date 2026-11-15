"""#226: ElevenLabs speaks the answer; on failure Gemini tries once, then the phone's own voice."""

import asyncio
import io
import json
import os
import time
import unittest
import wave
from unittest import mock

import httpx

from app.config import Settings, load_settings
from stt import elevenlabs, speak
from stt.elevenlabs import DEFAULT_MODEL_TTS_ELEVENLABS, ElevenLabsError, ElevenLabsSpeechClient

BASE = "https://metalab.example"
KEY = "xi-KEY-do-not-log-9876"
VOICE = "voice-abc123"
PCM = b"\x01\x00\x02\x00" * 1200
SECRET_TEXT = "the private words the reader asked about"


def transport(status=200, content=PCM, body=None, seen=None, delay=0.0, wait=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if delay:
            await asyncio.sleep(delay)
        if wait is not None:
            await wait.wait()
        if body is not None:
            return httpx.Response(status, json=body)
        return httpx.Response(status, content=content)
    return httpx.MockTransport(handler)


class FakeGemini:
    model = _configured_model = "gemini-fallback-tts"
    api_key = "GEMINI-KEY-do-not-log"

    def __init__(self, error=None, delay=0.0):
        self.error, self.delay, self.texts = error, delay, []

    async def synthesize(self, text):
        self.texts.append(text)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return b"\x05\x00" * 10, 24000


class ClientTest(unittest.TestCase):
    def test_request_url_header_and_body(self):
        seen = []
        client = ElevenLabsSpeechClient(KEY, VOICE, transport=transport(seen=seen))
        pcm, rate = asyncio.run(client.synthesize("Hello there"))
        self.assertEqual((pcm, rate), (PCM, 24000))
        (req,) = seen
        self.assertEqual(req.method, "POST")
        self.assertEqual(str(req.url), f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=pcm_24000")
        self.assertEqual(req.headers["xi-api-key"], KEY)
        self.assertEqual(json.loads(req.content), {"text": "Hello there", "model_id": "eleven_flash_v2_5"})

    def test_model_override_from_env(self):
        seen = []
        with mock.patch.dict(os.environ, {"MODEL_TTS_ELEVENLABS": "eleven_multilingual_v2"}):
            client = ElevenLabsSpeechClient(KEY, VOICE, transport=transport(seen=seen))
        asyncio.run(client.synthesize("hi"))
        self.assertEqual(json.loads(seen[0].content)["model_id"], "eleven_multilingual_v2")
        self.assertEqual(client.model, client._configured_model)

    def test_non_2xx_raises_with_status_code_and_short_reason(self):
        for code, status in ((401, "invalid_api_key"), (404, "voice_not_found"), (429, "quota_exceeded")):
            client = ElevenLabsSpeechClient(KEY, VOICE, transport=transport(
                code, body={"detail": {"status": status, "message": "x\n" * 300}}))
            with self.assertRaises(ElevenLabsError) as caught:
                asyncio.run(client.synthesize("hi"))
            self.assertEqual(caught.exception.status_code, code)
            self.assertEqual(caught.exception.status, status)
            self.assertLessEqual(len(caught.exception.message), 200)
            self.assertNotIn("\n", caught.exception.message)

    def test_non_json_error_body_still_raises(self):
        client = ElevenLabsSpeechClient(KEY, VOICE, transport=transport(500, content=b"<html>oops</html>"))
        with self.assertRaises(ElevenLabsError) as caught:
            asyncio.run(client.synthesize("hi"))
        self.assertEqual(caught.exception.status_code, 500)

    def test_empty_audio_raises(self):
        client = ElevenLabsSpeechClient(KEY, VOICE, transport=transport(content=b""))
        with self.assertRaises(ElevenLabsError):
            asyncio.run(client.synthesize("hi"))

    def test_repr_hides_the_key(self):
        self.assertNotIn(KEY, repr(ElevenLabsSpeechClient(KEY, VOICE)))


class SpeakWithElevenLabsTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"ELEVEN_LABS_API_KEY": KEY, "ELEVEN_LABS_VOICE_ID": VOICE,
                                           "GEMINI_API_KEY": "", "MODEL_TTS_ELEVENLABS": "",
                                           "IMAGE_BASE_URL": BASE})
        env.start()
        self.addCleanup(env.stop)
        speak.set_speech_client(None)
        speak._elevenlabs = None
        speak._gemini = None
        self.addCleanup(speak.set_speech_client, None)
        self.addCleanup(speak.clear)
        self.addCleanup(setattr, speak, "_elevenlabs", None)
        self.addCleanup(setattr, speak, "_gemini", None)

    def eleven(self, **kw):
        client = speak._elevenlabs_client()
        client._transport = transport(**kw)
        return client

    def gemini(self, fake):
        p = mock.patch.object(speak, "_gemini_client", lambda: fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def wav_of(self, url):
        self.assertTrue(url.startswith(BASE + "/audio/"))
        clip = speak.get(url.rsplit("/", 1)[-1].removesuffix(".wav"))
        with wave.open(io.BytesIO(clip)) as w:
            return w.getframerate(), w.readframes(w.getnframes())

    def test_elevenlabs_pcm_becomes_a_24khz_wav(self):
        self.eleven()
        rate, frames = self.wav_of(asyncio.run(speak.speak("hello", "s1")))
        self.assertEqual((rate, frames), (24000, PCM))

    def test_elevenlabs_is_chosen_before_gemini(self):
        fake = self.gemini(FakeGemini())
        self.eleven()
        asyncio.run(speak.speak("hello", "s1"))
        self.assertEqual(fake.texts, [])
        active = speak.active_speech_client()
        self.assertIsInstance(active, ElevenLabsSpeechClient)
        self.assertEqual(active.model, DEFAULT_MODEL_TTS_ELEVENLABS)

    def test_missing_key_or_voice_skips_elevenlabs(self):
        for name in ("ELEVEN_LABS_API_KEY", "ELEVEN_LABS_VOICE_ID"):
            with mock.patch.dict(os.environ, {name: "  "}):
                self.assertIsNone(speak._elevenlabs_client())
                fake = FakeGemini()
                with mock.patch.object(speak, "_gemini_client", lambda: fake):
                    self.assertIsNotNone(asyncio.run(speak.speak("hello", "s1")))
                self.assertEqual(fake.texts, ["hello"])

    def test_provider_errors_fall_back_to_gemini(self):
        for code in (401, 404, 429):
            with self.subTest(code=code):
                speak._elevenlabs = None
                fake = FakeGemini()
                with mock.patch.object(speak, "_gemini_client", lambda: fake):
                    self.eleven(status=code, body={"detail": {"status": "err", "message": "no"}})
                    with self.assertLogs("metalab.speak", level="INFO") as captured:
                        url = asyncio.run(speak.speak("hello", "s1"))
                    self.assertEqual(self.wav_of(url)[1], b"\x05\x00" * 10)
                    self.assertEqual(fake.texts, ["hello"])
                    self.assertIn(f"code={code}", " ".join(captured.output))
                    self.assertIs(speak.client_for(url), fake)

    def test_secret_straddling_200_chars_is_redacted_in_logs(self):
        message = "x" * 190 + KEY + " tail"
        err = elevenlabs._error_from(httpx.Response(401, json={"detail": {"message": message}}))
        out = speak.describe_failure(err, "", KEY)
        self.assertNotIn(KEY[:6], out)
        self.assertIn("[redacted]", out)

    def test_clip_keeps_its_own_provider(self):
        fake = self.gemini(FakeGemini())
        self.eleven(status=429, body={"detail": {"status": "q", "message": "no"}})
        url_a = asyncio.run(speak.speak("a", "s1"))
        self.eleven()
        speak._elevenlabs._transport = transport()
        url_b = asyncio.run(speak.speak("b", "s2"))
        self.assertIs(speak.client_for(url_a), fake)
        self.assertIsInstance(speak.client_for(url_b), ElevenLabsSpeechClient)

    def test_both_failing_returns_none(self):
        self.gemini(FakeGemini(error=RuntimeError("gemini down")))
        self.eleven(status=429, body={"detail": {"status": "quota_exceeded", "message": "quota"}})
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            self.assertIsNone(asyncio.run(speak.speak("hello", "s1")))
        out = " ".join(captured.output)
        self.assertIn("trying Gemini", out)
        self.assertIn("phone will use its own voice", out)

    def test_no_gemini_key_means_none_after_elevenlabs_fails(self):
        self.eleven(status=401, body={"detail": {"status": "invalid_api_key", "message": "bad"}})
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            self.assertIsNone(asyncio.run(speak.speak("hello", "s1")))
        self.assertIn("code=401", " ".join(captured.output))
        self.assertNotIn("trying Gemini", " ".join(captured.output))

    def test_timeout_stays_within_the_one_deadline(self):
        self.gemini(FakeGemini(delay=5))
        self.eleven(status=503, body={"detail": "busy"}, delay=0.15)
        with mock.patch.object(speak, "TTS_TIMEOUT_S", 0.3):
            start = time.monotonic()
            self.assertIsNone(asyncio.run(speak.speak("hello", "s1")))
            self.assertLess(time.monotonic() - start, 1.0)

    def test_empty_audio_falls_back(self):
        fake = self.gemini(FakeGemini())
        self.eleven(content=b"")
        self.assertIsNotNone(asyncio.run(speak.speak("hello", "s1")))
        self.assertEqual(fake.texts, ["hello"])

    def test_session_ending_mid_synthesis_drops_the_clip(self):
        release = asyncio.Event()
        self.eleven(wait=release)

        async def go():
            task = asyncio.create_task(speak.speak("hi", "A"))
            await asyncio.sleep(0.05)
            speak.cleanup_session("A")
            release.set()
            return await task

        self.assertIsNone(asyncio.run(go()))
        self.assertEqual(len(speak._clips), 0)

    def test_logs_never_hold_the_key_or_the_text(self):
        self.gemini(FakeGemini(error=RuntimeError(f"gemini echoed {SECRET_TEXT}")))
        self.eleven(status=401, body={"detail": {"status": "invalid_api_key",
                                                 "message": f"key {KEY} rejected for '{SECRET_TEXT}'"}})
        with self.assertLogs("metalab.speak", level="DEBUG") as captured:
            self.assertIsNone(asyncio.run(speak.speak(SECRET_TEXT, "s1")))
        out = " ".join(captured.output)
        self.assertNotIn(KEY, out)
        self.assertNotIn(SECRET_TEXT, out)
        self.assertIn("[redacted]", out)

    def test_client_is_reused_until_the_settings_change(self):
        first = speak._elevenlabs_client()
        self.assertIs(speak._elevenlabs_client(), first)
        with mock.patch.dict(os.environ, {"ELEVEN_LABS_VOICE_ID": "other"}):
            self.assertIsNot(speak._elevenlabs_client(), first)


class ConfigTest(unittest.TestCase):
    ENV = {"NVIDIA_API_KEY": "n", "GEMINI_API_KEY": "g"}

    def test_elevenlabs_settings_are_optional(self):
        s = load_settings(self.ENV)
        self.assertEqual((s.eleven_labs_api_key, s.eleven_labs_voice_id), ("", ""))
        self.assertEqual(s.model_tts_elevenlabs, DEFAULT_MODEL_TTS_ELEVENLABS)

    def test_elevenlabs_key_is_read_but_never_echoed(self):
        s = load_settings({**self.ENV, "ELEVEN_LABS_API_KEY": KEY, "ELEVEN_LABS_VOICE_ID": VOICE})
        self.assertEqual((s.eleven_labs_api_key, s.eleven_labs_voice_id), (KEY, VOICE))
        self.assertNotIn(KEY, repr(s))
        self.assertIsInstance(s, Settings)


if __name__ == "__main__":
    unittest.main()
