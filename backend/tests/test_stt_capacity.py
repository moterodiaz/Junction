"""#110: with both speech slots busy, a request waits for one within its stage budget."""

import asyncio
import threading
import unittest
from unittest import mock

import stt
from app import pipeline
from app.messages import Media


def audio():
    # A fresh object per call: a module-level Media would stay alive and trip the privacy
    # test that checks no frame or audio outlives a request.
    return Media(mime="audio/wav", b64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=")


class SlotTest(unittest.TestCase):
    def setUp(self):
        self.permits = threading.Semaphore(0)  # each permit lets one engine call finish
        self.calls = []

        def engine(audio):
            self.calls.append(audio)
            self.permits.acquire(timeout=5)
            return "explain"

        self.addCleanup(stt.set_engine, stt.set_engine(engine))
        self.addCleanup(lambda: [self.permits.release() for _ in range(5)])

    async def fill_both_slots(self):
        busy = [asyncio.ensure_future(pipeline.transcribe(audio())) for _ in range(2)]
        while len(self.calls) < 2:
            await asyncio.sleep(0.01)
        return busy

    def test_third_request_gets_the_next_free_slot(self):
        async def go():
            busy = await self.fill_both_slots()
            third = asyncio.ensure_future(pipeline.timed(pipeline.transcribe(audio())))
            await asyncio.sleep(0.1)
            self.assertFalse(third.done())  # waiting, not failed
            self.assertEqual(len(self.calls), 2)  # the cap still holds
            self.permits.release()  # one busy request finishes and frees its slot
            text = await third
            self.permits.release()
            self.permits.release()
            await asyncio.gather(*busy)
            return text

        self.assertEqual(asyncio.run(go()), "explain")
        self.assertEqual(len(self.calls), 3)

    def test_no_free_slot_within_the_budget_is_model_timeout(self):
        async def go():
            busy = await self.fill_both_slots()
            with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 0.1), \
                    self.assertRaises(pipeline.PipelineError) as ctx:
                await pipeline.timed(pipeline.transcribe(audio()))
            self.permits.release()
            self.permits.release()
            await asyncio.gather(*busy)
            return ctx.exception.code

        self.assertEqual(asyncio.run(go()), "model_timeout")
        self.assertEqual(len(self.calls), 2)  # the waiting request never reached the engine

    def test_cancelling_a_waiting_request_takes_no_slot(self):
        async def go():
            busy = await self.fill_both_slots()
            waiting = asyncio.ensure_future(pipeline.transcribe(audio()))
            await asyncio.sleep(0.05)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            self.permits.release()
            self.permits.release()
            await asyncio.gather(*busy)
            # Both slots are free again: two more requests run without waiting.
            self.permits.release()
            self.permits.release()
            return await asyncio.wait_for(asyncio.gather(*(pipeline.transcribe(audio()) for _ in range(2))), 2)

        self.assertEqual(asyncio.run(go()), ["explain", "explain"])
        self.assertEqual(len(self.calls), 4)  # the cancelled request never ran


if __name__ == "__main__":
    unittest.main()
