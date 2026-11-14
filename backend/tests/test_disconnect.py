"""#111: when the phone disconnects mid-request, the work stops and nothing is remembered."""

import asyncio
import contextlib
import json
import os
import socket
import threading
import time
import unittest
from unittest import mock

import uvicorn
import websockets

from ai import reasoning
from app.main import app

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
ANSWER = {"title": "t", "caption": "c", "speech_text": "s", "image_prompt": "p",
          "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 1"}}


def invoke(request_id="r1", session_id="s1"):
    return {"type": "invoke", "request_id": request_id, "session_id": session_id,
            "frame": FRAME, "audio": None, "text": "explain"}


class SlowModel:
    """A reasoning client that waits until released, recording whether it was cancelled."""

    def __init__(self):
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.release = threading.Event()

    async def generate_reasoning(self, **kwargs):
        self.started.set()
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return dict(ANSWER)


@contextlib.contextmanager
def real_server():
    """Serve the app with real uvicorn: unlike TestClient, it does not cancel the handler for us."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    try:
        yield f"ws://127.0.0.1:{port}/ws"
    finally:
        server.should_exit = True
        thread.join(5)


async def replies_until(ws, count, until_stage=None):
    """Read replies until `until_stage` arrives or `count` final (card/error) replies arrived."""
    finals = []
    while True:
        reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if reply["type"] == "status":
            if reply["stage"] == until_stage:
                return finals
            continue
        finals.append((reply["type"], reply["request_id"]))
        if len(finals) == count:
            return finals


def history(session_id):
    return list(reasoning.default_session_store.get_or_create(session_id).history)


class DisconnectTest(unittest.TestCase):
    def setUp(self):
        # A Gemini key routes `think` to backend/ai/reasoning.py; images and speech stay off.
        env = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": "key", "IMAGE_BASE_URL": ""})
        env.start()
        self.addCleanup(env.stop)
        self.model = SlowModel()
        reasoning.set_reasoning_client(self.model)
        self.addCleanup(reasoning.set_reasoning_client, None)
        draw = mock.patch("app.pipeline.draw", mock.AsyncMock(return_value=None))
        draw.start()
        self.addCleanup(draw.stop)
        self.addCleanup(self.model.release.set)

    def test_disconnect_while_thinking_cancels_and_records_nothing(self):
        session = f"cancel-{time.monotonic_ns()}"

        async def go(url):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke(session_id=session)))
                await replies_until(ws, 1, until_stage="thinking")
            # The phone hangs up while the model is still working.

        with real_server() as url:
            asyncio.run(go(url))
            self.assertTrue(self.model.started.is_set())
            self.assertTrue(self.model.cancelled.wait(2), "the model call kept running after the disconnect")
        self.assertEqual(history(session), [])

    def test_a_second_request_during_the_first_is_answered_in_order(self):
        session = f"queue-{time.monotonic_ns()}"

        async def go(url):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke("r1", session)))
                await replies_until(ws, 1, until_stage="thinking")
                await ws.send(json.dumps(invoke("r2", session)))
                self.model.release.set()
                return await replies_until(ws, 2)

        with real_server() as url:
            finals = asyncio.run(go(url))
        self.assertEqual(finals, [("card", "r1"), ("card", "r2")])
        self.assertEqual(len(history(session)), 2)

    def test_disconnect_with_a_queued_request_still_cancels(self):
        session = f"queued-dc-{time.monotonic_ns()}"

        async def go(url):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke("r1", session)))
                await replies_until(ws, 1, until_stage="thinking")
                await ws.send(json.dumps(invoke("r2", session)))
                await asyncio.sleep(0.2)

        with real_server() as url:
            asyncio.run(go(url))
            self.assertTrue(self.model.cancelled.wait(2), "a queued message hid the disconnect")
        self.assertEqual(history(session), [])

    def test_disconnect_while_drawing_forgets_the_exchange(self):
        session = f"drawing-dc-{time.monotonic_ns()}"
        drawing = threading.Event()

        async def hold(*args, **kwargs):
            drawing.set()
            await asyncio.sleep(30)

        async def go(url):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke(session_id=session)))
                await replies_until(ws, 1, until_stage="drawing")
                await asyncio.sleep(0.2)

        self.model.release.set()
        with mock.patch("app.pipeline.draw", hold), real_server() as url:
            asyncio.run(go(url))
            self.assertTrue(drawing.wait(2))
            time.sleep(0.3)
        self.assertEqual(history(session), [])

    def test_flooding_the_queue_closes_the_socket(self):
        from app import main

        async def go(url):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke("r0")))
                await replies_until(ws, 1, until_stage="thinking")
                for i in range(main.MAX_QUEUED_FRAMES + 1):
                    await ws.send(json.dumps(invoke(f"q{i}")))
                with self.assertRaises(websockets.ConnectionClosed) as ctx:
                    while True:
                        await asyncio.wait_for(ws.recv(), 5)
                return ctx.exception.rcvd.code

        with real_server() as url:
            self.assertEqual(asyncio.run(go(url)), 1008)
            self.assertTrue(self.model.cancelled.wait(2))

    def test_cancelling_one_socket_keeps_another_sockets_answer(self):
        session = f"shared-{time.monotonic_ns()}"
        permits = threading.Semaphore(0)  # each permit lets exactly one model call finish
        model = self.model

        async def gated(**kwargs):
            model.started.set()
            try:
                while not permits.acquire(blocking=False):
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                model.cancelled.set()
                raise
            return dict(ANSWER)

        model.generate_reasoning = gated

        async def go(url):
            async with websockets.connect(url) as first, websockets.connect(url) as second:
                await first.send(json.dumps(invoke("r1", session)))
                await replies_until(first, 1, until_stage="thinking")
                await second.send(json.dumps(invoke("r2", session)))  # waits for the session
                permits.release()  # only r1 may finish
                self.assertEqual(await replies_until(first, 1), [("card", "r1")])
                await replies_until(second, 1, until_stage="thinking")
                await second.close()  # r2 is cancelled after r1 was saved

        with real_server() as url:
            asyncio.run(go(url))
            self.assertTrue(model.cancelled.wait(2))
        self.assertEqual(len(history(session)), 1)  # r1's answer survives r2's cancellation

    def test_reconnecting_works_and_other_sessions_are_untouched(self):
        kept, dropped = f"kept-{time.monotonic_ns()}", f"dropped-{time.monotonic_ns()}"

        async def ask(url, request_id, session, finish):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(invoke(request_id, session)))
                if finish:
                    return await replies_until(ws, 1)
                await replies_until(ws, 1, until_stage="thinking")

        with real_server() as url:
            self.model.release.set()
            self.assertEqual(asyncio.run(ask(url, "r1", kept, True)), [("card", "r1")])
            self.model.release.clear()
            asyncio.run(ask(url, "r2", dropped, False))
            self.assertTrue(self.model.cancelled.wait(2))
            self.model.release.set()
            self.assertEqual(asyncio.run(ask(url, "r3", dropped, True)), [("card", "r3")])
        self.assertEqual(len(history(kept)), 1)
        self.assertEqual(len(history(dropped)), 1)  # only the request that finished


if __name__ == "__main__":
    unittest.main()
