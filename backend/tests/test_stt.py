import asyncio
import base64
import os
import threading
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import stt
from app import pipeline
from app.main import app
from stt import engine, match_command

FRAME = {"mime": "image/jpeg", "b64": "AAAA"}
AUDIO = {"mime": "audio/wav", "b64": base64.b64encode(b"RIFF fake wav").decode()}


def spoken(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": AUDIO, "text": None}
    msg.update(overrides)
    return msg


class MatchCommandTest(unittest.TestCase):
    def test_each_command_word(self):
        self.assertEqual(match_command("Explain this"), "explain")
        self.assertEqual(match_command("draw"), "draw")
        self.assertEqual(match_command("Who is this?"), "who_is_this")

    def test_command_inside_a_sentence(self):
        self.assertEqual(match_command("Hey, can you draw this scene for me?"), "draw")
        self.assertEqual(match_command("who’s that"), "who_is_this")

    def test_first_command_wins(self):
        self.assertEqual(match_command("draw it, then explain"), "draw")

    def test_word_forms_whisper_writes(self):
        for heard, command in [("Drawing.", "draw"), ("Make a drawing of this", "draw"),
                               ("She draws it", "draw"), ("Explained.", "explain"),
                               ("Explanation, please", "explain"), ("explaining this", "explain")]:
            with self.subTest(heard):
                self.assertEqual(match_command(heard), command)

    def test_whole_words_only(self):
        self.assertIsNone(match_command("the drawer is unexplained"))
        self.assertIsNone(match_command("Withdraw it"))

    def test_who_is_this_as_whisper_writes_it(self):
        for heard in ["Whose this?", "Who is it?", "Tell me who this is.", "Who this?",
                      "who  is this", "Who's in this picture?", "Who’s that?"]:
            with self.subTest(heard=heard):
                self.assertEqual(match_command(heard), "who_is_this")

    def test_first_command_wins_with_who(self):
        self.assertEqual(match_command("who drew this? explain"), "who_is_this")
        self.assertEqual(match_command("explain who this is"), "explain")

    def test_unknown(self):
        self.assertIsNone(match_command("what time is it"))
        self.assertIsNone(match_command(""))


class SpokenInvokeTest(unittest.TestCase):
    def setUp(self):
        self.heard = []

        def engine(audio):
            self.heard.append(audio)
            return self.transcript

        self.transcript = " Draw this. "
        stt.set_engine(engine)
        self.addCleanup(stt.set_engine, None)
        patcher = mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def exchange(self, message, expect):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json(message)
            return [ws.receive_json() for _ in range(expect)]

    def until_terminal(self, message):
        """Replies up to the card or error, so a wrong outcome fails instead of hanging."""
        replies = []
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json(message)
            while not replies or replies[-1]["type"] == "status":
                replies.append(ws.receive_json())
        return replies

    def test_audio_is_decoded_and_transcribed(self):
        replies = self.exchange(spoken(), 5)
        self.assertEqual(self.heard, [b"RIFF fake wav"])
        self.assertEqual([r.get("stage") for r in replies[:4]],
                         ["transcribing", "reading", "thinking", "drawing"])
        self.assertEqual(replies[4]["type"], "card")

    def test_utterance_without_a_command_word_gets_an_explain_card(self):
        """#260: Whisper heard a question but no command word: answer it as explain."""
        self.transcript = "what does this mean"
        with mock.patch.object(pipeline, "think", wraps=pipeline.think) as think:
            replies = self.until_terminal(spoken())
        self.assertEqual(replies[-1]["type"], "card")
        self.assertEqual([r.get("stage") for r in replies[:-1]],
                         ["transcribing", "reading", "thinking", "drawing"])
        self.assertEqual(think.call_args.args[0], "explain")

    def test_command_word_still_wins_inside_a_sentence(self):
        self.transcript = "can you draw it"
        self.assertEqual(pipeline.command_from(self.transcript), "draw")
        self.assertEqual(pipeline.command_from("so who is this guy"), "who_is_this")

    def test_empty_transcript_is_retryable_stt_failed(self):
        for heard in ("", "   "):
            with self.subTest(heard=heard):
                self.transcript = heard
                replies = self.exchange(spoken(), 2)
                self.assertEqual(replies[0]["stage"], "transcribing")
                self.assertEqual(replies[1]["type"], "error")
                self.assertEqual(replies[1]["code"], "stt_failed")
                self.assertTrue(replies[1]["retryable"])

    def test_engine_crash_is_logged_without_audio(self):
        message = " ".join(["gpu", "on", "fire"])  # built at runtime: logged frames show source lines

        def broken(audio):
            raise RuntimeError(message)

        stt.set_engine(broken)
        with self.assertLogs("metalab", "ERROR") as logs:
            with self.assertRaises(pipeline.PipelineError):
                asyncio.run(pipeline.transcribe(pipeline.Media(**AUDIO)))
        # Type and stack frames for debugging; never the message, which can quote user text (#102).
        self.assertIn("RuntimeError", logs.output[0])
        self.assertIn("in broken", logs.output[0])
        self.assertNotIn("gpu on fire", logs.output[0])
        self.assertNotIn("RIFF", logs.output[0])
        self.assertNotIn(AUDIO["b64"], logs.output[0])

    def test_engine_value_error_is_not_reported_as_bad_audio(self):
        def broken(audio):
            raise ValueError("bad sample rate")

        stt.set_engine(broken)
        with self.assertLogs("metalab", "ERROR"):
            with self.assertRaises(pipeline.PipelineError) as caught:
                asyncio.run(pipeline.transcribe(pipeline.Media(**AUDIO)))
        self.assertNotIn("decoded", caught.exception.message)

    def test_engine_crash_is_retryable_stt_failed(self):
        def broken(audio):
            raise RuntimeError("gpu on fire")

        stt.set_engine(broken)
        replies = self.exchange(spoken(), 2)
        self.assertEqual(replies[1]["code"], "stt_failed")
        self.assertNotIn("gpu", replies[1]["message"])

    def test_bad_base64_is_rejected_before_transcribing(self):
        # The contract makes bad base64 an invalid invoke, so it never reaches the engine.
        [reply] = self.exchange(spoken(audio={"mime": "audio/wav", "b64": "!!not base64!!"}), 1)
        self.assertEqual((reply["type"], reply["code"], reply["retryable"]), ("error", "internal", False))
        self.assertEqual(self.heard, [])

    def test_typed_text_without_a_command_word_is_explained(self):
        self.assertEqual(self.until_terminal(spoken(audio=None, text="sing a song"))[-1]["type"], "card")

    def test_blank_typed_text_is_stt_failed(self):
        replies = self.exchange(spoken(audio=None, text="   "), 1)
        self.assertEqual(replies[0]["code"], "stt_failed")


class EmptyTranscriptSkipsReadingTest(unittest.TestCase):
    def test_page_is_not_read_when_nothing_was_heard(self):
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "  "))
        reads = []

        async def read_page(frame):
            reads.append(frame)
            return "page"

        async def send_stage(stage):
            pass

        with mock.patch.object(pipeline, "read_page", read_page):
            with self.assertRaises(pipeline.PipelineError) as ctx:
                asyncio.run(pipeline.run(pipeline.Invoke.model_validate(spoken()), send_stage))
        self.assertEqual(ctx.exception.code, "stt_failed")
        self.assertEqual(reads, [])


class EngineLoadTest(unittest.TestCase):
    """The default engine is built once, even when the first calls arrive together."""

    def setUp(self):
        stt.set_engine(None)
        self.addCleanup(stt.set_engine, None)
        self.builds = 0

        def slow_factory():
            self.builds += 1
            time.sleep(0.1)  # widen the race window; the assertion does not depend on it
            return lambda audio: " heard "

        patcher = mock.patch.object(engine, "_faster_whisper", slow_factory)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_concurrent_first_calls_build_one_engine(self):
        start = threading.Barrier(8)
        results = []

        def call():
            start.wait()
            results.append(stt.transcribe(b"clip"))

        threads = [threading.Thread(target=call) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(results, ["heard"] * 8)
        self.assertEqual(self.builds, 1)

    def test_warm_loads_the_engine_once(self):
        stt.warm()
        stt.warm()
        self.assertEqual(self.builds, 1)
        self.assertEqual(stt.transcribe(b"clip"), "heard")
        self.assertEqual(self.builds, 1)


class WhisperPromptTest(unittest.TestCase):
    """#260: Whisper is biased toward the three command words."""

    def test_whisper_gets_the_command_prompt(self):
        calls = []

        class FakeModel:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, audio, **kwargs):
                calls.append(kwargs)
                return [mock.Mock(text=" Explain this. ")], None

        fake_module = mock.Mock(WhisperModel=FakeModel)
        with mock.patch.dict("sys.modules", {"faster_whisper": fake_module}):
            run = engine._faster_whisper()
            self.assertEqual(run(b"RIFF"), "Explain this.")
        self.assertEqual(calls[0]["initial_prompt"], "Explain this. Draw this. Who is this?")
        self.assertEqual((calls[0]["language"], calls[0]["beam_size"]), ("en", 1))


class SetEngineTest(unittest.TestCase):
    def test_set_engine_returns_the_engine_it_replaces(self):
        first = lambda audio: "first"  # noqa: E731
        second = lambda audio: "second"  # noqa: E731
        stt.set_engine(first)
        self.addCleanup(stt.set_engine, None)
        self.assertIs(stt.set_engine(second), first)
        self.assertIs(stt.set_engine(first), second)
        self.assertEqual(stt.transcribe(b"clip"), "first")


class GeminiSTTEngineTest(unittest.TestCase):
    """Offline tests for STT_ENGINE=gemini (gemini-3.5-transcribe) adapter."""

    def setUp(self):
        stt.set_engine(None)
        engine.set_gemini_client(None)
        self.addCleanup(stt.set_engine, None)
        self.addCleanup(engine.set_gemini_client, None)

    def test_default_stt_engine_is_whisper(self):
        """When STT_ENGINE is unset or default, _faster_whisper is selected."""
        with mock.patch.dict(os.environ, {"STT_ENGINE": ""}, clear=False):
            with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "whisper transcript") as mock_whisper:
                e = engine._loaded()
                self.assertEqual(e(b"RIFF dummy"), "whisper transcript")
                mock_whisper.assert_called_once()

    def test_stt_engine_gemini_selection_with_stubbed_client(self):
        """STT_ENGINE=gemini selects gemini adapter and calls stubbed client."""
        calls = []

        class StubModels:
            def generate_content(self, model, contents, **kwargs):
                calls.append({"model": model, "contents": contents})
                from types import SimpleNamespace
                return SimpleNamespace(text="Speak the speech, I pray you")

        stub_client = mock.Mock()
        stub_client.models = StubModels()
        engine.set_gemini_client(stub_client)

        with mock.patch.dict(os.environ, {"STT_ENGINE": "gemini"}, clear=False):
            e = engine._loaded()
            result = e(b"RIFF fake audio")
            self.assertEqual(result, "Speak the speech, I pray you")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["model"], "gemini-3.5-transcribe")

    def test_shakespeare_vocabulary_biasing_prompt_usage(self):
        """Gemini transcription uses the Shakespeare / literature vocabulary prompt."""
        calls = []

        class StubModels:
            def generate_content(self, model, contents, **kwargs):
                calls.append(contents)
                from types import SimpleNamespace
                return SimpleNamespace(text="Hamlet, Act 3")

        stub_client = mock.Mock()
        stub_client.models = StubModels()

        eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=False)
        transcript = eng(b"RIFF sample audio")
        self.assertEqual(transcript, "Hamlet, Act 3")

        self.assertEqual(len(calls), 1)
        contents = calls[0]
        # First item is the vocabulary biasing prompt
        prompt = contents[0]
        self.assertIn("Shakespeare", prompt)
        self.assertIn("literature", prompt)
        self.assertIn("Hamlet", prompt)
        self.assertEqual(prompt, engine.SHAKESPEARE_VOCABULARY_PROMPT)
        # Second item is the audio part
        audio_part = contents[1]
        self.assertEqual(audio_part.inline_data.data, b"RIFF sample audio")
        self.assertEqual(audio_part.inline_data.mime_type, "audio/wav")

    def test_missing_api_key_clean_fallback_or_descriptive_error(self):
        """When GEMINI_API_KEY is missing, falls back cleanly to whisper or raises descriptive error."""
        # 1. Fallback to whisper when whisper engine succeeds
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "fallback to whisper"):
                eng = engine._gemini_engine(client=None, api_key="", fallback_to_whisper=True)
                self.assertEqual(eng(b"RIFF audio"), "fallback to whisper")

        # Reset cached _fallback_engine so scenario 2 builds a fresh one via the new mock.
        stt.set_engine(None)

        # 2. Descriptive error when fallback fails / unavailable without leaking audio (REQ-PRIV-02)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with mock.patch.object(engine, "_faster_whisper", side_effect=ImportError("no whisper")):
                eng = engine._gemini_engine(client=None, api_key="", fallback_to_whisper=True)
                with self.assertRaises(RuntimeError) as ctx:
                    eng(b"RIFF audio")
                msg = str(ctx.exception)
                self.assertIn("GEMINI_API_KEY is not set", msg)
                self.assertNotIn("RIFF", msg)

    def test_gemini_client_error_fallback_and_descriptive_exception(self):
        """When Gemini call fails, falls back cleanly to whisper or raises descriptive exception."""
        class FailingModels:
            def generate_content(self, model, contents, **kwargs):
                raise ConnectionError("connection reset by peer")

        stub_client = mock.Mock()
        stub_client.models = FailingModels()

        # 1. Fallback when whisper succeeds
        with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "whisper saved it"):
            eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=True)
            self.assertEqual(eng(b"RIFF clip"), "whisper saved it")

        # 2. Descriptive exception when fallback disabled or fails (REQ-PRIV-02)
        eng_no_fallback = engine._gemini_engine(client=stub_client, fallback_to_whisper=False)
        with self.assertRaises(RuntimeError) as ctx:
            eng_no_fallback(b"RIFF secret clip")
        msg = str(ctx.exception)
        self.assertIn("Gemini transcription failed", msg)
        self.assertIn("ConnectionError", msg)
        self.assertNotIn("secret", msg)
        self.assertNotIn("RIFF", msg)

    def test_unsupported_audio_clean_error(self):
        """Unsupported audio format raises clean ValueError without leaking audio data."""
        stub_client = mock.Mock()
        eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=False)
        with self.assertRaises(ValueError) as ctx:
            eng(b"UNSUPPORTED_DATA_BYTES")
        self.assertIn("Unsupported audio format", str(ctx.exception))
        self.assertNotIn("UNSUPPORTED_DATA_BYTES", str(ctx.exception))

    def test_empty_audio_clean_error(self):
        """Empty audio clip raises ValueError cleanly."""
        stub_client = mock.Mock()
        eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=False)
        with self.assertRaises(ValueError) as ctx:
            eng(b"   ")
        self.assertIn("Empty or invalid audio clip", str(ctx.exception))


class GeminiSTTBehaviorTest(unittest.TestCase):
    """Offline tests for items (a)-(d): debug logging, timeout env, config validation, empty response."""

    def setUp(self):
        stt.set_engine(None)
        engine.set_gemini_client(None)
        self.addCleanup(stt.set_engine, None)
        self.addCleanup(engine.set_gemini_client, None)

    def test_fallback_emits_debug_log_explaining_reason(self):
        """(a) When whisper fallback is taken, a DEBUG log records why (not bare except/pass)."""
        class FailingModels:
            def generate_content(self, model, contents, **kwargs):
                raise ConnectionError("network down")

        stub_client = mock.Mock()
        stub_client.models = FailingModels()

        with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "whisper result"):
            eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=True)
            with self.assertLogs("metalab", "DEBUG") as logs:
                result = eng(b"RIFF audio")
        self.assertEqual(result, "whisper result")
        self.assertTrue(any("fallback" in m.lower() for m in logs.output))

    def test_gemini_timeout_ms_env_override_and_config_validation(self):
        """(b) GEMINI_TIMEOUT_MS is read from env by the engine and validated by config_problems."""
        from app.config import config_problems

        self.assertTrue(any("GEMINI_TIMEOUT_MS" in p for p in config_problems({"GEMINI_TIMEOUT_MS": "not-a-number"})))
        self.assertTrue(any("GEMINI_TIMEOUT_MS" in p for p in config_problems({"GEMINI_TIMEOUT_MS": "0"})))
        self.assertTrue(any("GEMINI_TIMEOUT_MS" in p for p in config_problems({"GEMINI_TIMEOUT_MS": "-1"})))
        self.assertFalse(any("GEMINI_TIMEOUT_MS" in p for p in config_problems({"GEMINI_TIMEOUT_MS": "5000"})))
        self.assertFalse(any("GEMINI_TIMEOUT_MS" in p for p in config_problems({})))

        with mock.patch.dict(os.environ, {"GEMINI_TIMEOUT_MS": "7000"}, clear=False):
            self.assertEqual(engine._get_gemini_timeout_ms(), 7000)
        with mock.patch.dict(os.environ, {"GEMINI_TIMEOUT_MS": ""}, clear=False):
            self.assertEqual(engine._get_gemini_timeout_ms(), engine.GEMINI_TIMEOUT_MS)

    def test_stt_engine_unrecognised_reported_in_config_problems(self):
        """(c) An unrecognised STT_ENGINE value is reported in config_problems; unset is silent."""
        from app.config import config_problems

        self.assertTrue(any("STT_ENGINE" in p for p in config_problems({"STT_ENGINE": "flac"})))
        self.assertFalse(any("STT_ENGINE" in p for p in config_problems({"STT_ENGINE": "whisper"})))
        self.assertFalse(any("STT_ENGINE" in p for p in config_problems({"STT_ENGINE": "gemini"})))
        self.assertFalse(any("STT_ENGINE" in p for p in config_problems({})))

    def test_empty_gemini_response_falls_back_to_whisper(self):
        """(d) Empty or blocked Gemini response falls back to whisper; no fallback raises RuntimeError."""
        from types import SimpleNamespace

        class StubModelsEmpty:
            def generate_content(self, model, contents, **kwargs):
                return SimpleNamespace(text="", candidates=None)

        stub_client = mock.Mock()
        stub_client.models = StubModelsEmpty()

        with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "whisper fallback"):
            eng = engine._gemini_engine(client=stub_client, fallback_to_whisper=True)
            self.assertEqual(eng(b"RIFF audio"), "whisper fallback")

        eng_no_fallback = engine._gemini_engine(client=stub_client, fallback_to_whisper=False)
        with self.assertRaises(RuntimeError) as ctx:
            eng_no_fallback(b"RIFF audio")
        self.assertIn("no speech", str(ctx.exception).lower())


class STTDebugLogTest(unittest.TestCase):
    """REQ-OBS-02: the opt-in transcript log for glasses test runs."""

    def setUp(self):
        import tempfile

        from stt import debug_log

        self.debug_log = debug_log
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "logs", "transcripts.jsonl")
        patcher = mock.patch.dict("os.environ", {
            "NVIDIA_API_KEY": "", "GEMINI_API_KEY": "",
            "STT_DEBUG_LOG": "on", "STT_DEBUG_LOG_PATH": self.path,
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(stt.set_engine, None)
        engine.set_gemini_client(None)
        self.addCleanup(engine.set_gemini_client, None)
        self.addCleanup(debug_log.set_commit_hook, debug_log.set_commit_hook(None))

    def exchange(self, message, expect):
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json(message)
            return [ws.receive_json() for _ in range(expect)]

    def lines(self):
        import json

        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def transcribe(self, raw=b"RIFF fake wav", session_id="s1"):
        media = pipeline.Media(mime="audio/wav", b64=base64.b64encode(raw).decode())
        return asyncio.run(pipeline.transcribe(media, session_id=session_id))

    def test_flag_off_writes_no_file(self):
        os.environ["STT_DEBUG_LOG"] = "off"
        stt.set_engine(lambda audio: "Draw this.")
        replies = self.exchange(spoken(), 5)
        self.assertEqual(replies[4]["type"], "card")
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(os.path.dirname(self.path)))

    def test_one_line_per_clip_with_every_field(self):
        stt.set_engine(lambda audio: " Draw this. ")
        for request_id in ("r1", "r2"):
            replies = self.exchange(spoken(request_id=request_id), 5)
            self.assertEqual(replies[4]["type"], "card")
        lines = self.lines()
        self.assertEqual(len(lines), 2)
        line = lines[0]
        self.assertEqual(set(line), {"ts", "session_id", "engine", "model", "latency_ms", "fallback_used",
                                     "fallback_reason", "clip_bytes", "mime", "transcript", "ok", "error_type"})
        self.assertEqual(line["session_id"], "s1")
        self.assertEqual(line["engine"], "custom")
        self.assertIsNone(line["model"])
        self.assertEqual(line["transcript"], "Draw this.")
        self.assertEqual(line["clip_bytes"], len(b"RIFF fake wav"))
        self.assertEqual(line["mime"], "audio/wav")
        self.assertIs(line["ok"], True)
        self.assertIsNone(line["error_type"])
        self.assertIs(line["fallback_used"], False)
        self.assertIsNone(line["fallback_reason"])
        self.assertIsInstance(line["latency_ms"], int)
        self.assertTrue(line["ts"].endswith("Z"))

    def test_engine_failure_is_recorded_without_its_message(self):
        def broken(audio):
            raise RuntimeError("secret words")

        stt.set_engine(broken)
        with self.assertLogs("metalab", "ERROR"):
            with self.assertRaises(pipeline.PipelineError):
                self.transcribe()
        [line] = self.lines()
        self.assertIs(line["ok"], False)
        self.assertEqual(line["error_type"], "RuntimeError")
        self.assertEqual(line["transcript"], "")
        self.assertNotIn("secret words", open(self.path, encoding="utf-8").read())

    def test_gemini_error_falls_back_to_whisper(self):
        class FailingModels:
            def generate_content(self, model, contents, **kwargs):
                raise ConnectionError("connection reset")

        client = mock.Mock()
        client.models = FailingModels()
        with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "draw this"):
            stt.set_engine(engine._gemini_engine(client=client, fallback_to_whisper=True))
            self.assertEqual(self.transcribe(), "draw this")
        [line] = self.lines()
        self.assertEqual((line["engine"], line["model"]), ("gemini", engine.WHISPER_MODEL))
        self.assertIs(line["fallback_used"], True)
        self.assertEqual(line["fallback_reason"], "gemini_error")
        self.assertEqual(line["transcript"], "draw this")

    def test_failed_whisper_fallback_keeps_the_fallback_reason(self):
        def failing_whisper(audio):
            engine._set_run_info("whisper", engine.WHISPER_MODEL)
            raise RuntimeError("whisper down")

        with mock.patch.object(engine, "_faster_whisper", return_value=failing_whisper):
            stt.set_engine(engine._gemini_engine(client=None, api_key="", fallback_to_whisper=True))
            with self.assertLogs("metalab", "ERROR"):
                with self.assertRaises(pipeline.PipelineError):
                    self.transcribe()
        [line] = self.lines()
        self.assertIs(line["ok"], False)
        self.assertIs(line["fallback_used"], True)
        self.assertEqual(line["fallback_reason"], "no_key")

    def test_no_key_and_bad_format_fallbacks(self):
        with mock.patch.object(engine, "_faster_whisper", return_value=lambda a: "explain"):
            stt.set_engine(engine._gemini_engine(client=None, api_key="", fallback_to_whisper=True))
            self.transcribe()
            stt.set_engine(engine._gemini_engine(client=mock.Mock(), fallback_to_whisper=True))
            self.transcribe(raw=b"not a known container")
        no_key, bad_format = self.lines()
        self.assertEqual((no_key["fallback_reason"], no_key["model"]), ("no_key", engine.WHISPER_MODEL))
        self.assertEqual((bad_format["fallback_reason"], bad_format["model"]), ("bad_format", engine.WHISPER_MODEL))
        self.assertTrue(no_key["fallback_used"] and bad_format["fallback_used"])

    def test_gemini_success_reports_the_gemini_model(self):
        response = mock.Mock(text="who is this")
        client = mock.Mock()
        client.models.generate_content.return_value = response
        stt.set_engine(engine._gemini_engine(client=client, model="gemini-test", fallback_to_whisper=False))
        self.assertEqual(self.transcribe(), "who is this")
        [line] = self.lines()
        self.assertEqual((line["engine"], line["model"], line["fallback_used"]), ("gemini", "gemini-test", False))

    def test_unwritable_path_never_fails_the_request_or_logs_the_transcript(self):
        blocker = os.path.join(self.tmp.name, "a_file")
        open(blocker, "w").close()
        os.environ["STT_DEBUG_LOG_PATH"] = os.path.join(blocker, "sub", "transcripts.jsonl")
        transcript = " ".join(["draw", "the", "ghost", "please"])
        stt.set_engine(lambda audio: transcript)
        with self.assertLogs("metalab", "DEBUG") as logs:
            replies = self.exchange(spoken(), 5)
        self.assertEqual(replies[4]["type"], "card")
        self.assertTrue(any("stt debug log write skipped" in out for out in logs.output))
        for out in logs.output:
            self.assertNotIn("ghost", out)

    def test_commit_hook_is_throttled(self):
        commits = []
        self.debug_log.set_commit_hook(lambda: commits.append(1))
        with mock.patch.object(self.debug_log, "_last_commit", -1e9), \
                mock.patch.object(self.debug_log, "_schedule") as schedule:
            self.debug_log.record(transcript="one")
            self.debug_log.wait_for_commit()
            self.debug_log.record(transcript="two")
            self.debug_log.wait_for_commit()
            self.assertEqual(len(commits), 1)
            schedule.assert_called_once()
            self.debug_log.flush()
            self.assertEqual(len(commits), 2)
        self.assertEqual(len(self.lines()), 2)

    def test_config_problems_for_the_new_variables(self):
        from app.config import config_problems, load_settings

        self.assertTrue(any("STT_DEBUG_LOG must" in p for p in config_problems({"STT_DEBUG_LOG": "maybe"})))
        self.assertTrue(any("STT_DEBUG_LOG_PATH" in p for p in config_problems({"STT_DEBUG_LOG_PATH": "  "})))
        for ok in ({}, {"STT_DEBUG_LOG": "on"}, {"STT_DEBUG_LOG": "off"}, {"STT_DEBUG_LOG_PATH": "/tmp/x.jsonl"}):
            self.assertFalse(any("STT_DEBUG_LOG" in p for p in config_problems(ok)), ok)
        s = load_settings({"NVIDIA_API_KEY": "k", "GEMINI_API_KEY": "k"})
        self.assertEqual((s.stt_debug_log, s.stt_debug_log_path), ("off", "/stt-logs/transcripts.jsonl"))


if __name__ == "__main__":
    unittest.main()
