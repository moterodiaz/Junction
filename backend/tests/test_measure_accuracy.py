"""Unit tests for reading accuracy measurement script."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from ai.measure_accuracy import (
    DEFAULT_SAMPLES_DIR,
    compute_character_accuracy,
    compute_word_accuracy,
    format_report_table,
    load_samples,
    main,
    run_benchmark,
)
from ai.page_reader import StubNemotronClient


class MeasureAccuracyTest(unittest.TestCase):
    def test_metrics_identical_strings(self):
        s = "To be or not to be"
        self.assertEqual(compute_character_accuracy(s, s), 1.0)
        self.assertEqual(compute_word_accuracy(s, s), 1.0)

    def test_metrics_empty_strings(self):
        self.assertEqual(compute_character_accuracy("", ""), 1.0)
        self.assertEqual(compute_word_accuracy("", ""), 1.0)
        self.assertEqual(compute_character_accuracy("abc", ""), 0.0)
        self.assertEqual(compute_word_accuracy("abc def", ""), 0.0)

    def test_metrics_slight_differences(self):
        ref = "To be, or not to be"
        pred = "To be or not to be"
        char_acc = compute_character_accuracy(pred, ref)
        word_acc = compute_word_accuracy(pred, ref)
        self.assertGreater(char_acc, 0.9)
        self.assertGreater(word_acc, 0.8)

    def test_load_samples_from_directory(self):
        samples = load_samples(DEFAULT_SAMPLES_DIR)
        self.assertGreaterEqual(len(samples), 4)
        sample_ids = {s["id"] for s in samples}
        self.assertIn("hamlet_act3_scene1", sample_ids)
        self.assertIn("blank_page", sample_ids)

    def test_run_benchmark_with_stub_client(self):
        samples = load_samples(DEFAULT_SAMPLES_DIR)
        responses = {}
        for s in samples:
            with open(s["image_path"], "rb") as f:
                raw = f.read()
            import base64
            b64 = base64.b64encode(raw).decode("ascii")
            responses[b64] = s["expected_text"] if s["has_text"] else "NO_TEXT_FOUND"

        client = StubNemotronClient(responses=responses)
        report = asyncio.run(run_benchmark(samples_dir=DEFAULT_SAMPLES_DIR, client=client))

        self.assertEqual(report.total_samples, len(samples))
        self.assertEqual(report.blank_detection_rate, 1.0)
        self.assertEqual(report.avg_char_accuracy, 1.0)
        self.assertEqual(report.overall_accuracy, 1.0)

        table = format_report_table(report)
        self.assertIn("Sample ID", table)
        self.assertIn("hamlet_act3_scene1", table)
        self.assertIn("Overall Accuracy:       100.00%", table)

    def test_main_cli(self):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["measure_accuracy.py", "--use-stub"]
            exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
