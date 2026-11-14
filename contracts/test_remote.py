"""Remote mode: replay the recorded exchanges against a running backend over a real socket.

Opt in with WS_URL (e.g. WS_URL=wss://<modal-url>/ws ./test.sh). A live server runs real models
on the recorded media, so its outcomes can legitimately differ from the stubbed recordings.
Remote mode therefore enforces only the contract: every reply passes ws-messages.schema.json and
the flow is valid (stages in PRD order, one card or error per send, request_id echoed).
Differences from the recordings are printed as drift and never fail the run.

WS_TIMEOUT_S bounds each receive (default 300 s; page reading on Nemotron takes minutes).
LocalServerRemoteModeTests always runs: it starts uvicorn on a free local port, so CI covers the
real socket path without network or keys.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import contextmanager

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect
from websockets.sync.server import serve

from test_conformance import BACKEND_DIR, COMPARED, encode_like_ios, flow_problems, load, names, schema_problems

DEFAULT_TIMEOUT_S = 300.0
CONNECT_TIMEOUT_S = 15.0
EXTRA_REPLY_WAIT_S = 0.5
MAX_REPLIES_PER_SEND = 50
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


def remote_timeout() -> float:
    return float(os.environ.get("WS_TIMEOUT_S") or DEFAULT_TIMEOUT_S)


def send_remote(ws, frame: dict) -> None:
    if "bytes" in frame:
        ws.send(encode_like_ios(frame["bytes"]))
    elif isinstance(frame["text"], str):
        ws.send(frame["text"])
    else:
        ws.send(json.dumps(frame["text"]))


def drive_remote(url: str, exchange: dict, timeout: float, *,
                 extra_reply_wait: float = EXTRA_REPLY_WAIT_S) -> list[dict]:
    """Send the exchange's frames to url and read replies until each send has ended in a card or
    error, plus any extra reply that arrives shortly after. Raises TimeoutError when a receive
    waits longer than `timeout`, and ValueError on a reply that is not a JSON object.
    After the terminal, observe one extra reply for at most `extra_reply_wait` seconds
    (legacy default 0.5 s); later replies are outside this finite observation."""
    replies: list[dict] = []
    max_replies = MAX_REPLIES_PER_SEND * len(exchange["send"])
    with connect(url, open_timeout=min(timeout, CONNECT_TIMEOUT_S), max_size=MAX_MESSAGE_BYTES) as ws:
        for frame in exchange["send"]:
            send_remote(ws, frame)
        done = 0
        while done < len(exchange["send"]):
            if len(replies) >= max_replies:
                raise ValueError(f"{len(replies)} replies without a card or error for every send")
            reply = parse(ws.recv(timeout=timeout))
            replies.append(reply)
            done += reply.get("type") in ("card", "error")
        try:
            replies.append(parse(ws.recv(timeout=extra_reply_wait)))
        except (TimeoutError, ConnectionClosed):
            pass
    return replies


def parse(raw: str | bytes) -> dict:
    reply = json.loads(raw)
    if not isinstance(reply, dict):
        raise ValueError(f"reply is not a JSON object: {raw!r}")
    return reply


def check_remote(url: str, name: str, timeout: float | None = None) -> tuple[list[str], list[str]]:
    """Run one exchange against url. Returns (problems, drift): problems break the contract,
    drift notes only differences from the recording."""
    exchange = load(name)
    timeout = remote_timeout() if timeout is None else timeout
    try:
        replies = drive_remote(url, exchange, timeout)
    except TimeoutError:
        return [f"{name}: no reply from {url} within {timeout}s"], []
    except ConnectionClosed as exc:
        return [f"{name}: {url} closed the socket before the exchange finished: {exc}"], []
    except ValueError as exc:
        return [f"{name}: {exc}"], []
    except Exception as exc:  # connection refused, DNS failure, bad handshake, invalid URI
        return [f"{name}: could not talk to {url}: {type(exc).__name__}: {exc}"], []
    problems: list[str] = []
    for i, frame in enumerate(replies):
        problems += schema_problems(frame, f"{name} receive[{i}]")
    problems += [f"{name}: {p}" for p in flow_problems(exchange, replies)]
    recorded = exchange["receive"]
    drift: list[str] = []
    if len(replies) != len(recorded):
        drift.append(f"{name}: {len(replies)} replies, recorded {len(recorded)}")
    for i, (got, want) in enumerate(zip(replies, recorded)):
        for key in COMPARED:
            if got.get(key) != want.get(key):
                drift.append(f"{name} receive[{i}].{key}: remote {got.get(key)!r}, recorded {want.get(key)!r}")
    return problems, drift


def report_drift(url: str, drift: list[str]) -> None:
    if drift:
        print(f"\ndrift from recordings at {url} (reported, not enforced):", file=sys.stderr)
        for line in drift:
            print(f"  {line}", file=sys.stderr)


@unittest.skipUnless(os.environ.get("WS_URL"), "set WS_URL=wss://<host>/ws to run against a live backend")
class RemoteExchangesTests(unittest.TestCase):
    def test_remote_backend_conforms(self) -> None:
        url = os.environ["WS_URL"]
        drift: list[str] = []
        for name in names():
            with self.subTest(exchange=name):
                problems, notes = check_remote(url, name)
                drift += notes
                self.assertEqual(problems, [])
        report_drift(url, drift)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalServerRemoteModeTests(unittest.TestCase):
    """Remote mode against a real uvicorn on localhost, offline: no keys, no speech engine."""

    @classmethod
    def setUpClass(cls) -> None:
        port = free_port()
        cls.url = f"ws://127.0.0.1:{port}/ws"
        # Without keys the pipeline uses its offline stubs, so this never calls a model API.
        env = {k: v for k, v in os.environ.items() if k not in ("NVIDIA_API_KEY", "GEMINI_API_KEY")}
        cls.log = tempfile.TemporaryFile()
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND_DIR, env=env, stdout=cls.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        return
            except OSError:
                pass
            if cls.server.poll() is not None or time.monotonic() > deadline:
                cls.log.seek(0)
                output = cls.log.read().decode(errors="replace")[-4000:]
                cls.tearDownClass()
                raise RuntimeError(f"local uvicorn did not become healthy within 30 s:\n{output}")
            time.sleep(0.2)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()
        cls.log.close()

    def test_local_server_conforms(self) -> None:
        for name in names():
            with self.subTest(exchange=name):
                problems, _ = check_remote(self.url, name, timeout=30)
                self.assertEqual(problems, [])


@contextmanager
def fake_backend(handler):
    """A one-off websocket server on localhost that answers each message with handler(message)."""

    def session(ws) -> None:
        try:
            for message in ws:
                for reply in handler(message):
                    ws.send(json.dumps(reply))
        except ConnectionClosed:
            pass

    with serve(session, "127.0.0.1", 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}/ws"
        finally:
            server.shutdown()
            thread.join()


class RemoteDriftTests(unittest.TestCase):
    def test_schema_breaking_reply_is_reported(self) -> None:
        recorded = load("text-invoke")["receive"]
        broken = [dict(f, image_url="http://x.png") if f["type"] == "card" else f for f in recorded]
        with fake_backend(lambda message: broken) as url:
            problems, _ = check_remote(url, "text-invoke", timeout=5)
        self.assertTrue(any("schema violation" in p and "receive[3]" in p for p in problems), problems)

    def test_different_outcome_is_drift_not_failure(self) -> None:
        def stt_failed(message):
            request_id = json.loads(message)["request_id"]
            return [{"type": "status", "request_id": request_id, "stage": "transcribing"},
                    {"type": "error", "request_id": request_id, "code": "stt_failed",
                     "message": "Speech recognition failed. Try again.", "retryable": True}]

        with fake_backend(stt_failed) as url:
            problems, drift = check_remote(url, "audio-invoke", timeout=5)
        self.assertEqual(problems, [])
        self.assertTrue(any("stt_failed" in d for d in drift), drift)

    def test_silent_backend_fails_instead_of_hanging(self) -> None:
        with fake_backend(lambda message: []) as url:
            started = time.monotonic()
            problems, _ = check_remote(url, "text-invoke", timeout=1)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(any("no reply" in p for p in problems), problems)

    def test_unreachable_url_is_reported(self) -> None:
        problems, _ = check_remote(f"ws://127.0.0.1:{free_port()}/ws", "text-invoke", timeout=5)
        self.assertTrue(any("could not talk to" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
