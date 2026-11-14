"""Measure reading accuracy on saved sample frames.

PRD reference: section 9 Risks (C1: reading accuracy on 720x1280 frames).
Issue #28: script that measures reading accuracy on saved sample frames.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

try:
    from .page_reader import (
        NoTextFoundError,
        StubNemotronClient,
        extract_frame_data,
        read_page,
    )
except ImportError:
    from page_reader import (
        NoTextFoundError,
        StubNemotronClient,
        extract_frame_data,
        read_page,
    )

DEFAULT_SAMPLES_DIR = Path(__file__).parent / "sample_frames"


def levenshtein(s1: Sequence[Any], s2: Sequence[Any]) -> int:
    """Calculate edit distance between two sequences."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr[j + 1] = min(insertions, deletions, substitutions)
        prev = curr
    return prev[-1]


def compute_character_accuracy(pred: str, target: str) -> float:
    """Compute character accuracy (1 - CER), normalized [0.0, 1.0]."""
    p = pred.strip()
    t = target.strip()
    if not t:
        return 1.0 if not p else 0.0
    dist = levenshtein(p, t)
    return max(0.0, 1.0 - (dist / max(len(t), len(p))))


def compute_word_accuracy(pred: str, target: str) -> float:
    """Compute word accuracy (1 - WER), normalized [0.0, 1.0]."""
    p_words = pred.strip().split()
    t_words = target.strip().split()
    if not t_words:
        return 1.0 if not p_words else 0.0
    dist = levenshtein(p_words, t_words)
    return max(0.0, 1.0 - (dist / max(len(t_words), len(p_words))))


@dataclass
class SampleResult:
    sample_id: str
    has_text: bool
    expected_text: str | None
    predicted_text: str | None
    char_accuracy: float
    word_accuracy: float
    status: str  # "ok", "false_positive", "false_negative", "error"


@dataclass
class BenchmarkReport:
    total_samples: int
    text_samples: int
    blank_samples: int
    avg_char_accuracy: float
    avg_word_accuracy: float
    blank_detection_rate: float
    overall_accuracy: float
    results: list[SampleResult]


def load_samples(samples_dir: Path | str) -> list[dict[str, Any]]:
    """Load sample metadata and file paths from samples_dir."""
    dir_path = Path(samples_dir)
    manifest_path = dir_path / "manifest.json"

    if manifest_path.is_file():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        samples = []
        for entry in manifest:
            img_file = dir_path / entry["image"]
            samples.append({
                "id": entry["id"],
                "image_path": img_file,
                "has_text": entry.get("has_text", True),
                "expected_text": entry.get("expected_text"),
            })
        return samples

    # Fallback: scan directory for images
    samples = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        for img_file in sorted(dir_path.glob(ext)):
            txt_file = img_file.with_suffix(".txt")
            sample_id = img_file.stem
            expected = None
            has_text = False
            if txt_file.is_file():
                raw = txt_file.read_text(encoding="utf-8").strip()
                if raw and raw != "NO_TEXT_FOUND":
                    expected = raw
                    has_text = True
            samples.append({
                "id": sample_id,
                "image_path": img_file,
                "has_text": has_text,
                "expected_text": expected,
            })
    return samples


async def evaluate_sample(
    sample: dict[str, Any],
    client: Any,
) -> SampleResult:
    """Evaluate a single sample frame."""
    sample_id = sample["id"]
    has_text = sample["has_text"]
    expected_text = sample.get("expected_text")
    image_path = Path(sample["image_path"])

    with open(image_path, "rb") as f:
        frame_bytes = f.read()

    predicted_text = None
    char_acc = 0.0
    word_acc = 0.0

    try:
        predicted_text = await read_page(frame_bytes, client=client)
        if not has_text:
            # Blank page returned text -> false positive
            status = "false_positive"
        else:
            status = "ok"
            char_acc = compute_character_accuracy(predicted_text, expected_text or "")
            word_acc = compute_word_accuracy(predicted_text, expected_text or "")
    except NoTextFoundError:
        if not has_text:
            # Blank page correctly returned no text
            status = "ok"
            char_acc = 1.0
            word_acc = 1.0
        else:
            # Text page failed to read -> false negative
            status = "false_negative"
    except Exception as exc:
        status = f"error: {exc}"

    return SampleResult(
        sample_id=sample_id,
        has_text=has_text,
        expected_text=expected_text,
        predicted_text=predicted_text,
        char_accuracy=char_acc,
        word_accuracy=word_acc,
        status=status,
    )


async def run_benchmark(
    samples_dir: Path | str = DEFAULT_SAMPLES_DIR,
    client: Any | None = None,
) -> BenchmarkReport:
    """Run accuracy benchmark over all samples in directory."""
    samples = load_samples(samples_dir)
    if not samples:
        raise ValueError(f"No sample frames found in {samples_dir}")

    if client is None:
        # If no client passed and no NVIDIA_API_KEY in env, use stub
        if not os.environ.get("NVIDIA_API_KEY"):
            # Build stub responses from samples
            stub_responses = {}
            for s in samples:
                with open(s["image_path"], "rb") as f:
                    _, b64 = extract_frame_data(f.read())
                resp = s["expected_text"] if s["has_text"] else "NO_TEXT_FOUND"
                stub_responses[b64] = resp or "NO_TEXT_FOUND"
            client = StubNemotronClient(responses=stub_responses)

    results: list[SampleResult] = []
    for s in samples:
        res = await evaluate_sample(s, client)
        results.append(res)

    text_results = [r for r in results if r.has_text]
    blank_results = [r for r in results if not r.has_text]

    avg_char = (
        sum(r.char_accuracy for r in text_results) / len(text_results)
        if text_results else 1.0
    )
    avg_word = (
        sum(r.word_accuracy for r in text_results) / len(text_results)
        if text_results else 1.0
    )
    blank_rate = (
        sum(1.0 for r in blank_results if r.status == "ok") / len(blank_results)
        if blank_results else 1.0
    )

    all_acc = [r.char_accuracy for r in results]
    overall = sum(all_acc) / len(all_acc) if all_acc else 0.0

    return BenchmarkReport(
        total_samples=len(results),
        text_samples=len(text_results),
        blank_samples=len(blank_results),
        avg_char_accuracy=avg_char,
        avg_word_accuracy=avg_word,
        blank_detection_rate=blank_rate,
        overall_accuracy=overall,
        results=results,
    )


def format_report_table(report: BenchmarkReport) -> str:
    """Format benchmark report as readable table."""
    lines = [
        "=" * 78,
        f"{'Sample ID':<25} {'Type':<8} {'Status':<15} {'Char Acc':<12} {'Word Acc':<12}",
        "-" * 78,
    ]
    for r in report.results:
        stype = "Text" if r.has_text else "Blank"
        char_pct = f"{r.char_accuracy * 100:.1f}%"
        word_pct = f"{r.word_accuracy * 100:.1f}%"
        lines.append(f"{r.sample_id:<25} {stype:<8} {r.status:<15} {char_pct:<12} {word_pct:<12}")

    lines.append("-" * 78)
    lines.append(f"Total Samples:          {report.total_samples}")
    lines.append(f"Text Samples:           {report.text_samples}")
    lines.append(f"Blank/No-Text Samples:  {report.blank_samples}")
    lines.append(f"Avg Character Accuracy: {report.avg_char_accuracy * 100:.2f}%")
    lines.append(f"Avg Word Accuracy:      {report.avg_word_accuracy * 100:.2f}%")
    lines.append(f"Blank Rejection Rate:   {report.blank_detection_rate * 100:.2f}%")
    lines.append(f"Overall Accuracy:       {report.overall_accuracy * 100:.2f}%")
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Nemotron page reading accuracy.")
    parser.add_argument("--samples-dir", default=str(DEFAULT_SAMPLES_DIR), help="Path to sample frames")
    parser.add_argument("--use-stub", action="store_true", help="Force stub client")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    client = None
    if args.use_stub:
        samples = load_samples(args.samples_dir)
        stub_responses = {}
        for s in samples:
            with open(s["image_path"], "rb") as f:
                _, b64 = extract_frame_data(f.read())
            resp = s["expected_text"] if s["has_text"] else "NO_TEXT_FOUND"
            stub_responses[b64] = resp or "NO_TEXT_FOUND"
        client = StubNemotronClient(responses=stub_responses)

    report = asyncio.run(run_benchmark(samples_dir=args.samples_dir, client=client))

    if args.json:
        data = asdict(report)
        print(json.dumps(data, indent=2))
    else:
        print(format_report_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
