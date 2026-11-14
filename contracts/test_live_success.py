"""Opt-in #81 success assertions, distinct from schema-only remote conformance.

Local tests use synthetic responses. Live checks require explicit WS_URL and
WS_SUCCESS_CASES; neither media nor model output is printed or saved.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock
from urllib.parse import urlsplit

from test_conformance import VALIDATOR, expected_request_id, load
from test_remote import drive_remote, fake_backend, remote_timeout

MAX_CASE_BYTES = 16 * 1024 * 1024


def https_url(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not (
            parsed.username or parsed.password or parsed.fragment
        )
    except ValueError:
        return False


def load_success_cases(path: str) -> list[dict]:
    """Read externally supplied, cleared inputs, not the placeholder recordings."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_CASE_BYTES + 1)
    if len(raw) > MAX_CASE_BYTES:
        raise ValueError("success cases exceed the 16 MiB limit")
    try:
        cases = json.loads(raw)
        if not isinstance(cases, list) or not 2 <= len(cases) <= 10:
            raise ValueError
        modes = set()
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"send", "expect"}:
                raise ValueError
            frames = case["send"]
            if not isinstance(frames, list) or len(frames) != 1:
                raise ValueError
            frame = frames[0]
            if not isinstance(frame, dict) or set(frame) not in ({"text"}, {"bytes"}):
                raise ValueError
            invoke = next(iter(frame.values()))
            if not isinstance(invoke, dict) or invoke.get("type") != "invoke" or not VALIDATOR.is_valid(invoke):
                raise ValueError
            modes.add("audio" if invoke.get("audio") is not None else "text")
            expected = case["expect"]
            if not isinstance(expected, dict) or set(expected) != {"book", "sources"}:
                raise ValueError
            book = expected["book"]
            if not isinstance(book, dict) or set(book) != {"title", "author", "location"}:
                raise ValueError
            if not all(isinstance(v, str) and v.strip() for v in book.values()):
                raise ValueError
            sources = expected["sources"]
            if not isinstance(sources, list) or not sources:
                raise ValueError
            for source in sources:
                if not isinstance(source, dict) or set(source) != {"title", "url"}:
                    raise ValueError
                if not isinstance(source["title"], str) or not source["title"].strip() or not https_url(source["url"]):
                    raise ValueError
        if modes != {"text", "audio"}:
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        # Do not echo a JSON parser error containing captured input.
        raise ValueError("invalid success cases: need typed and audio invokes with independent book/source expectations") from None
    return cases


def success_problems(case: dict, replies: list[dict]) -> list[str]:
    """Strict one-invocation success; diagnostics never include user content."""
    problems = []
    want_id = expected_request_id(case["send"][0])
    stages = ["transcribing", "reading", "thinking", "drawing"]
    last_stage = -1
    terminals = 0
    for index, reply in enumerate(replies):
        if not isinstance(reply, dict) or not VALIDATOR.is_valid(reply):
            problems.append(f"reply {index}: schema violation")
            continue
        if reply.get("request_id") != want_id:
            problems.append(f"reply {index}: request ID mismatch")
        if terminals:
            problems.append(f"reply {index}: response after terminal")
        if reply["type"] == "status":
            stage = stages.index(reply["stage"])
            if stage <= last_stage:
                problems.append(f"reply {index}: stage out of order")
            last_stage = stage
        else:
            terminals += 1
            if reply["type"] != "card":
                problems.append(f"reply {index}: expected successful card, got error")
                continue
            for field in ("image_url", "audio_url"):
                if not https_url(reply[field]):
                    problems.append(f"reply {index}: missing usable HTTPS {field}")
            if reply["book"] != case["expect"]["book"]:
                problems.append(f"reply {index}: expected book grounding missing")
            for source in case["expect"]["sources"]:
                if source not in reply["sources"]:
                    problems.append(f"reply {index}: expected source citation missing")
    if terminals != 1:
        problems.append("expected exactly one terminal card")
    return problems


def check_success(url: str, case: dict, timeout: float) -> list[str]:
    try:
        replies = drive_remote(url, case, timeout)
    except Exception as exc:
        # Existing schema-only mode may print payloads; this mode never does.
        return [f"success exchange failed: {type(exc).__name__}"]
    return success_problems(case, replies)


@unittest.skipUnless(os.environ.get("WS_URL") and os.environ.get("WS_SUCCESS_CASES"),
                     "set WS_URL and WS_SUCCESS_CASES explicitly for live success checks")
class LiveSuccessTests(unittest.TestCase):
    def test_typed_and_audio_cards(self) -> None:
        cases = load_success_cases(os.environ["WS_SUCCESS_CASES"])
        for index, case in enumerate(cases):
            with self.subTest(case_index=index):
                self.assertEqual(check_success(os.environ["WS_URL"], case, remote_timeout()), [])


class OfflineSuccessAssertionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.replies = load("text-invoke")["receive"]
        card = self.replies[-1]
        self.case = {
            "send": load("text-invoke")["send"],
            "expect": {
                "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
                "sources": [{"title": "Synthetic citation", "url": "https://example.test/hamlet"}],
            },
        }
        card["sources"] = [{"title": "Synthetic citation", "url": "https://example.test/hamlet"}]
        card["image_url"] = "https://example.test/generated.png"
        card["audio_url"] = "https://example.test/generated.wav"

    def test_success_over_real_local_socket(self) -> None:
        with fake_backend(lambda message: self.replies) as url:
            self.assertEqual(check_success(url, self.case, 2), [])

    def test_rejects_schema_valid_error(self) -> None:
        error = {"type": "error", "request_id": self.replies[-1]["request_id"],
                 "code": "internal", "message": "Unavailable", "retryable": True}
        with fake_backend(lambda message: [error]) as url:
            self.assertTrue(any("got error" in p for p in check_success(url, self.case, 2)))

    def test_missing_media_and_wrong_grounding_fail(self) -> None:
        for field, value, diagnostic in (
            ("image_url", None, "image_url"), ("audio_url", None, "audio_url"),
            ("book", {"title": "Other", "author": "Other", "location": "Other"}, "book grounding"),
            ("sources", [], "source citation"),
            ("image_url", "http://example.test/x", "schema violation"),
        ):
            with self.subTest(field=field):
                replies = copy.deepcopy(self.replies)
                replies[-1][field] = value
                self.assertTrue(any(diagnostic in p for p in success_problems(self.case, replies)))

    def test_terminal_order_and_matching_ids(self) -> None:
        for replies in ([], self.replies * 2, self.replies + [self.replies[0]],
                        [{**r, "request_id": "other"} for r in self.replies],
                        [self.replies[1], self.replies[0], *self.replies[2:]]):
            with self.subTest(sequence_length=len(replies)):
                self.assertTrue(success_problems(self.case, replies))

    def test_diagnostics_do_not_echo_content(self) -> None:
        marker = "PRIVATE-TEST-CONTENT"
        with mock.patch("test_live_success.drive_remote", side_effect=ValueError(marker)):
            self.assertNotIn(marker, " ".join(check_success("unused", self.case, 1)))
        replies = copy.deepcopy(self.replies)
        replies[-1]["speech_text"] = {"invalid": marker}
        self.assertNotIn(marker, " ".join(success_problems(self.case, replies)))

    def test_manifest_requires_both_modes_and_independent_expectations(self) -> None:
        typed = self.case
        audio = {**copy.deepcopy(typed), "send": load("audio-invoke")["send"]}
        def read(cases):
            with mock.patch.object(Path, "open", mock.mock_open(read_data=json.dumps(cases).encode())):
                return load_success_cases("unused")
        self.assertEqual(len(read([typed, audio])), 2)
        for cases in ([], [typed], [typed, typed], [{**typed, "expect": {}}, audio]):
            with self.subTest(count=len(cases)), self.assertRaises(ValueError):
                read(cases)


if __name__ == "__main__":
    unittest.main()
