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



def interactions_from(models):
    """Answer aio.interactions.create the way the provider does, from the same fake as
    models.generate_content, so each test still controls the audio, errors and model list."""
    import base64

    async def create(model, input, response_format, generation_config):
        out = await models.generate_content(model=model, contents=input[0]["content"][0]["text"], config=None)
        part = next(p for p in out.candidates[0].content.parts if p.inline_data)
        data = part.inline_data.data
        mime = getattr(part.inline_data, "mime_type", "") or ""
        rate = int(mime.split("rate=")[1]) if "rate=" in mime else None
        return SimpleNamespace(output_audio=SimpleNamespace(data=base64.b64encode(data).decode(), sample_rate=rate))
    return SimpleNamespace(create=create)


def fake_aio(models):
    return SimpleNamespace(models=models, interactions=interactions_from(models))

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

    def test_http_base_is_upgraded_to_https(self):
        speak.set_speech_client(StubSpeech())
        with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": "http://metalab.example"}):
            card = self.card()
            self.assertIsNotNone(card["audio_url"])
            self.assertTrue(card["audio_url"].startswith(BASE + "/audio/"))

    def test_bare_host_base_is_upgraded_to_https(self):
        speak.set_speech_client(StubSpeech())
        with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": "metalab.example"}):
            card = self.card()
            self.assertIsNotNone(card["audio_url"])
            self.assertTrue(card["audio_url"].startswith(BASE + "/audio/"))

    def test_logging_never_echoes_speech_text_on_failure(self):
        secret_user_speech = "SUPER_SECRET_USER_WORDS_12345"
        speak.set_speech_client(StubSpeech(error=RuntimeError("upstream tts quota error")))
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            url = asyncio.run(speak.speak(secret_user_speech, "s1"))
        self.assertIsNone(url)
        log_text = " ".join(captured.output)
        self.assertNotIn(secret_user_speech, log_text)
        self.assertIn("RuntimeError", log_text)

    def provider_error(self, code, status, message):
        """What google.genai raises for an HTTP error: .code, .status and .message."""
        err = RuntimeError(message)
        err.code, err.status, err.message = code, status, message
        return err

    def failure_log(self, error, text="hello there", api_key="KEY-do-not-log-1234"):
        client = StubSpeech(error=error)
        client.api_key = api_key
        speak.set_speech_client(client)
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            self.assertIsNone(asyncio.run(speak.speak(text, "s1")))
        return " ".join(captured.output)

    def test_a_provider_failure_logs_its_status_and_reason(self):
        out = self.failure_log(self.provider_error(400, "INVALID_ARGUMENT", "Unsupported voice name\nfor this model"))
        self.assertIn("code=400", out)
        self.assertIn("status=INVALID_ARGUMENT", out)
        self.assertIn("reason=Unsupported voice name for this model", out)

    def test_the_failure_log_never_holds_the_key_or_the_text(self):
        message = "bad request for KEY-do-not-log-1234 while speaking: secret words here"
        out = self.failure_log(self.provider_error(403, "PERMISSION_DENIED", message), text="secret words here")
        self.assertNotIn("KEY-do-not-log-1234", out)
        self.assertNotIn("secret words here", out)
        self.assertIn("[redacted]", out)

    def test_the_reason_is_cut_to_one_short_line(self):
        out = self.failure_log(self.provider_error(500, "INTERNAL", "x" * 5000))
        self.assertLess(len(out), 600)

    def test_a_missing_model_logs_the_tts_models_the_key_can_use(self):
        class Lister(StubSpeech):
            async def list_tts_models(self):
                return ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]
        speak._listed_models = False
        client = Lister(error=self.provider_error(404, "NOT_FOUND", "models/gemini-3.8-flash-tts is not found"))
        speak.set_speech_client(client)
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            asyncio.run(speak.speak("hello", "s1"))
        out = " ".join(captured.output)
        self.assertIn("status=NOT_FOUND", out)
        self.assertIn("TTS models available to this key: gemini-2.5-flash-preview-tts, gemini-2.5-pro-preview-tts", out)

    def fake_genai(self, models, fail_models):
        """A stand-in for genai.Client: calls to a model in fail_models raise a 404 like the provider."""
        calls = []

        class Err(Exception):
            code, status = 404, "NOT_FOUND"
            message = "model not found"

        async def generate_content(model, contents, config):
            calls.append(model)
            if model in fail_models:
                raise Err("not found")
            part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01\x00" * 100, mime_type="audio/L16;rate=24000"))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

        async def listing():
            for name in models:
                yield SimpleNamespace(name="models/" + name)

        async def list_models():
            return listing()

        client = SimpleNamespace(aio=fake_aio(SimpleNamespace(
            generate_content=generate_content, list=list_models)))
        return client, calls

    def test_a_missing_model_falls_back_to_the_best_tts_model_and_retries_once(self):
        fake, calls = self.fake_genai(
            ["gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts", "gemini-2.0-flash", "gemini-3.1-flash-tts"],
            fail_models={"gemini-3.8-flash-tts"})
        client = speak.GeminiSpeechClient("KEY", "gemini-3.8-flash-tts")
        client._genai = fake
        pcm, rate = asyncio.run(client.synthesize("hello"))
        self.assertEqual((len(pcm), rate), (200, 24000))
        self.assertEqual(calls, ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts"])  # stable Flash beats preview and Pro
        self.assertEqual(client.model, "gemini-3.1-flash-tts")
        asyncio.run(client.synthesize("again"))
        self.assertEqual(calls[2:], ["gemini-3.1-flash-tts"])  # remembered: no second 404

    def test_no_other_tts_model_means_the_error_stands(self):
        fake, calls = self.fake_genai(["gemini-2.0-flash"], fail_models={"gemini-3.8-flash-tts"})
        client = speak.GeminiSpeechClient("KEY", "gemini-3.8-flash-tts")
        client._genai = fake
        with self.assertRaises(Exception) as caught:
            asyncio.run(client.synthesize("hello"))
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(calls, ["gemini-3.8-flash-tts"])

    def test_other_errors_never_switch_models(self):
        fake, calls = self.fake_genai(["gemini-3.1-flash-tts"], fail_models=set())

        async def boom(model, contents, config):
            calls.append(model)
            err = RuntimeError("bad voice")
            err.code, err.status = 400, "INVALID_ARGUMENT"
            raise err
        fake.aio.models.generate_content = boom
        client = speak.GeminiSpeechClient("KEY", "gemini-3.8-flash-tts")
        client._genai = fake
        with self.assertRaises(RuntimeError):
            asyncio.run(client.synthesize("hello"))
        self.assertEqual(calls, ["gemini-3.8-flash-tts"])
        self.assertEqual(client.model, "gemini-3.8-flash-tts")

    def test_recovered_model_not_reset_on_next_speak_call(self):
        """Thread 1: after model recovery, speak() must reuse the client without reverting to the broken model."""
        speak._gemini = None
        speak._listed_models = False
        calls = []

        class Err(Exception):
            code, status, message = 404, "NOT_FOUND", "not found"

        async def gen(model, contents, config):
            calls.append(model)
            if model == "gemini-broken":
                raise Err()
            part = SimpleNamespace(inline_data=SimpleNamespace(
                data=b"\x01\x00" * 8, mime_type="audio/L16;rate=24000"))
            return SimpleNamespace(
                candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

        async def listing():
            yield SimpleNamespace(name="models/gemini-flash-tts")

        async def list_models():
            return listing()

        fake = SimpleNamespace(aio=fake_aio(SimpleNamespace(
            generate_content=gen, list=list_models)))

        patched_env = {"GEMINI_API_KEY": "KEY", "MODEL_TTS": "gemini-broken", "IMAGE_BASE_URL": BASE}
        with mock.patch.dict(os.environ, patched_env):
            with mock.patch("google.genai.Client", lambda api_key: fake):
                asyncio.run(speak.speak("first", "s1"))
                after_first = len(calls)
                asyncio.run(speak.speak("second", "s1"))

        self.assertIn("gemini-broken", calls[:after_first])
        self.assertEqual(calls[after_first:], ["gemini-flash-tts"])  # no retry of broken model

    def test_describe_failure_redacts_secret_spanning_truncation_boundary(self):
        """Thread 2: a secret that starts before the 200-char cutoff must still be fully redacted."""
        padding = "x" * 190
        secret_text = "TOP_SECRET_DATA"
        message = padding + secret_text + " extra"
        err = self.provider_error(400, "BAD", message)
        result = speak.describe_failure(err, text=secret_text)
        self.assertNotIn("TOP_SECRET_DATA", result)
        self.assertIn("[redacted]", result)

    def test_describe_failure_redacts_multiline_speech_text(self):
        """Thread 2: multiline speech text must be matched after whitespace normalization."""
        secret = "my secret\nphrase"
        message = "leaked: my secret phrase here"
        err = self.provider_error(400, "BAD", message)
        result = speak.describe_failure(err, text=secret)
        self.assertNotIn("my secret phrase", result)
        self.assertIn("[redacted]", result)

    def test_model_list_error_in_synthesize_reraises_original_404(self):
        """Thread 3: if list_tts_models() raises during fallback, the original 404 is preserved."""
        speak._listed_models = False

        class Err(Exception):
            code, status, message = 404, "NOT_FOUND", "model not found"

        async def gen(model, contents, config):
            raise Err()

        async def list_models():
            raise ConnectionError("network down")

        fake = SimpleNamespace(aio=fake_aio(SimpleNamespace(
            generate_content=gen, list=list_models)))

        client = speak.GeminiSpeechClient("KEY", "gemini-broken")
        client._genai = fake
        speak.set_speech_client(client)
        with self.assertLogs("metalab.speak", level="INFO") as captured:
            result = asyncio.run(speak.speak("hello", "s1"))
        self.assertIsNone(result)
        out = " ".join(captured.output)
        self.assertIn("status=NOT_FOUND", out)
        self.assertIn("TTS model list failed", out)

    def test_model_list_called_at_most_once_on_persistent_404(self):
        """Thread 4: list_tts_models() must be called once total, not once in synthesize and again in speak."""
        list_calls = []

        class Err(Exception):
            code, status, message = 404, "NOT_FOUND", "not found"

        async def gen(model, contents, config):
            raise Err()

        async def listing():
            list_calls.append(1)
            if False:
                yield  # make this an empty async generator

        async def list_models():
            return listing()

        fake = SimpleNamespace(aio=fake_aio(SimpleNamespace(
            generate_content=gen, list=list_models)))

        speak._listed_models = False
        client = speak.GeminiSpeechClient("KEY", "gemini-broken")
        client._genai = fake
        speak.set_speech_client(client)

        with self.assertLogs("metalab.speak", level="INFO"):
            asyncio.run(speak.speak("hello", "s1"))

        self.assertEqual(len(list_calls), 1)

    def test_active_speech_client_exposes_recovered_model(self):
        """Thread 5: active_speech_client().model is the recovered model; _configured_model is original."""
        speak._gemini = None
        speak._listed_models = False

        class Err(Exception):
            code, status, message = 404, "NOT_FOUND", "not found"

        async def gen(model, contents, config):
            if model == "gemini-broken":
                raise Err()
            part = SimpleNamespace(inline_data=SimpleNamespace(
                data=b"\x01\x00" * 8, mime_type="audio/L16;rate=24000"))
            return SimpleNamespace(
                candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

        async def listing():
            yield SimpleNamespace(name="models/gemini-flash-tts")

        async def list_models():
            return listing()

        fake = SimpleNamespace(aio=fake_aio(SimpleNamespace(
            generate_content=gen, list=list_models)))

        patched_env = {"GEMINI_API_KEY": "KEY", "MODEL_TTS": "gemini-broken", "IMAGE_BASE_URL": BASE}
        with mock.patch.dict(os.environ, patched_env):
            with mock.patch("google.genai.Client", lambda api_key: fake):
                asyncio.run(speak.speak("hello", "s1"))

        client = speak.active_speech_client()
        self.assertIsNotNone(client)
        self.assertEqual(client.model, "gemini-flash-tts")
        self.assertEqual(client._configured_model, "gemini-broken")

    def test_other_failures_do_not_list_models(self):
        class Lister(StubSpeech):
            listed = False

            async def list_tts_models(self):
                Lister.listed = True
                return []
        speak._listed_models = False
        speak.set_speech_client(Lister(error=self.provider_error(429, "RESOURCE_EXHAUSTED", "quota")))
        with self.assertLogs("metalab.speak", level="INFO"):
            asyncio.run(speak.speak("hello", "s1"))
        self.assertFalse(Lister.listed)

    def test_logging_never_echoes_speech_text_when_skipped(self):
        secret_user_speech = "SUPER_SECRET_USER_WORDS_67890"
        speak.set_speech_client(None)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertLogs("metalab.speak", level="INFO") as captured:
                url = asyncio.run(speak.speak(secret_user_speech, "s1"))
            self.assertIsNone(url)
            log_text = " ".join(captured.output)
            self.assertNotIn(secret_user_speech, log_text)

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

    def test_resumed_session_speech_delivered_despite_full_epoch_cap(self):
        """LRU fix: a session that resumes and speaks while >cap other sessions are cleaned
        up must still deliver audio; with the old FIFO cap its entry would be pruned
        mid-speak, epoch would read 0 != saved epoch, and valid speech would be dropped."""
        with mock.patch.object(speak, "_MAX_EPOCH_ENTRIES", 5):
            # Register the target session first so its entry is the oldest (would be
            # pruned first under the old FIFO scheme), then fill to the cap with others.
            speak.cleanup_session("target")
            for i in range(4):
                speak.cleanup_session(f"filler-{i}")
            # _epochs now has 5 entries; "target" is the oldest (front of the OrderedDict).

            release = asyncio.Event()

            class SlowSpeech:
                async def synthesize(self, text):
                    await release.wait()
                    return b"\x01\x00" * 8

            speak.set_speech_client(SlowSpeech())

            async def go():
                task = asyncio.create_task(speak.speak("hello", "target"))
                await asyncio.sleep(0)  # speak() reads epoch, moves to end, marks inflight
                # Push over cap twice; pruning must skip "target" (has an inflight speak).
                speak.cleanup_session("overflow-1")
                speak.cleanup_session("overflow-2")
                release.set()
                return await task

            url = asyncio.run(go())
            self.assertIsNotNone(url, "speech must be delivered: epoch entry must not be pruned while speak() is inflight")


class InflightCountTest(SpeakBase):
    """_epochs_inflight entries are removed when speak() finishes, fails, or is cancelled."""

    def test_normal_speak_removes_inflight_entry(self):
        speak.set_speech_client(StubSpeech())
        asyncio.run(speak.speak("hello", "s1"))
        self.assertNotIn("s1", speak._epochs_inflight)

    def test_exception_in_speak_removes_inflight_entry(self):
        speak.set_speech_client(StubSpeech(error=RuntimeError("boom")))
        asyncio.run(speak.speak("hello", "s1"))
        self.assertNotIn("s1", speak._epochs_inflight)

    def test_cancelled_speak_removes_inflight_entry_and_session_is_prunable(self):
        hangup = asyncio.Event()

        class HangingSpeech:
            async def synthesize(self, text):
                await hangup.wait()
                return b"\x01\x00" * 8

        speak.set_speech_client(HangingSpeech())

        async def go():
            task = asyncio.create_task(speak.speak("hello", "s1"))
            await asyncio.sleep(0)  # let speak() increment inflight
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(go())
        self.assertNotIn("s1", speak._epochs_inflight)
        # with no inflight count, s1 is now prunable when the LRU cap is exceeded
        with mock.patch.object(speak, "_MAX_EPOCH_ENTRIES", 1):
            speak.cleanup_session("other")
        self.assertNotIn("s1", speak._epochs)


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
            return SimpleNamespace(aio=fake_aio(FakeModels()))

        client = speak.GeminiSpeechClient("key", "tts-model")
        with mock.patch("google.genai.Client", fake_client):
            pcm, rate = asyncio.run(client.synthesize("one"))
            asyncio.run(client.synthesize("two"))
        self.assertEqual((pcm, rate), (b"\x01\x00" * 8, 16000))
        self.assertEqual(made, ["key"])
        with wave.open(io.BytesIO(speak.to_wav(pcm, rate))) as wav:
            self.assertEqual(wav.getframerate(), 16000)


class InteractionsRequestTest(unittest.TestCase):
    def test_speech_is_requested_through_the_interactions_api_with_l16_and_the_voice(self):
        sent = {}

        async def create(**kwargs):
            sent.update(kwargs)
            return SimpleNamespace(output_audio=SimpleNamespace(data="AQA=", sample_rate=None))

        client = speak.GeminiSpeechClient("key", "gemini-3.8-flash-tts")
        client._genai = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        pcm, rate = asyncio.run(client.synthesize("Hello there"))
        self.assertEqual(pcm, b"\x01\x00")  # base64 "AQA=" decodes to two PCM bytes
        self.assertEqual(sent["model"], "gemini-3.8-flash-tts")
        self.assertEqual(sent["input"], [{"type": "user_input", "content": [{"type": "text", "text": "Hello there"}]}])
        self.assertEqual(sent["response_format"]["mime_type"], "audio/l16")
        self.assertEqual(sent["generation_config"], {"speech_config": [{"voice": speak.VOICE}]})
        self.assertNotIn("speechConfig", str(sent))


if __name__ == "__main__":
    unittest.main()
