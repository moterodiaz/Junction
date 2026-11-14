import asyncio
import base64
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

    def test_audio_is_decoded_and_transcribed(self):
        replies = self.exchange(spoken(), 5)
        self.assertEqual(self.heard, [b"RIFF fake wav"])
        self.assertEqual([r.get("stage") for r in replies[:4]],
                         ["transcribing", "reading", "thinking", "drawing"])
        self.assertEqual(replies[4]["type"], "card")

    def test_unknown_command_is_retryable_stt_failed(self):
        self.transcript = "what time is it"
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

    def test_unknown_typed_command_is_stt_failed(self):
        replies = self.exchange(spoken(audio=None, text="sing a song"), 1)
        self.assertEqual(replies[0]["code"], "stt_failed")


class UnknownCommandSkipsReadingTest(unittest.TestCase):
    def test_page_is_not_read_for_an_unknown_command(self):
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "what time is it"))
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


class SetEngineTest(unittest.TestCase):
    def test_set_engine_returns_the_engine_it_replaces(self):
        first = lambda audio: "first"  # noqa: E731
        second = lambda audio: "second"  # noqa: E731
        stt.set_engine(first)
        self.addCleanup(stt.set_engine, None)
        self.assertIs(stt.set_engine(second), first)
        self.assertIs(stt.set_engine(first), second)
        self.assertEqual(stt.transcribe(b"clip"), "first")


if __name__ == "__main__":
    unittest.main()
