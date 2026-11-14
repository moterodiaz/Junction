"""Public-domain play text loader and passage locator (PRD section 2, section 8, section 10 C4).

Loads structured public-domain play texts (e.g. Hamlet from Project Gutenberg #1524)
to place recognized camera passages by Act, Scene, and Line.
Per Issue #29 and PRD Open Question 7, adding a play is a data-only change:
any .json file in backend/ai/data/plays/ is automatically discovered.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger("metalab.ai.source_loader")

# Default location for public-domain play JSON files
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "plays"

_custom_data_dir: Optional[Path] = None
_play_cache: Dict[str, Play] = {}


def set_plays_directory(path: Optional[Path | str]) -> None:
    """Override the directory scanned for play JSON files (used for testing)."""
    global _custom_data_dir
    if path is not None:
        _custom_data_dir = Path(path).resolve()
    else:
        _custom_data_dir = None
    _play_cache.clear()


def get_plays_directory() -> Path:
    """Get the active directory containing play data files."""
    if _custom_data_dir is not None:
        return _custom_data_dir
    return DEFAULT_DATA_DIR


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation, and collapsing whitespace."""
    if not text:
        return ""
    # Replace smart quotes, apostrophes, dashes, and punctuation with spaces
    cleaned = re.sub(r"[\x27\u2019\u2018\"\u201c\u201d.,;:!?()\[\]\u2014\-_\/\\`]", " ", text.lower())
    return " ".join(cleaned.split())


@dataclass
class Line:
    type: str  # "line" or "stage_direction"
    line: int = 0
    speaker: str = ""
    text: str = ""
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "line": self.line,
            "speaker": self.speaker,
            "text": self.text,
            "raw_text": self.raw_text,
        }


@dataclass
class Scene:
    scene: int
    scene_roman: str
    location_desc: str
    lines: List[Line] = field(default_factory=list)

    @property
    def spoken_lines(self) -> List[Line]:
        return [line for line in self.lines if line.type == "line"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene": self.scene,
            "scene_roman": self.scene_roman,
            "location_desc": self.location_desc,
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass
class Act:
    act: int
    act_roman: str
    scenes: List[Scene] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "act": self.act,
            "act_roman": self.act_roman,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


@dataclass
class FlatLineIndex:
    act: int
    scene: int
    act_roman: str
    scene_roman: str
    scene_desc: str
    line: int
    speaker: str
    text: str
    norm: str


@dataclass
class Play:
    id: str
    title: str
    full_title: str
    author: str
    source_url: str
    license: str
    acts: List[Act] = field(default_factory=list)
    _indexed_lines: List[FlatLineIndex] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self._indexed_lines:
            self._build_index()

    def _build_index(self) -> None:
        flat: List[FlatLineIndex] = []
        for act in self.acts:
            for scene in act.scenes:
                for line in scene.lines:
                    if line.type == "line" and line.text:
                        flat.append(
                            FlatLineIndex(
                                act=act.act,
                                scene=scene.scene,
                                act_roman=act.act_roman,
                                scene_roman=scene.scene_roman,
                                scene_desc=scene.location_desc,
                                line=line.line,
                                speaker=line.speaker,
                                text=line.text,
                                norm=normalize_text(line.text),
                            )
                        )
        self._indexed_lines = flat

    @property
    def total_lines(self) -> int:
        return len(self._indexed_lines)

    def get_source_citation(self) -> Dict[str, str]:
        return {
            "title": f"{self.title}, public-domain text",
            "url": self.source_url,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "full_title": self.full_title,
            "author": self.author,
            "source_url": self.source_url,
            "license": self.license,
            "acts": [act.to_dict() for act in self.acts],
        }


@dataclass
class PassageMatch:
    play_id: str
    play_title: str
    author: str
    act: int
    scene: int
    act_roman: str
    scene_roman: str
    line_start: int
    line_end: int
    speaker: Optional[str]
    text: str
    location: str
    score: float
    source: Dict[str, str]

    @property
    def book_location(self) -> str:
        """Coarse location string for Book schema (e.g. 'Act 3, Scene 1')."""
        return f"Act {self.act}, Scene {self.scene}"

    @property
    def card_title(self) -> str:
        """Card title string (e.g. 'Hamlet, Act 3, Scene 1')."""
        return f"{self.play_title}, Act {self.act}, Scene {self.scene}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "play": self.play_title,
            "title": self.play_title,
            "author": self.author,
            "act": self.act,
            "scene": self.scene,
            "line": self.line_start,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "location": self.location,
            "book_location": self.book_location,
            "speaker": self.speaker,
            "text": self.text,
            "score": round(self.score, 3),
            "source": self.source,
        }


def _parse_play_json(data: Dict[str, Any]) -> Play:
    acts: List[Act] = []
    for act_data in data.get("acts", []):
        scenes: List[Scene] = []
        for scene_data in act_data.get("scenes", []):
            lines: List[Line] = []
            for line_data in scene_data.get("lines", []):
                lines.append(
                    Line(
                        type=line_data.get("type", "line"),
                        line=line_data.get("line", 0),
                        speaker=line_data.get("speaker", ""),
                        text=line_data.get("text", ""),
                        raw_text=line_data.get("raw_text", line_data.get("text", "")),
                    )
                )
            scenes.append(
                Scene(
                    scene=scene_data.get("scene", 1),
                    scene_roman=scene_data.get("scene_roman", "I"),
                    location_desc=scene_data.get("location_desc", ""),
                    lines=lines,
                )
            )
        acts.append(
            Act(
                act=act_data.get("act", 1),
                act_roman=act_data.get("act_roman", "I"),
                scenes=scenes,
            )
        )

    return Play(
        id=data.get("id", "unknown"),
        title=data.get("title", "Untitled Play"),
        full_title=data.get("full_title", data.get("title", "Untitled Play")),
        author=data.get("author", "Unknown"),
        source_url=data.get("source_url", ""),
        license=data.get("license", "Public Domain"),
        acts=acts,
    )


def list_plays(data_dir: Optional[Path | str] = None) -> List[str]:
    """List IDs of all registered plays in the plays directory."""
    dir_path = Path(data_dir).resolve() if data_dir else get_plays_directory()
    if not dir_path.is_dir():
        return []
    plays: List[str] = []
    for file in sorted(dir_path.glob("*.json")):
        plays.append(file.stem)
    return plays


def load_play(
    play_name_or_id: str = "Hamlet",
    data_dir: Optional[Path | str] = None,
    force_reload: bool = False,
) -> Play:
    """Load a play by ID or title from the data directory.

    Caches loaded plays in memory. Case-insensitive lookup.
    """
    key = play_name_or_id.strip().lower()
    dir_path = Path(data_dir).resolve() if data_dir else get_plays_directory()
    cache_key = f"{dir_path}::{key}"
    if not force_reload and cache_key in _play_cache:
        return _play_cache[cache_key]

    if not dir_path.is_dir():
        raise FileNotFoundError(f"Plays directory not found: {dir_path}")

    # 1. Exact or lowercase filename match (<name>.json)
    target_file = dir_path / f"{key}.json"
    if not target_file.is_file():
        # Search all json files for matching ID or Title
        matching_file: Optional[Path] = None
        for candidate in dir_path.glob("*.json"):
            if candidate.stem.lower() == key:
                matching_file = candidate
                break
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    preview = json.load(f)
                    if (
                        preview.get("id", "").lower() == key
                        or preview.get("title", "").lower() == key
                    ):
                        matching_file = candidate
                        break
            except Exception:
                continue

        if matching_file is None:
            available = list_plays(dir_path)
            raise FileNotFoundError(
                f"Play '{play_name_or_id}' not found in {dir_path}. Available: {available}"
            )
        target_file = matching_file

    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    play = _parse_play_json(data)
    _play_cache[cache_key] = play
    _play_cache[f"{dir_path}::{play.id.lower()}"] = play
    _play_cache[f"{dir_path}::{play.title.lower()}"] = play
    return play


get_play = load_play


def get_source_citation(play: str = "Hamlet") -> Dict[str, str]:
    """Return the source citation dictionary for a play per the Card schema."""
    try:
        loaded = load_play(play)
        return loaded.get_source_citation()
    except Exception:
        if play.strip().lower() != "hamlet":
            raise
        # Fallback citation for Hamlet if file not loaded
        return {
            "title": f"{play}, public-domain text",
            "url": "https://www.gutenberg.org/ebooks/1524",
        }


def _token_similarity(s1: str, s2: str) -> float:
    """Compute token Jaccard overlap similarity between two normalized strings."""
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    return len(intersection) / len(tokens1)


@lru_cache(maxsize=262144)
def _word_ratio(a: str, b: str) -> float:
    """Memoized SequenceMatcher ratio; windows overlap so pairs repeat heavily."""
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_token_similarity(query_words: List[str], window_norm: str, threshold: float = 0.5) -> float:
    """Fraction of query words with a best per-word SequenceMatcher ratio >= threshold."""
    # ponytail: O(q*w) per window; fine for <=4-word queries; switch to index if longer
    window_words = window_norm.split()
    if not query_words or not window_words:
        return 0.0
    matched = sum(
        1 for qw in query_words
        if max(_word_ratio(qw, ww) for ww in set(window_words)) >= threshold
    )
    return matched / len(query_words)


def find_passage(
    query: str,
    play: Optional[str] = "Hamlet",
    min_score: float = 0.5,
    max_window_lines: int = 6,
    data_dir: Optional[Path | str] = None,
) -> Optional[PassageMatch]:
    """Locate a query passage within a play by Act, Scene, and Line.

    Handles exact matches, normalized punctuation/case mismatches, multi-line passages,
    and fuzzy matching for OCR-transcribed camera frames.

    If play is None, searches all registered plays and returns the best match.
    """
    if not query or not query.strip():
        return None

    norm_query = normalize_text(query)
    query_words = norm_query.split()
    if not query_words:
        return None

    # Search all plays if play is None
    if play is None:
        best_match: Optional[PassageMatch] = None
        for play_id in list_plays(data_dir=data_dir):
            match = find_passage(
                query=query,
                play=play_id,
                min_score=min_score,
                max_window_lines=max_window_lines,
                data_dir=data_dir,
            )
            if match and (best_match is None or match.score > best_match.score):
                best_match = match
        return best_match

    loaded_play = load_play(play, data_dir=data_dir)
    lines = loaded_play._indexed_lines
    if not lines:
        return None

    # 1. Exact normalized single-line match
    # Whole-line equality wins over word-bounded partial matches.
    padded_query = f" {norm_query} "
    ordered = [i for i in lines if i.norm == norm_query] + [
        i for i in lines if i.norm != norm_query and padded_query in f" {i.norm} "
    ]
    for item in ordered:
        score = 1.0 if norm_query == item.norm else 0.95
        if score >= min_score:
            loc_str = f"Act {item.act}, Scene {item.scene}, line {item.line}"
            return PassageMatch(
                play_id=loaded_play.id,
                play_title=loaded_play.title,
                author=loaded_play.author,
                act=item.act,
                scene=item.scene,
                act_roman=item.act_roman,
                scene_roman=item.scene_roman,
                line_start=item.line,
                line_end=item.line,
                speaker=item.speaker or None,
                text=item.text,
                location=loc_str,
                score=score,
                source=loaded_play.get_source_citation(),
            )

    # Size the window from the query so full-page transcripts can match.
    max_window_lines = max(max_window_lines, min(len(query_words) // 2 + 2, 60))

    # 2. Multi-line window search (exact normalized substring)
    total = len(lines)
    for window_size in range(2, max_window_lines + 1):
        for i in range(total - window_size + 1):
            # Must be within the same scene
            if lines[i].act != lines[i + window_size - 1].act or lines[i].scene != lines[i + window_size - 1].scene:
                continue
            window_norm = " ".join(lines[i + k].norm for k in range(window_size))
            if 0.92 >= min_score and padded_query in f" {window_norm} ":
                matched_lines = lines[i : i + window_size]
                first = matched_lines[0]
                last = matched_lines[-1]
                loc_str = (
                    f"Act {first.act}, Scene {first.scene}, line {first.line}"
                    if first.line == last.line
                    else f"Act {first.act}, Scene {first.scene}, lines {first.line}-{last.line}"
                )
                combined_text = "\n".join(l.text for l in matched_lines)
                return PassageMatch(
                    play_id=loaded_play.id,
                    play_title=loaded_play.title,
                    author=loaded_play.author,
                    act=first.act,
                    scene=first.scene,
                    act_roman=first.act_roman,
                    scene_roman=first.scene_roman,
                    line_start=first.line,
                    line_end=last.line,
                    speaker=first.speaker or None,
                    text=combined_text,
                    location=loc_str,
                    score=0.92,
                    source=loaded_play.get_source_citation(),
                )

    # 3. Fuzzy token overlap / SequenceMatcher window search for OCR errors or partial speech
    best_candidate: Optional[Tuple[float, int, int]] = None  # (score, start_idx, end_idx)
    # ponytail: short-query threshold ≤ 4 words; raise if OCR errors regularly span longer passages
    _is_short_query = len(query_words) <= 4
    len_query_chars = len(norm_query)
    query_words_set = set(query_words)
    # ponytail: _best_score tightens as we find better candidates, pruning hopeless windows early
    _best_score = min_score

    # Outer loop by start index; inner loop by window_size allows incremental window building
    # and early break when the window crosses a scene boundary.
    for i in range(total):
        window_norm = ""
        window_words_set: set = set()

        for window_size in range(1, max_window_lines + 1):
            j = i + window_size - 1
            if j >= total:
                break
            line_j = lines[j]
            if lines[i].act != line_j.act or lines[i].scene != line_j.scene:
                break  # extending the window further won't re-enter this scene

            # Incremental window text: avoids O(window_size) join per window
            window_norm = (window_norm + " " + line_j.norm) if window_norm else line_j.norm
            if not window_norm:
                continue
            window_words_set.update(line_j.norm.split())

            tok_sim = len(query_words_set & window_words_set) / len(query_words_set)

            if _is_short_query:
                seq_ratio = SequenceMatcher(None, norm_query, window_norm).ratio()
                fuzzy_tok_sim = _fuzzy_token_similarity(query_words, window_norm)
                combined_score = 0.6 * fuzzy_tok_sim + 0.4 * seq_ratio
            else:
                if tok_sim < 0.4:
                    continue
                # real_quick_ratio = 2*min(len_a,len_b)/(len_a+len_b) is a proven upper bound
                # of SequenceMatcher.ratio(); prune before the expensive ratio() call.
                len_w = len(window_norm)
                real_quick = 2.0 * min(len_query_chars, len_w) / (len_query_chars + len_w)
                if 0.6 * tok_sim + 0.4 * real_quick < _best_score:
                    continue
                sm = SequenceMatcher(None, norm_query, window_norm)
                if 0.6 * tok_sim + 0.4 * sm.quick_ratio() < _best_score:
                    continue
                seq_ratio = sm.ratio()
                combined_score = 0.6 * tok_sim + 0.4 * seq_ratio

            if combined_score >= min_score:
                if best_candidate is None or combined_score > best_candidate[0]:
                    best_candidate = (combined_score, i, i + window_size)
                    _best_score = combined_score  # tighten pruning threshold

    if best_candidate is not None:
        score, start_idx, end_idx = best_candidate
        matched_lines = lines[start_idx:end_idx]
        first = matched_lines[0]
        last = matched_lines[-1]
        loc_str = (
            f"Act {first.act}, Scene {first.scene}, line {first.line}"
            if first.line == last.line
            else f"Act {first.act}, Scene {first.scene}, lines {first.line}-{last.line}"
        )
        combined_text = "\n".join(l.text for l in matched_lines)
        return PassageMatch(
            play_id=loaded_play.id,
            play_title=loaded_play.title,
            author=loaded_play.author,
            act=first.act,
            scene=first.scene,
            act_roman=first.act_roman,
            scene_roman=first.scene_roman,
            line_start=first.line,
            line_end=last.line,
            speaker=first.speaker or None,
            text=combined_text,
            location=loc_str,
            score=score,
            source=loaded_play.get_source_citation(),
        )

    return None


locate_passage = find_passage
