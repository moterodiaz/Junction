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

# Study notes live next to the play as <play>_notes.json and are not plays themselves.
NOTES_SUFFIX = "_notes"

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


def strip_ocr_artefacts(text: str) -> str:
    """Strip OCR artefacts before scoring: speaker prefixes, bare line numbers, and stage directions."""
    if not text:
        return ""
    # 1. Bracketed stage directions like [Enter Hamlet.], [Exit.], etc.
    cleaned = re.sub(r"\[[^\]]*\]", " ", text)
    # 2. Unbracketed stage directions like Enter Hamlet, Exit, Exeunt at start of line
    cleaned = re.sub(r"(?im)^\s*(?:enter|exit|exeunt|re-enter)\b[^\n]*$", " ", cleaned)
    # 3. All-caps speaker prefixes like HAMLET., SPEAKER., KING., FIRST CLOWN.
    # ponytail: cap at 3 words + start-of-line so multi-word uppercase dialogue (e.g. "WORDS WITHOUT THOUGHTS NEVER TO HEAVEN GO.") is not stripped
    cleaned = re.sub(r"(?m)^\s*[A-Z]{2,}(?:\s+[A-Z]{2,}){0,2}\s*[\.:]\s*", " ", cleaned)
    # 4. Speaker prefixes with colon (e.g. Hamlet:) or Speaker.
    cleaned = re.sub(r"\b(?:[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s*:|Speaker\s*[\.:])\s*", " ", cleaned)
    # 5. Bare line numbers / margin numbers
    cleaned = re.sub(r"\b\d+\b", " ", cleaned)
    return cleaned


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
    words_set: frozenset[str] = field(default_factory=frozenset)


@dataclass
class SceneIndex:
    act: int
    scene: int
    act_roman: str
    scene_roman: str
    scene_desc: str
    start_idx: int
    end_idx: int
    norm_text: str
    words_set: frozenset[str]


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
    _scenes: List[SceneIndex] = field(default_factory=list, repr=False)
    notes: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self._indexed_lines or not getattr(self, "_scenes", None):
            self._build_index()

    def _build_index(self) -> None:
        flat: List[FlatLineIndex] = []
        scenes: List[SceneIndex] = []
        for act in self.acts:
            for scene in act.scenes:
                scene_start = len(flat)
                scene_lines_flat: List[FlatLineIndex] = []
                for line in scene.lines:
                    if line.type == "line" and line.text:
                        norm = normalize_text(line.text)
                        item = FlatLineIndex(
                            act=act.act,
                            scene=scene.scene,
                            act_roman=act.act_roman,
                            scene_roman=scene.scene_roman,
                            scene_desc=scene.location_desc,
                            line=line.line,
                            speaker=line.speaker,
                            text=line.text,
                            norm=norm,
                            words_set=frozenset(norm.split()),
                        )
                        flat.append(item)
                        scene_lines_flat.append(item)
                if scene_lines_flat:
                    scene_end = len(flat)
                    norm_text = " " + " ".join(item.norm for item in scene_lines_flat) + " "
                    scene_words = frozenset().union(*(item.words_set for item in scene_lines_flat))
                    scenes.append(
                        SceneIndex(
                            act=act.act,
                            scene=scene.scene,
                            act_roman=act.act_roman,
                            scene_roman=scene.scene_roman,
                            scene_desc=scene.location_desc,
                            start_idx=scene_start,
                            end_idx=scene_end,
                            norm_text=norm_text,
                            words_set=scene_words,
                        )
                    )
        self._indexed_lines = flat
        self._scenes = scenes

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
        if file.stem.endswith(NOTES_SUFFIX):
            continue
        plays.append(file.stem)
    return plays


def _load_notes_file(play_file: Path) -> Optional[Dict[Tuple[int, int], Dict[str, Any]]]:
    """Read <play>_notes.json next to the play file; a missing or unreadable file yields None."""
    notes_file = play_file.with_name(f"{play_file.stem}{NOTES_SUFFIX}.json")
    if not notes_file.is_file():
        return None
    try:
        with open(notes_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        notes: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for entry in data.get("scenes", []):
            notes[(int(entry["act"]), int(entry["scene"]))] = entry
        return notes or None
    except Exception as exc:
        log.warning("ignoring unreadable notes file %s: %s", notes_file.name, type(exc).__name__)
        return None


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
    if key.endswith(NOTES_SUFFIX):
        raise FileNotFoundError(f"Play '{play_name_or_id}' not found in {dir_path}")
    if not target_file.is_file():
        # Search all json files for matching ID or Title
        matching_file: Optional[Path] = None
        for candidate in dir_path.glob("*.json"):
            if candidate.stem.endswith(NOTES_SUFFIX):
                continue
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
    play.notes = _load_notes_file(target_file)
    _play_cache[cache_key] = play
    _play_cache[f"{dir_path}::{play.id.lower()}"] = play
    _play_cache[f"{dir_path}::{play.title.lower()}"] = play
    return play


get_play = load_play


def _play_for_match(match: "PassageMatch", data_dir: Optional[Path | str] = None) -> Optional[Play]:
    try:
        return load_play(match.play_id, data_dir=data_dir)
    except Exception as exc:
        log.warning("play for match not loadable: %s", type(exc).__name__)
        return None


def get_scene_notes(match: "PassageMatch", data_dir: Optional[Path | str] = None) -> Optional[Dict[str, Any]]:
    """Study notes for the matched scene, or None when the play has no notes file or no entry."""
    play = _play_for_match(match, data_dir)
    if play is None or not play.notes:
        return None
    return play.notes.get((match.act, match.scene))


@dataclass
class ContextWindow:
    before: List[FlatLineIndex]
    matched: List[FlatLineIndex]
    after: List[FlatLineIndex]

    @property
    def lines(self) -> List[FlatLineIndex]:
        return self.before + self.matched + self.after


def context_window(
    match: "PassageMatch",
    before: int = 6,
    after: int = 6,
    data_dir: Optional[Path | str] = None,
) -> Optional[ContextWindow]:
    """Canonical lines around a match, clipped to the matched scene (never crosses a scene boundary)."""
    play = _play_for_match(match, data_dir)
    if play is None:
        return None
    sc = next((s for s in play._scenes if s.act == match.act and s.scene == match.scene), None)
    if sc is None:
        return None
    sc_lines = play._indexed_lines[sc.start_idx : sc.end_idx]
    idx = [i for i, l in enumerate(sc_lines) if match.line_start <= l.line <= match.line_end]
    if not idx:
        return None
    first, last = idx[0], idx[-1]
    return ContextWindow(
        before=sc_lines[max(0, first - max(0, before)) : first],
        matched=sc_lines[first : last + 1],
        after=sc_lines[last + 1 : last + 1 + max(0, after)],
    )


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


def _match_single_chunk(
    chunk_norm_text: str,
    loaded_play: Play,
    min_score: float = 0.45,
) -> Optional[PassageMatch]:
    lines = loaded_play._indexed_lines
    if not lines:
        return None
    q_words = chunk_norm_text.split()
    if not q_words:
        return None
    q_words_set = set(q_words)
    len_q = len(chunk_norm_text)
    padded_q = f" {chunk_norm_text} "

    # 1. Exact substring in scene
    if getattr(loaded_play, "_scenes", None):
        first_w = q_words[0]
        for sc in loaded_play._scenes:
            if padded_q in sc.norm_text:
                sc_lines = lines[sc.start_idx : sc.end_idx]
                max_w = min(len(q_words) // 2 + 4, len(sc_lines) + 1)
                for w_len in range(2, max_w):
                    for i in range(len(sc_lines) - w_len + 1):
                        if first_w not in sc_lines[i].norm:
                            continue
                        w_norm = " ".join(sc_lines[i + k].norm for k in range(w_len))
                        if padded_q in f" {w_norm} ":
                            g_start = sc.start_idx + i
                            g_end = g_start + w_len
                            m_lines = lines[g_start:g_end]
                            first, last = m_lines[0], m_lines[-1]
                            loc_str = (
                                f"Act {first.act}, Scene {first.scene}, line {first.line}"
                                if first.line == last.line
                                else f"Act {first.act}, Scene {first.scene}, lines {first.line}-{last.line}"
                            )
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
                                text="\n".join(l.text for l in m_lines),
                                location=loc_str,
                                score=0.95,
                                source=loaded_play.get_source_citation(),
                            )

    # 2. Fast candidate search
    scenes = getattr(loaded_play, "_scenes", None)
    if not scenes:
        return None

    cand_scenes = []
    for sc in scenes:
        ov = len(q_words_set & sc.words_set) / len(q_words_set)
        cand_scenes.append((ov, sc))
    cand_scenes.sort(key=lambda x: x[0], reverse=True)

    best: Optional[PassageMatch] = None
    _best_score = min_score
    max_w = min(len(q_words) // 2 + 3, 14)
    needed = int(0.35 * len(q_words_set))

    for ov, sc in cand_scenes[:2]:
        sc_lines = lines[sc.start_idx : sc.end_idx]
        n_sc = len(sc_lines)
        line_counts = [len(l.words_set & q_words_set) for l in sc_lines]
        candidates = []
        for i in range(n_sc):
            running = 0
            len_w = 0
            w_set: set[str] = set()
            for w in range(1, max_w + 1):
                j = i + w - 1
                if j >= n_sc:
                    break
                l_j = sc_lines[j]
                len_w = (len_w + 1 + len(l_j.norm)) if len_w else len(l_j.norm)
                running += line_counts[j]
                w_set.update(l_j.words_set)
                if running < needed:
                    continue
                tok_sim = len(q_words_set & w_set) / len(q_words_set)
                if tok_sim < 0.4:
                    continue
                rq = 2.0 * min(len_q, len_w) / (len_q + len_w)
                ub = 0.6 * tok_sim + 0.4 * rq
                if ub >= _best_score:
                    candidates.append((ub, tok_sim, i, w))

        candidates.sort(key=lambda c: -c[0])
        for ub, tok_sim, i, w in candidates[:15]:
            if ub < _best_score:
                break
            w_norm = " ".join(sc_lines[k].norm for k in range(i, i + w))
            sm = SequenceMatcher(None, chunk_norm_text, w_norm)
            if 0.6 * tok_sim + 0.4 * sm.quick_ratio() < _best_score:
                continue
            sr = sm.ratio()
            score = 0.6 * tok_sim + 0.4 * sr
            if score >= min_score and score > _best_score:
                _best_score = score
                m_lines = lines[sc.start_idx + i : sc.start_idx + i + w]
                first, last = m_lines[0], m_lines[-1]
                loc_str = (
                    f"Act {first.act}, Scene {first.scene}, line {first.line}"
                    if first.line == last.line
                    else f"Act {first.act}, Scene {first.scene}, lines {first.line}-{last.line}"
                )
                best = PassageMatch(
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
                    text="\n".join(l.text for l in m_lines),
                    location=loc_str,
                    score=score,
                    source=loaded_play.get_source_citation(),
                )
        if _best_score >= 0.70:
            break

    return best


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

    cleaned_query = strip_ocr_artefacts(query)
    norm_query = normalize_text(cleaned_query)
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

    # Chunk and vote for long queries (> 60 words) to handle scene breaks, full pages, and stay under 0.3s
    if len(query_words) > 60:
        chunk_size = 40
        stride = 35
        chunks = []
        for idx in range(0, len(query_words), stride):
            cw = query_words[idx : idx + chunk_size]
            if len(cw) >= 15:
                chunks.append(" ".join(cw))
            elif chunks:
                chunks[-1] += " " + " ".join(cw)
        if not chunks:
            chunks = [" ".join(query_words)]

        votes: Dict[Tuple[int, int], List[PassageMatch]] = {}
        for ch in chunks:
            m = _match_single_chunk(ch, loaded_play, min_score=0.45)
            if m:
                key = (m.act, m.scene)
                votes.setdefault(key, []).append(m)

        if votes:
            winning_key = max(votes.keys(), key=lambda k: (len(votes[k]), sum(m.score for m in votes[k])))
            winning_matches = votes[winning_key]
            line_start = min(m.line_start for m in winning_matches)
            line_end = max(m.line_end for m in winning_matches)
            best_score = max(m.score for m in winning_matches)
            if best_score >= min_score:
                matched_lines = [
                    l for l in lines
                    if l.act == winning_key[0] and l.scene == winning_key[1] and line_start <= l.line <= line_end
                ]
                first = matched_lines[0] if matched_lines else winning_matches[0]
                last = matched_lines[-1] if matched_lines else winning_matches[-1]
                loc_str = (
                    f"Act {winning_key[0]}, Scene {winning_key[1]}, line {line_start}"
                    if line_start == line_end
                    else f"Act {winning_key[0]}, Scene {winning_key[1]}, lines {line_start}-{line_end}"
                )
                combined_text = (
                    "\n".join(l.text for l in matched_lines)
                    if matched_lines
                    else "\n".join(m.text for m in winning_matches)
                )
                return PassageMatch(
                    play_id=loaded_play.id,
                    play_title=loaded_play.title,
                    author=loaded_play.author,
                    act=winning_key[0],
                    scene=winning_key[1],
                    act_roman=first.act_roman,
                    scene_roman=first.scene_roman,
                    line_start=line_start,
                    line_end=line_end,
                    speaker=first.speaker or None,
                    text=combined_text,
                    location=loc_str,
                    score=best_score,
                    source=loaded_play.get_source_citation(),
                )

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
    if 0.92 >= min_score and getattr(loaded_play, "_scenes", None):
        first_word = query_words[0]
        cand_scenes = [sc for sc in loaded_play._scenes if padded_query in sc.norm_text]
        # Shortest span across all scenes wins, so window size is the outer loop.
        for window_size in range(2, max_window_lines + 1):
            for sc in cand_scenes:
                sc_lines = lines[sc.start_idx : sc.end_idx]
                n_sc = len(sc_lines)
                if window_size > n_sc:
                    continue
                for i in range(n_sc - window_size + 1):
                    # To be the shortest matching window, the first line must contain the first word
                    if first_word not in sc_lines[i].norm:
                        continue
                    window_norm = " ".join(sc_lines[i + k].norm for k in range(window_size))
                    if padded_query in f" {window_norm} ":
                        global_start = sc.start_idx + i
                        global_end = global_start + window_size
                        matched_lines = lines[global_start:global_end]
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

    if getattr(loaded_play, "_scenes", None):
        scenes_to_search = loaded_play._scenes
    else:
        # Fallback if _scenes was not initialized
        scenes_to_search = [
            SceneIndex(
                act=lines[0].act,
                scene=lines[0].scene,
                act_roman=lines[0].act_roman,
                scene_roman=lines[0].scene_roman,
                scene_desc=lines[0].scene_desc,
                start_idx=0,
                end_idx=len(lines),
                norm_text=" " + " ".join(l.norm for l in lines) + " ",
                words_set=frozenset().union(*(l.words_set for l in lines)),
            )
        ]

    if _is_short_query:
        for sc in scenes_to_search:
            sc_lines = lines[sc.start_idx : sc.end_idx]
            n_sc = len(sc_lines)
            max_w = min(max_window_lines, n_sc)
            for i in range(n_sc):
                window_norm = ""
                for window_size in range(1, max_w + 1):
                    j = i + window_size - 1
                    if j >= n_sc:
                        break
                    line_j = sc_lines[j]
                    window_norm = (window_norm + " " + line_j.norm) if window_norm else line_j.norm
                    if not window_norm:
                        continue
                    len_w = len(window_norm)
                    real_quick = 2.0 * min(len_query_chars, len_w) / (len_query_chars + len_w)
                    if 0.6 + 0.4 * real_quick < _best_score:
                        continue
                    seq_ratio = SequenceMatcher(None, norm_query, window_norm).ratio()
                    fuzzy_tok_sim = _fuzzy_token_similarity(query_words, window_norm)
                    combined_score = 0.6 * fuzzy_tok_sim + 0.4 * seq_ratio
                    if combined_score >= min_score:
                        if best_candidate is None or combined_score > best_candidate[0]:
                            best_candidate = (combined_score, sc.start_idx + i, sc.start_idx + i + window_size)
                            _best_score = combined_score
    else:
        needed_words = int(0.4 * len(query_words_set))
        scene_candidates = []
        for sc in scenes_to_search:
            overlap = len(query_words_set & sc.words_set) / len(query_words_set)
            if 0.6 * overlap + 0.4 >= _best_score:
                scene_candidates.append((overlap, sc))

        # Sort scenes with highest word overlap first to establish a tight _best_score quickly
        scene_candidates.sort(key=lambda s: s[0], reverse=True)

        for overlap, sc in scene_candidates:
            if 0.6 * overlap + 0.4 < _best_score:
                break

            sc_lines = lines[sc.start_idx : sc.end_idx]
            n_sc = len(sc_lines)
            max_w = min(max_window_lines, n_sc)
            start_offset = sc.start_idx
            line_query_counts = [len(l.words_set & query_words_set) for l in sc_lines]

            candidates = []
            for i in range(n_sc):
                running_q_count = 0
                len_w = 0
                window_words_set: set = set()
                for w in range(1, max_w + 1):
                    j = i + w - 1
                    if j >= n_sc:
                        break
                    line_j = sc_lines[j]
                    len_w = (len_w + 1 + len(line_j.norm)) if len_w else len(line_j.norm)
                    running_q_count += line_query_counts[j]
                    window_words_set.update(line_j.words_set)
                    if running_q_count < needed_words:
                        continue
                    tok_sim = len(query_words_set & window_words_set) / len(query_words_set)
                    if tok_sim < 0.4:
                        continue
                    real_quick = 2.0 * min(len_query_chars, len_w) / (len_query_chars + len_w)
                    upper_bound = 0.6 * tok_sim + 0.4 * real_quick
                    if upper_bound >= _best_score:
                        candidates.append((upper_bound, tok_sim, real_quick, i, w, len_w))

            # Sort candidate windows by upper bound descending, tie-breaking by i ascending, w ascending
            candidates.sort(key=lambda c: (-c[0], c[3], c[4]))

            for upper_bound, tok_sim, real_quick, i, w, len_w in candidates[:30]:
                if upper_bound < _best_score:
                    break
                window_norm = " ".join(sc_lines[k].norm for k in range(i, i + w))
                sm = SequenceMatcher(None, norm_query, window_norm)
                if 0.6 * tok_sim + 0.4 * sm.quick_ratio() < _best_score:
                    continue
                seq_ratio = sm.ratio()
                combined_score = 0.6 * tok_sim + 0.4 * seq_ratio
                if combined_score >= min_score:
                    if best_candidate is None or combined_score > best_candidate[0]:
                        best_candidate = (combined_score, start_offset + i, start_offset + i + w)
                        _best_score = combined_score

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
