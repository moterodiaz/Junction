"""#33: one latency summary line per request, with the time spent in each stage (PRD section 9).
#198: thread-safe, privacy-safe model choice distribution tracking (REQ-LAT-01, REQ-PRIV-02).
"""

import os
import re
import threading
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import stt
from app import latency
from app.main import app

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
AUDIO = {"mime": "audio/wav", "b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="}


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


class StageTimerTest(unittest.TestCase):
    def test_each_stage_lasts_until_the_next_one_starts(self):
        ticks = iter([10.0, 10.0, 11.5, 14.0])
        with mock.patch.object(latency, "clock", lambda: next(ticks)):
            timer = latency.StageTimer("r1")
            timer.start("reading")
            timer.start("thinking")
            self.assertEqual(timer.finish(), {"reading": 1.5, "thinking": 2.5, "total": 4.0})


class LatencyLogTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "draw this"))

    def summary_for(self, message):
        with self.assertLogs("metalab.latency", level="INFO") as logs:
            with TestClient(app).websocket_connect("/ws") as ws:
                ws.send_json(message)
                while ws.receive_json()["type"] not in ("card", "error"):
                    pass
        self.assertEqual(len(logs.output), 1, logs.output)
        return logs.output[0]

    def test_spoken_request_logs_all_four_stages(self):
        line = self.summary_for(invoke(text=None, audio=AUDIO))
        for part in ("request=r1", "outcome=card", "transcribing=", "reading=", "thinking=",
                     "drawing=", "total="):
            self.assertIn(part, line)

    def test_typed_request_has_no_transcribing_stage(self):
        line = self.summary_for(invoke())
        self.assertIn("reading=", line)
        self.assertNotIn("transcribing=", line)

    def test_failed_request_still_logs_the_stages_it_reached(self):
        stt.set_engine(lambda audio: "what time is it")
        line = self.summary_for(invoke(text=None, audio=AUDIO))
        self.assertIn("outcome=error", line)
        self.assertIn("transcribing=", line)
        self.assertNotIn("reading=", line)


class ModelChoiceTrackerTest(unittest.TestCase):
    def setUp(self):
        latency.reset_model_distribution()
        self.addCleanup(latency.reset_model_distribution)

    def test_default_stages_initialized_empty(self):
        dist = latency.get_model_distribution()
        expected_stages = {"decision", "read", "reason", "image", "tts"}
        self.assertEqual(set(dist["stages"].keys()), expected_stages)
        for stage in expected_stages:
            self.assertEqual(dist["stages"][stage], {})
            self.assertEqual(dist["fallback_by_stage"][stage], 0)
        self.assertEqual(dist["fallback_total"], 0)
        self.assertEqual(dist["total"], 0)

    def test_record_choice_increments_counters(self):
        latency.record_model_choice("decision", "gemini-3.5-flash-lite")
        latency.record_model_choice("decision", "gemini-3.5-flash-lite")
        latency.record_model_choice("decision", "gemini-4-argon")
        latency.record_model_choice("reason", "gemini-4-argon")

        dist = latency.get_model_distribution()
        self.assertEqual(dist["stages"]["decision"]["gemini-3.5-flash-lite"], 2)
        self.assertEqual(dist["stages"]["decision"]["gemini-4-argon"], 1)
        self.assertEqual(dist["stages"]["reason"]["gemini-4-argon"], 1)
        self.assertEqual(dist["stages"]["read"], {})
        self.assertEqual(dist["total"], 4)
        self.assertEqual(dist["fallback_total"], 0)

    def test_direct_stage_access_and_get(self):
        latency.record_model_choice("decision", "stub")
        dist = latency.get_model_distribution()
        self.assertEqual(dist["decision"]["stub"], 1)
        self.assertEqual(dist.get("decision")["stub"], 1)
        self.assertEqual(dist.get("nonexistent", "default"), "default")
        with self.assertRaises(KeyError):
            _ = dist["completely_invalid_key"]

    def test_fallback_tracking(self):
        latency.record_model_choice("read", "stub", fallback=True)
        latency.record_model_choice("read", "gemini-4-argon", fallback=False)
        latency.record_model_choice("tts", "stub", fallback=True)

        dist = latency.get_model_distribution()
        self.assertEqual(dist["fallback_total"], 2)
        self.assertEqual(dist["fallback_by_stage"]["read"], 1)
        self.assertEqual(dist["fallback_by_stage"]["tts"], 1)
        self.assertEqual(dist["fallback_by_stage"]["decision"], 0)
        self.assertEqual(dist["total"], 3)

    def test_snapshot_isolation(self):
        latency.record_model_choice("image", "imagen-3")
        snap1 = latency.get_model_distribution()

        # Mutate snapshot dict directly
        snap1["stages"]["image"]["imagen-3"] = 999
        snap1["stages"]["image"]["injected"] = 100
        snap1["total"] = -1

        # Internal tracker should be unaffected
        snap2 = latency.get_model_distribution()
        self.assertEqual(snap2["stages"]["image"]["imagen-3"], 1)
        self.assertNotIn("injected", snap2["stages"]["image"])
        self.assertEqual(snap2["total"], 1)

        # New records should not affect snap2
        latency.record_model_choice("image", "imagen-3")
        self.assertEqual(snap2["stages"]["image"]["imagen-3"], 1)
        snap3 = latency.get_model_distribution()
        self.assertEqual(snap3["stages"]["image"]["imagen-3"], 2)

    def test_reset_model_distribution(self):
        latency.record_model_choice("decision", "gemini-3.5-flash-lite", fallback=True)
        self.assertGreater(latency.get_model_distribution()["total"], 0)

        latency.reset_model_distribution()
        dist = latency.get_model_distribution()
        self.assertEqual(dist["total"], 0)
        self.assertEqual(dist["fallback_total"], 0)
        self.assertEqual(dist["stages"]["decision"], {})

    def test_concurrent_recording_thread_safety(self):
        threads = []
        num_threads = 10
        records_per_thread = 50

        def worker():
            for _ in range(records_per_thread):
                latency.record_model_choice("reason", "gemini-4-argon", fallback=False)
                latency.record_model_choice("read", "stub", fallback=True)

        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        dist = latency.get_model_distribution()
        expected_each = num_threads * records_per_thread
        self.assertEqual(dist["stages"]["reason"]["gemini-4-argon"], expected_each)
        self.assertEqual(dist["stages"]["read"]["stub"], expected_each)
        self.assertEqual(dist["fallback_by_stage"]["read"], expected_each)
        self.assertEqual(dist["fallback_total"], expected_each)
        self.assertEqual(dist["total"], expected_each * 2)

    def test_custom_safe_stage(self):
        latency.record_model_choice("rerank", "cross-encoder-v1")
        dist = latency.get_model_distribution()
        self.assertIn("rerank", dist["stages"])
        self.assertEqual(dist["stages"]["rerank"]["cross-encoder-v1"], 1)
        self.assertEqual(dist["fallback_by_stage"]["rerank"], 0)

    def test_log_summary_format(self):
        latency.record_model_choice("decision", "gemini-3.5-flash-lite", fallback=False)
        latency.record_model_choice("read", "stub", fallback=True)

        with self.assertLogs("metalab.latency", level="INFO") as logs:
            summary = latency.log_model_distribution_summary()

        self.assertEqual(len(logs.output), 1)
        log_line = logs.output[0]
        self.assertIn("model_distribution", log_line)
        self.assertIn("total=2", log_line)
        self.assertIn("fallback_total=1", log_line)
        self.assertIn("decision[gemini-3.5-flash-lite=1,fallbacks=0]", log_line)
        self.assertIn("read[stub=1,fallbacks=1]", log_line)
        self.assertEqual(summary, f"total=2 fallback_total=1 {summary.split(' ', 2)[2]}")

    def test_tracker_instance_methods(self):
        tracker = latency.ModelChoiceTracker()
        tracker.record_choice("image", "imagen-3", fallback=True)
        self.assertEqual(tracker.total, 1)
        self.assertEqual(tracker.fallback_total, 1)
        dist = tracker.get_distribution()
        self.assertEqual(dist["stages"]["image"]["imagen-3"], 1)
        tracker.reset()
        self.assertEqual(tracker.total, 0)


class ModelChoicePrivacyTest(unittest.TestCase):
    def setUp(self):
        latency.reset_model_distribution()
        self.addCleanup(latency.reset_model_distribution)

    def test_privacy_guarantee_only_ids_and_integers(self):
        """REQ-PRIV-02: Stored counters must only contain stage IDs, model IDs, and integers."""
        latency.record_model_choice("decision", "gemini-3.5-flash-lite", fallback=False)
        latency.record_model_choice("read", "stub", fallback=True)
        latency.record_model_choice("reason", "gemini-4-argon", fallback=False)
        latency.record_model_choice("image", "models/imagen-3", fallback=False)
        latency.record_model_choice("tts", "stub", fallback=True)

        dist = latency.get_model_distribution()
        stage_pat = re.compile(r"^[a-z0-9_\-]+$")
        model_pat = re.compile(r"^[a-zA-Z0-9_\-\.\/]+$")

        self.assertIsInstance(dist["total"], int)
        self.assertIsInstance(dist["fallback_total"], int)

        for stage_name, fb_count in dist["fallback_by_stage"].items():
            self.assertTrue(stage_pat.match(stage_name), f"Invalid stage: {stage_name}")
            self.assertIsInstance(fb_count, int)

        for stage_name, model_counts in dist["stages"].items():
            self.assertTrue(stage_pat.match(stage_name), f"Invalid stage: {stage_name}")
            self.assertIsInstance(model_counts, dict)
            for model_id, count in model_counts.items():
                self.assertTrue(model_pat.match(model_id), f"Invalid model_id: {model_id}")
                self.assertIsInstance(count, int)
                # Confirm zero user utterances / prompts
                self.assertNotIn(" ", model_id)
                self.assertNotIn("\n", model_id)

    def test_reject_user_utterance(self):
        """User speech or transcript text with spaces or punctuation must be rejected."""
        with self.assertRaises(ValueError):
            latency.record_model_choice("decision", "What is Hamlet's soliloquy about?")

        with self.assertRaises(ValueError):
            latency.record_model_choice("User utterance: hello", "gemini-3.5-flash-lite")

    def test_reject_prompt_text(self):
        """Prompt texts with spaces, newlines, or markdown must be rejected."""
        with self.assertRaises(ValueError):
            latency.record_model_choice("reason", "You are an assistant. Answer the user.")

        with self.assertRaises(ValueError):
            latency.record_model_choice("read", "Line 1\nLine 2 of book page")

    def test_reject_audio_bytes(self):
        """Raw audio bytes must be rejected."""
        with self.assertRaises(TypeError):
            latency.record_model_choice("decision", b"\x00\x01\x02\x03")

        with self.assertRaises(TypeError):
            latency.record_model_choice(b"decision", "gemini-4")

    def test_reject_session_or_request_ids_in_model(self):
        """Parameters formatted as session/request assignments or URLs must be rejected."""
        with self.assertRaises(ValueError):
            latency.record_model_choice("read", "session_id=123-456")

        with self.assertRaises(ValueError):
            latency.record_model_choice("read", "https://api.nvidia.com/v1/models")

    def test_reject_non_string_inputs(self):
        with self.assertRaises(TypeError):
            latency.record_model_choice(123, "gemini-4")

        with self.assertRaises(TypeError):
            latency.record_model_choice("reason", {"model": "gemini-4"})

    def test_reject_empty_string(self):
        with self.assertRaises(ValueError):
            latency.record_model_choice("", "gemini-4")

        with self.assertRaises(ValueError):
            latency.record_model_choice("decision", "   ")

    def test_reject_excessive_length(self):
        with self.assertRaises(ValueError):
            latency.record_model_choice("read", "a" * 100)

    def test_reject_invalid_fallback_type(self):
        with self.assertRaises(TypeError):
            latency.record_model_choice("read", "gemini-4", fallback="yes")


if __name__ == "__main__":
    unittest.main()
