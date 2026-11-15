"""Hamlet scene notes feed the reasoning prompt (#259, REQ-SRC-01, REQ-REASON-01)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest import mock

from ai import make_notes
from ai.reasoning import HttpGeminiClient, build_scene_notes_block
from ai.session import BookInfo, BookSession
from ai.source_loader import (
    DEFAULT_DATA_DIR,
    PassageMatch,
    context_window,
    find_passage,
    get_scene_notes,
    list_plays,
    load_play,
    set_plays_directory,
)

PLAY_JSON = DEFAULT_DATA_DIR / "hamlet.json"
NOTES_JSON = DEFAULT_DATA_DIR / "hamlet_notes.json"

# Hamlet 3.1, the "bodkin" lines of the soliloquy.
BODKIN_PAGE = (
    "When he himself might his quietus make\n"
    "With a bare bodkin? Who would these fardels bear,\n"
    "To grunt and sweat under a weary life,"
)


def _match(act: int, scene: int, start: int, end: int) -> PassageMatch:
    return PassageMatch(
        play_id="hamlet", play_title="Hamlet", author="William Shakespeare",
        act=act, scene=scene, act_roman="", scene_roman="",
        line_start=start, line_end=end, speaker=None, text="",
        location=f"Act {act}, Scene {scene}, lines {start}-{end}", score=1.0, source={},
    )


async def _captured_prompt(page_text: str, passage_match: Any) -> str:
    client = HttpGeminiClient(api_key="test-api-key")
    session = BookSession("s-notes", book=BookInfo(title="Hamlet", location="Act 3, Scene 1"))
    captured: Dict[str, Any] = {}

    def fake_urlopen(req, timeout=None):
        captured.update(json.loads(req.data.decode("utf-8")))
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({
            "title": "Hamlet", "caption": "c", "speech_text": "s",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": ""}, "sources": [],
        })}]}}]}).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        await client.generate_reasoning("What does bodkin mean?", page_text, session, passage_match=passage_match)
    return captured["contents"][-1]["parts"][0]["text"]


class NotesFileTest(unittest.TestCase):
    def test_notes_file_validates_against_hamlet_json(self) -> None:
        self.assertEqual(make_notes.validate(PLAY_JSON, NOTES_JSON), [])
        notes = json.loads(NOTES_JSON.read_text(encoding="utf-8"))["scenes"]
        play = load_play("Hamlet", force_reload=True)
        play_scenes = {(a.act, s.scene) for a in play.acts for s in a.scenes}
        self.assertEqual(len(notes), 20)
        self.assertEqual({(n["act"], n["scene"]) for n in notes}, play_scenes)
        self.assertEqual(set(play.notes or {}), play_scenes)

    def test_validator_rejects_term_missing_from_scene(self) -> None:
        notes = json.loads(NOTES_JSON.read_text(encoding="utf-8"))
        notes["scenes"][0]["glossary"].append({"term": "bodkin", "gloss": "dagger"})
        notes["scenes"].pop()
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "hamlet_notes.json"
            bad.write_text(json.dumps(notes), encoding="utf-8")
            errors = make_notes.validate(PLAY_JSON, bad)
        self.assertIn("Act 1, Scene 1: glossary term 'bodkin' does not occur in the scene text", errors)
        self.assertIn("Act 5, Scene 2: no notes entry", errors)

    def test_skeleton_lists_every_scene(self) -> None:
        sk = make_notes.skeleton(PLAY_JSON)
        self.assertEqual(len(sk["scenes"]), 20)

    def test_notes_file_is_not_listed_as_a_play(self) -> None:
        self.assertIn("hamlet", list_plays())
        self.assertNotIn("hamlet_notes", list_plays())

    def test_notes_file_cannot_be_loaded_directly_as_a_play(self) -> None:
        from ai.source_loader import load_play
        with self.assertRaises(FileNotFoundError):
            load_play("hamlet_notes")


class ContextWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        set_plays_directory(None)

    def test_window_has_six_lines_each_side_inside_a_scene(self) -> None:
        w = context_window(_match(3, 1, 70, 72))
        assert w is not None
        self.assertEqual([l.line for l in w.before], list(range(64, 70)))
        self.assertEqual([l.line for l in w.matched], [70, 71, 72])
        self.assertEqual([l.line for l in w.after], list(range(73, 79)))

    def test_window_stops_at_the_end_of_a_scene(self) -> None:
        last = load_play("Hamlet").acts[0].scenes[0].spoken_lines[-1].line
        w = context_window(_match(1, 1, last - 1, last))
        assert w is not None
        self.assertEqual(w.after, [])
        self.assertEqual(len(w.before), 6)
        self.assertTrue(all((l.act, l.scene) == (1, 1) for l in w.lines))

    def test_window_stops_at_the_start_of_a_scene(self) -> None:
        w = context_window(_match(1, 2, 1, 2))
        assert w is not None
        self.assertEqual(w.before, [])
        self.assertEqual(len(w.after), 6)
        self.assertTrue(all((l.act, l.scene) == (1, 2) for l in w.lines))


class NotesPromptTest(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        set_plays_directory(None)

    async def test_prompt_contains_notes_block_when_passage_matched(self) -> None:
        match = find_passage(BODKIN_PAGE, play="Hamlet")
        assert match is not None
        self.assertEqual((match.act, match.scene), (3, 1))
        prompt = await _captured_prompt(BODKIN_PAGE, match)
        notes = get_scene_notes(match)
        assert notes is not None
        w = context_window(match)
        assert w is not None
        self.assertIn("Authoritative Scene Notes", prompt)
        self.assertIn(notes["summary"], prompt)
        self.assertIn("Do NOT recall the play from memory", prompt)
        self.assertIn("bodkin: dagger", prompt)
        self.assertIn("quietus: release", prompt)
        self.assertNotIn("nunnery:", prompt)
        self.assertIn(w.before[0].text, prompt)
        self.assertIn(w.after[-1].text, prompt)
        self.assertEqual(prompt.count("Authoritative Scene Notes"), 1)

    async def test_prompt_has_no_notes_block_without_a_match(self) -> None:
        prompt = await _captured_prompt(BODKIN_PAGE, None)
        self.assertNotIn("Authoritative Scene Notes", prompt)
        self.assertEqual(build_scene_notes_block(None, BODKIN_PAGE), "")

    async def test_missing_notes_file_degrades_to_plain_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(PLAY_JSON, Path(d) / "hamlet.json")
            set_plays_directory(d)
            match = find_passage(BODKIN_PAGE, play="Hamlet")
            assert match is not None
            self.assertIsNone(load_play("Hamlet").notes)
            self.assertIsNone(get_scene_notes(match))
            prompt = await _captured_prompt(BODKIN_PAGE, match)
        self.assertIn("Canonical Grounding", prompt)
        self.assertIn(match.location, prompt)
        self.assertNotIn("Authoritative Scene Notes", prompt)

    def test_unreadable_notes_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(PLAY_JSON, Path(d) / "hamlet.json")
            (Path(d) / "hamlet_notes.json").write_text("{not json", encoding="utf-8")
            set_plays_directory(d)
            self.assertIsNone(load_play("Hamlet").notes)
            self.assertEqual(list_plays(), ["hamlet"])

    def test_malformed_notes_entry_never_breaks_the_prompt(self) -> None:
        match = _match(3, 1, 83, 85)
        bad = {"summary": None, "characters_on_stage": ["Hamlet", 7], "glossary": [{"term": "bodkin", "gloss": "dagger"}]}
        with mock.patch("ai.reasoning.get_scene_notes", return_value=bad):
            block = build_scene_notes_block(match, BODKIN_PAGE)
        self.assertIn("Characters on stage: Hamlet, 7", block)
        self.assertIn("bodkin: dagger", block)
        with mock.patch("ai.reasoning.get_scene_notes", return_value={"summary": "s", "glossary": [{"term": 5}]}):
            self.assertEqual(build_scene_notes_block(match, BODKIN_PAGE), "")


if __name__ == "__main__":
    unittest.main()
