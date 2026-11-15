"""Offline helper for per-play study notes (REQ-SRC-01).

Never imported at request time and never touches the network. Notes are
written once (by hand or with a model outside this repo) and committed as
``<play>_notes.json`` next to ``<play>.json``.

Usage (from the repository root or anywhere):
    python3 backend/ai/make_notes.py                      # validate hamlet_notes.json
    python3 backend/ai/make_notes.py --play macbeth       # validate macbeth_notes.json
    python3 backend/ai/make_notes.py --skeleton macbeth   # print an empty notes file for a play
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PLAYS_DIR = Path(__file__).resolve().parent / "data" / "plays"
NOTES_SUFFIX = "_notes"


def _normalize_text():
    # Loaded by path so the tool runs with a bare python3 (ai/__init__ pulls in app deps).
    spec = importlib.util.spec_from_file_location(
        "_notes_source_loader", Path(__file__).resolve().parent / "source_loader.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.normalize_text


def _scene_texts(play: Dict[str, Any]) -> Dict[tuple, Dict[str, Any]]:
    scenes: Dict[tuple, Dict[str, Any]] = {}
    for act in play.get("acts", []):
        for scene in act.get("scenes", []):
            scenes[(act.get("act"), scene.get("scene"))] = scene
    return scenes


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z'\u2018\"])", text.strip()) if s])


def validate(play_json: Path, notes_json: Path) -> List[str]:
    """Return a list of problems; an empty list means the notes file is valid."""
    normalize_text = _normalize_text()
    play = json.loads(play_json.read_text(encoding="utf-8"))
    notes = json.loads(notes_json.read_text(encoding="utf-8"))
    scenes = _scene_texts(play)
    errors: List[str] = []

    entries = notes.get("scenes") if isinstance(notes, dict) else None
    if not isinstance(entries, list):
        return ["notes file must be an object with a 'scenes' list"]

    seen: Dict[tuple, int] = {}
    for i, entry in enumerate(entries):
        key = (entry.get("act"), entry.get("scene"))
        where = f"Act {key[0]}, Scene {key[1]}"
        if key in seen:
            errors.append(f"{where}: duplicate entry")
        seen[key] = i
        if key not in scenes:
            errors.append(f"{where}: not a scene in {play_json.name}")
            continue
        summary = entry.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"{where}: missing summary")
        elif not 3 <= _sentence_count(summary) <= 4:
            errors.append(f"{where}: summary has {_sentence_count(summary)} sentences (want 3-4)")
        for field in ("characters_on_stage", "themes"):
            value = entry.get(field)
            if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
                errors.append(f"{where}: '{field}' must be a non-empty list of strings")
        glossary = entry.get("glossary")
        if not isinstance(glossary, list) or not glossary:
            errors.append(f"{where}: 'glossary' must be a non-empty list")
            continue
        scene_norm = " " + " ".join(
            normalize_text(line.get("text", "")) for line in scenes[key].get("lines", [])
        ) + " "
        for g in glossary:
            term = g.get("term") if isinstance(g, dict) else None
            gloss = g.get("gloss") if isinstance(g, dict) else None
            if not isinstance(term, str) or not term.strip() or not isinstance(gloss, str) or not gloss.strip():
                errors.append(f"{where}: glossary entries need non-empty 'term' and 'gloss'")
                continue
            if f" {normalize_text(term)} " not in scene_norm:
                errors.append(f"{where}: glossary term '{term}' does not occur in the scene text")

    for key in scenes:
        if key not in seen:
            errors.append(f"Act {key[0]}, Scene {key[1]}: no notes entry")
    return errors


def skeleton(play_json: Path) -> Dict[str, Any]:
    play = json.loads(play_json.read_text(encoding="utf-8"))
    return {
        "play_id": play.get("id", play_json.stem),
        "description": "Hand-written study notes; see SOURCES.md.",
        "scenes": [
            {
                "act": act,
                "scene": scene,
                "summary": "",
                "characters_on_stage": [],
                "glossary": [{"term": "", "gloss": ""}],
                "themes": [],
            }
            for (act, scene) in _scene_texts(play)
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--play", default="hamlet", help="play id (file stem in data/plays), default hamlet")
    parser.add_argument("--skeleton", metavar="PLAY", help="print an empty notes skeleton for PLAY and exit")
    parser.add_argument("--dir", default=str(PLAYS_DIR), help="plays directory")
    args = parser.parse_args(argv)
    plays_dir = Path(args.dir)

    if args.skeleton:
        print(json.dumps(skeleton(plays_dir / f"{args.skeleton}.json"), indent=2, ensure_ascii=False))
        return 0

    play_json = plays_dir / f"{args.play}.json"
    notes_json = plays_dir / f"{args.play}{NOTES_SUFFIX}.json"
    errors = validate(play_json, notes_json)
    if errors:
        for e in errors:
            print(f"INVALID {e}")
        return 1
    count = len(json.loads(notes_json.read_text(encoding="utf-8"))["scenes"])
    print(f"OK {notes_json.name}: {count} scenes match {play_json.name}; all glossary terms occur in their scene")
    return 0


if __name__ == "__main__":
    sys.exit(main())
