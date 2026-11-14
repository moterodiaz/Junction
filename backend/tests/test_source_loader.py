"""Unit tests for public-domain Hamlet source text loader and passage locator.

Tests cover:
- PRD Section 2: Loading source text to place passages by act, scene, and line.
- PRD Section 8: Demo play (Hamlet) and canonical quotes.
- PRD Section 10 Open Question 7 (C4) and Issue #29: Adding a play is a data-only change.
- Multi-line, OCR-noisy, and fuzzy passage recognition.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ai import (
    find_passage,
    get_play,
    get_source_citation,
    list_plays,
    load_play,
    locate_passage,
    set_plays_directory,
)


class SourceLoaderTest(unittest.TestCase):
    def tearDown(self) -> None:
        # Ensure default plays directory is restored after any custom directory test
        set_plays_directory(None)

    def test_hamlet_metadata_and_license(self) -> None:
        """Verify Hamlet source text provenance, Project Gutenberg URL, and public-domain license."""
        play = load_play("Hamlet")
        self.assertEqual(play.id, "hamlet")
        self.assertEqual(play.title, "Hamlet")
        self.assertEqual(play.author, "William Shakespeare")
        self.assertEqual(play.source_url, "https://www.gutenberg.org/ebooks/1524")
        self.assertIn("Public Domain", play.license)
        self.assertEqual(len(play.acts), 5)
        self.assertGreater(play.total_lines, 3500)

    def test_list_plays_discovers_hamlet(self) -> None:
        """Verify list_plays discovers registered play JSON files."""
        plays = list_plays()
        self.assertIn("hamlet", plays)

    def test_data_only_extensibility(self) -> None:
        """Verify PRD Open Question 7: adding a play is a data-only change.

        Placing a new play JSON into a directory makes it immediately discoverable
        and searchable without modifying any code.
        """
        sample_play = {
            "id": "macbeth",
            "title": "Macbeth",
            "full_title": "The Tragedy of Macbeth",
            "author": "William Shakespeare",
            "source_url": "https://www.gutenberg.org/ebooks/1533",
            "license": "Public Domain (Project Gutenberg License)",
            "acts": [
                {
                    "act": 1,
                    "act_roman": "I",
                    "scenes": [
                        {
                            "scene": 1,
                            "scene_roman": "I",
                            "location_desc": "An open place. Thunder and lightning.",
                            "lines": [
                                {
                                    "type": "line",
                                    "line": 1,
                                    "speaker": "FIRST WITCH",
                                    "text": "When shall we three meet again",
                                },
                                {
                                    "type": "line",
                                    "line": 2,
                                    "speaker": "FIRST WITCH",
                                    "text": "In thunder, lightning, or in rain?",
                                },
                                {
                                    "type": "line",
                                    "line": 10,
                                    "speaker": "ALL",
                                    "text": "Fair is foul, and foul is fair:",
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            play_file = tmppath / "macbeth.json"
            with open(play_file, "w", encoding="utf-8") as f:
                json.dump(sample_play, f)

            # Point loader to the new directory (pure data change)
            set_plays_directory(tmppath)

            plays = list_plays()
            self.assertEqual(plays, ["macbeth"])

            loaded = load_play("macbeth")
            self.assertEqual(loaded.title, "Macbeth")
            self.assertEqual(loaded.source_url, "https://www.gutenberg.org/ebooks/1533")

            match = find_passage("Fair is foul, and foul is fair", play="macbeth")
            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match.act, 1)
            self.assertEqual(match.scene, 1)
            self.assertEqual(match.line_start, 10)
            self.assertEqual(match.speaker, "ALL")

    def test_locate_canonical_hamlet_passages(self) -> None:
        """Verify placing key passages by Act, Scene, and Line (PRD section 2 and 8)."""
        test_cases = [
            ("To be, or not to be, that is the question", 3, 1, 64, "HAMLET"),
            ("A little more than kin, and less than kind", 1, 2, 70, "HAMLET"),
            ("Neither a borrower nor a lender be", 1, 3, 81, "POLONIUS"),
            ("This above all: to thine own self be true", 1, 3, 84, "POLONIUS"),
            ("Something is rotten in the state of Denmark", 1, 4, 101, "MARCELLUS"),
            ("Brevity is the soul of wit", 2, 2, 99, "POLONIUS"),
            ("The play’s the thing", 2, 2, 563, "HAMLET"),
            ("The lady protests too much, methinks", 3, 2, 232, "QUEEN"),
            ("Words without thoughts never to heaven go", 3, 3, 104, "KING"),
            ("I must be cruel, only to be kind", 3, 4, 198, "HAMLET"),
            ("Alas, poor Yorick! I knew him, Horatio", 5, 1, 150, "HAMLET"),
            ("The rest is silence", 5, 2, 360, "HAMLET"),
        ]

        for quote, exp_act, exp_scene, exp_line, exp_speaker in test_cases:
            with self.subTest(quote=quote):
                match = locate_passage(quote, play="Hamlet")
                self.assertIsNotNone(match, f"Failed to match: {quote}")
                assert match is not None
                self.assertEqual(match.act, exp_act)
                self.assertEqual(match.scene, exp_scene)
                self.assertEqual(match.line_start, exp_line)
                if exp_speaker:
                    self.assertEqual(match.speaker, exp_speaker)
                self.assertEqual(match.play_title, "Hamlet")

    def test_locate_multiline_passage(self) -> None:
        """Verify recognizing multi-line passages spanning line ranges."""
        passage = (
            "To be, or not to be, that is the question:\n"
            "Whether 'tis nobler in the mind to suffer\n"
            "The slings and arrows of outrageous fortune"
        )
        match = find_passage(passage, play="Hamlet")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)
        self.assertEqual(match.line_start, 64)
        self.assertEqual(match.line_end, 66)
        self.assertIn("lines 64-66", match.location)

    def test_fuzzy_and_ocr_noise_tolerance(self) -> None:
        """Verify tolerance to typical camera/OCR artifacts: missing punctuation, casing, line break."""
        noisy_transcription = "to be or not to be that is the queston whether tis nobler in the mind"
        match = find_passage(noisy_transcription, play="Hamlet", min_score=0.6)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)
        self.assertEqual(match.line_start, 64)
        self.assertGreaterEqual(match.score, 0.6)

    def test_unmatched_passage_returns_none(self) -> None:
        """Verify queries not present in the play return None gracefully."""
        self.assertIsNone(find_passage("A completely invented line not in Shakespeare", play="Hamlet"))
        self.assertIsNone(find_passage("", play="Hamlet"))
        self.assertIsNone(find_passage("    ", play="Hamlet"))

    def test_source_citation_format(self) -> None:
        """Verify source citation conforms to PRD Section 7 Card schema."""
        citation = get_source_citation("Hamlet")
        self.assertEqual(citation["title"], "Hamlet, public-domain text")
        self.assertEqual(citation["url"], "https://www.gutenberg.org/ebooks/1524")

    def test_cross_play_search(self) -> None:
        """Verify searching across all registered plays when play is None."""
        match = find_passage("To be, or not to be", play=None)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.play_title, "Hamlet")
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)

    def test_passage_match_to_dict(self) -> None:
        """Verify PassageMatch dictionary representation."""
        match = find_passage("To be, or not to be, that is the question", play="Hamlet")
        self.assertIsNotNone(match)
        assert match is not None
        d = match.to_dict()
        self.assertEqual(d["play"], "Hamlet")
        self.assertEqual(d["act"], 3)
        self.assertEqual(d["scene"], 1)
        self.assertEqual(d["line_start"], 64)
        self.assertEqual(d["speaker"], "HAMLET")
        self.assertIn("source", d)
        self.assertEqual(d["source"]["url"], "https://www.gutenberg.org/ebooks/1524")

    def test_cache_is_per_directory(self) -> None:
        """Same play name in different directories must not share a cache entry."""
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for d, title in ((d1, "One"), (d2, "Two")):
                (Path(d) / "hamlet.json").write_text(
                    json.dumps({"id": "hamlet", "title": title, "acts": []}), encoding="utf-8"
                )
            self.assertEqual(load_play("hamlet", data_dir=d1).title, "One")
            self.assertEqual(load_play("hamlet", data_dir=d2).title, "Two")

    def test_fallback_citation_only_for_hamlet(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            set_plays_directory(d)
            self.assertEqual(get_source_citation("Hamlet")["url"], "https://www.gutenberg.org/ebooks/1524")
            with self.assertRaises(FileNotFoundError):
                get_source_citation("Macbeth")

    def test_min_score_applies_to_exact_paths(self) -> None:
        match = find_passage("To be, or not to be", play="Hamlet", min_score=0.99)
        self.assertTrue(match is None or match.score >= 0.99)

    def test_min_score_rejects_multiline_passage(self) -> None:
        # Multi-line path uses a hardcoded score of 0.92; min_score=0.99 must reject it.
        passage = (
            "To be, or not to be, question:\n"
            "Whether 'tis nobler in mind suffer\n"
            "The slings arrows of outrageous fortune"
        )
        self.assertIsNone(find_passage(passage, play="Hamlet", min_score=0.99))
        # With a permissive threshold the same passage still matches.
        match = find_passage(passage, play="Hamlet", min_score=0.90)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertGreaterEqual(match.score, 0.90)

    def test_ocr_every_word_error_short_query(self) -> None:
        """Verify short queries where every word has an OCR character error can still match."""
        with tempfile.TemporaryDirectory() as d:
            lines = [
                {"type": "line", "line": 1, "speaker": "HAMLET", "text": "To be."},
                {"type": "line", "line": 2, "speaker": "HAMLET", "text": "Or not to be."},
            ]
            play = {
                "id": "t", "title": "T",
                "acts": [{"act": 1, "act_roman": "I", "scenes": [
                    {"scene": 1, "scene_roman": "I", "lines": lines}]}],
            }
            (Path(d) / "t.json").write_text(json.dumps(play), encoding="utf-8")
            # "T0 bc" is an OCR misread of "To be" — every word has a character substitution
            match = find_passage("T0 bc", play="t", data_dir=d, min_score=0.6)
            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match.line_start, 1)
            self.assertGreaterEqual(match.score, 0.6)

    def test_unrelated_short_query_returns_none(self) -> None:
        """Verify a clearly unrelated short query returns None even after the prefilter is relaxed."""
        with tempfile.TemporaryDirectory() as d:
            lines = [
                {"type": "line", "line": 1, "speaker": "HAMLET", "text": "To be."},
                {"type": "line", "line": 2, "speaker": "HAMLET", "text": "Or not to be."},
            ]
            play = {
                "id": "t", "title": "T",
                "acts": [{"act": 1, "act_roman": "I", "scenes": [
                    {"scene": 1, "scene_roman": "I", "lines": lines}]}],
            }
            (Path(d) / "t.json").write_text(json.dumps(play), encoding="utf-8")
            # "xyzzy quux" shares no meaningful characters with the play lines
            self.assertIsNone(find_passage("xyzzy quux", play="t", data_dir=d, min_score=0.6))

    def test_exact_line_beats_partial_word_match(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            lines = [
                {"type": "line", "line": 1, "speaker": "A", "text": "Who's there?"},
                {"type": "line", "line": 2, "speaker": "B", "text": "He."},
            ]
            play = {
                "id": "t", "title": "T",
                "acts": [{"act": 1, "act_roman": "I", "scenes": [
                    {"scene": 1, "scene_roman": "I", "lines": lines}]}],
            }
            (Path(d) / "t.json").write_text(json.dumps(play), encoding="utf-8")
            match = find_passage("He.", play="t", data_dir=d)
            assert match is not None
            self.assertEqual(match.line_start, 2)

    def test_short_query_word_overlap_beats_char_similarity(self) -> None:
        """Verify short query uses fuzzy word overlap: slings line wins over unrelated short line."""
        with tempfile.TemporaryDirectory() as d:
            lines = [
                {"type": "line", "line": 1, "speaker": "A", "text": "The King, sir."},
                {"type": "line", "line": 5, "speaker": "B", "text": "The slings and arrows of outrageous fortune."},
            ]
            play = {
                "id": "t", "title": "T",
                "acts": [{"act": 1, "act_roman": "I", "scenes": [
                    {"scene": 1, "scene_roman": "I", "lines": lines}]}],
            }
            (Path(d) / "t.json").write_text(json.dumps(play), encoding="utf-8")
            # "the slings arrows" (missing "and") must locate the slings line, not "The King, sir."
            match = find_passage("the slings arrows", play="t", data_dir=d, min_score=0.6)
            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match.line_start, 5)
            self.assertGreaterEqual(match.score, 0.6)
            # Confirm the unrelated short line is not returned
            self.assertNotEqual(match.line_start, 1)


    def test_ocr_30line_passage_queston(self) -> None:
        """30-line passage with one OCR error (question→queston) must locate Act 3, Scene 1, lines 64-93."""
        import time
        play = load_play("Hamlet")
        lines_data = []
        for act in play.acts:
            if act.act == 3:
                for scene in act.scenes:
                    if scene.scene == 1:
                        for line in scene.lines:
                            if line.type == "line" and 64 <= line.line <= 93:
                                lines_data.append(line.text)
        self.assertEqual(len(lines_data), 30)
        query = "\n".join(lines_data).replace("question", "queston")
        t0 = time.time()
        match = find_passage(query, play="Hamlet")
        elapsed = time.time() - t0
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)
        self.assertEqual(match.line_start, 64)
        self.assertEqual(match.line_end, 93)
        self.assertLess(elapsed, 3.0, f"queston query took {elapsed:.2f}s, expected < 3s")

    def test_unknown_book_raises_file_not_found(self) -> None:
        """Unknown-book calls must raise FileNotFoundError rather than inventing coordinates or returning Hamlet citation."""
        with self.assertRaises(FileNotFoundError):
            load_play("Unknown Book")

        with self.assertRaises(FileNotFoundError):
            get_source_citation("Unknown Book")

        with self.assertRaises(FileNotFoundError):
            find_passage("To be, or not to be", play="Unknown Book")


if __name__ == "__main__":
    unittest.main()
