"""End-to-end conformance: replay recorded exchanges against the backend's /ws and check every
outbound frame against ws-messages.schema.json and its recording.

Each exchanges/<name>.json holds:
  send:    inbound frames, {"text": <object or raw string>} or {"bytes": <object>}
  receive: outbound frames recorded from the backend (rewrite with `record.py <name>`)
Optional "invalid_send": true marks an exchange whose invoke is meant to break the schema.
"""

from __future__ import annotations

import json
import signal
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

CONTRACTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CONTRACTS_DIR.parent / "backend"
EXCHANGES_DIR = CONTRACTS_DIR / "exchanges"
SCHEMA = json.loads((CONTRACTS_DIR / "ws-messages.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)

sys.path.insert(0, str(BACKEND_DIR))
from fastapi.testclient import TestClient  # noqa: E402

from app import main, pipeline  # noqa: E402
from app.main import app  # noqa: E402

STAGES = ["transcribing", "reading", "thinking", "drawing"]
COMPARED = ("type", "stage", "request_id", "code", "retryable")
TIMEOUT_S = 10
EXTRA_REPLY_TIMEOUT_S = 0.1


def load(name: str) -> dict:
    return json.loads((EXCHANGES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def names() -> list[str]:
    return sorted(p.stem for p in EXCHANGES_DIR.glob("*.json"))


def encode_like_ios(message: dict) -> bytes:
    # Contract.encode uses JSONEncoder with .sortedKeys and explicit nulls; without
    # .withoutEscapingSlashes it also escapes "/" (common in base64) as "\/".
    return json.dumps(message, sort_keys=True, separators=(",", ":")).replace("/", "\\/").encode()


@contextmanager
def deadline(seconds: float):
    def fire(signum, frame):
        raise TimeoutError(f"no reply from /ws within {seconds}s")

    previous = signal.signal(signal.SIGALRM, fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def send_frame(ws, frame: dict) -> None:
    if "bytes" in frame:
        ws.send_bytes(encode_like_ios(frame["bytes"]))
    elif isinstance(frame["text"], str):
        ws.send_text(frame["text"])
    else:
        ws.send_text(json.dumps(frame["text"]))


def drive(exchange: dict, count: int | None = None) -> list[dict]:
    """Replay the send frames and return replies: `count` of them, or (when recording)
    replies until each send has ended in a card or error."""
    replies: list[dict] = []
    with deadline(TIMEOUT_S), TestClient(app).websocket_connect("/ws") as ws:
        for frame in exchange["send"]:
            send_frame(ws, frame)
        if count is not None:
            replies = [ws.receive_json() for _ in range(count)]
            try:
                with deadline(EXTRA_REPLY_TIMEOUT_S):
                    extra = ws.receive_json()
            except TimeoutError:
                pass
            else:
                raise AssertionError(f"unexpected reply after expected sequence: {extra}")
        else:
            done = 0
            while done < len(exchange["send"]):
                reply = ws.receive_json()
                replies.append(reply)
                done += reply.get("type") in ("card", "error")
    return replies


def expected_request_id(frame: dict) -> str | None:
    message = frame.get("bytes", frame.get("text"))
    if isinstance(message, dict) and isinstance(message.get("request_id"), str):
        return message["request_id"]
    return None


def schema_problems(frame: dict, where: str) -> list[str]:
    return [f"{where}: schema violation at /{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in VALIDATOR.iter_errors(frame)]


def flow_problems(exchange: dict, replies: list[dict]) -> list[str]:
    """Status stages in PRD order, then exactly one card or error, per send; ids echo the invoke."""
    problems: list[str] = []
    turns: list[list[dict]] = [[]]
    for reply in replies:
        turns[-1].append(reply)
        if reply.get("type") in ("card", "error"):
            turns.append([])
    if turns[-1]:
        problems.append(f"replies end without a card or error: {turns[-1]}")
    turns = [t for t in turns if t and t[-1].get("type") in ("card", "error")]
    if len(turns) != len(exchange["send"]):
        problems.append(f"{len(exchange['send'])} sends but {len(turns)} card/error replies")
    for i, (frame, turn) in enumerate(zip(exchange["send"], turns)):
        want_id = expected_request_id(frame)
        last = -1
        for reply in turn[:-1]:
            if reply.get("type") != "status":
                problems.append(f"send {i}: expected status before the final reply, got {reply.get('type')}")
                continue
            index = STAGES.index(reply["stage"]) if reply.get("stage") in STAGES else -1
            if index <= last:
                problems.append(f"send {i}: stage {reply.get('stage')!r} out of PRD order")
            last = max(last, index)
        for reply in turn:
            if reply.get("request_id") != want_id:
                problems.append(f"send {i}: request_id {reply.get('request_id')!r}, expected {want_id!r}")
    return problems


def check(name: str) -> list[str]:
    """Run one exchange live and return every problem found (empty means conformant)."""
    exchange = load(name)
    recorded = exchange["receive"]
    try:
        live = drive(exchange, len(recorded))
    except TimeoutError as exc:
        return [f"{name}: {exc}"]
    problems: list[str] = []
    for i, frame in enumerate(live):
        problems += schema_problems(frame, f"{name} receive[{i}]")
    for i, (got, want) in enumerate(zip(live, recorded)):
        for key in COMPARED:
            if got.get(key) != want.get(key):
                problems.append(f"{name} receive[{i}].{key}: live {got.get(key)!r}, recorded {want.get(key)!r}")
    problems += [f"{name}: {p}" for p in flow_problems(exchange, live)]
    return problems


class RecordedExchangesTests(unittest.TestCase):
    def test_exchanges_exist(self) -> None:
        self.assertTrue({"text-invoke", "audio-invoke", "ios-binary-invoke", "invalid-json",
                         "audio-and-text"} <= set(names()))

    def test_recordings_pass_schema(self) -> None:
        for name in names():
            exchange = load(name)
            with self.subTest(exchange=name):
                self.assertTrue(exchange["receive"], "empty recording; run record.py")
                for i, frame in enumerate(exchange["receive"]):
                    self.assertEqual(schema_problems(frame, f"receive[{i}]"), [])
                self.assertEqual(flow_problems(exchange, exchange["receive"]), [])

    def test_sent_invokes_pass_schema(self) -> None:
        for name in names():
            exchange = load(name)
            if exchange.get("invalid_send"):
                continue
            for i, frame in enumerate(exchange["send"]):
                message = frame.get("bytes", frame.get("text"))
                if isinstance(message, dict):
                    with self.subTest(exchange=name, send=i):
                        self.assertEqual(schema_problems(message, f"send[{i}]"), [])

    def test_backend_conforms(self) -> None:
        for name in names():
            with self.subTest(exchange=name):
                self.assertEqual(check(name), [])


class DriftTests(unittest.TestCase):
    def test_non_https_image_url_is_reported(self) -> None:
        with mock.patch.object(pipeline, "draw", new=mock.AsyncMock(return_value="http://x.png")):
            problems = check("text-invoke")
        self.assertTrue(any("schema violation" in p and "receive[3]" in p for p in problems), problems)

    def test_missing_reply_fails_instead_of_hanging(self) -> None:
        exchange = load("audio-and-text")
        with mock.patch(f"{__name__}.TIMEOUT_S", 1), self.assertRaises(TimeoutError):
            drive(exchange, len(exchange["receive"]) + 1)

    def test_duplicate_final_reply_is_reported(self) -> None:
        original_send = main.send

        async def send_duplicate_final(ws, message) -> None:
            await original_send(ws, message)
            if message.type == "card":
                await original_send(ws, message)

        with mock.patch.object(main, "send", new=send_duplicate_final), self.assertRaises(AssertionError):
            check("text-invoke")


if __name__ == "__main__":
    unittest.main()
