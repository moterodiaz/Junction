"""Issue #83: Gemini reads the page when Nemotron misses its budget or fails."""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

import httpx

from ai import page_reader
from ai.page_reader import (
    DEFAULT_MODEL_READ_FALLBACK,
    GeminiPageReader,
    NoTextFoundError,
    PageReadError,
    PageReadTimeoutError,
    PageText,
    StubGeminiPageReader,
    StubNemotronClient,
    read_page_with_fallback,
)
from app import pipeline
from app.messages import Frame, Invoke

FRAME = {"mime": "image/jpeg", "b64": "QUFBQQ=="}
NEMOTRON_MODEL = "nemotron-test"
GEMINI_MODEL = "gemini-read-test"


class SlowNemotron:
    """A Nemotron stand-in that answers only after delay_s (the Verda queue)."""

    model = NEMOTRON_MODEL

    def __init__(self, delay_s: float, text: str = "Text read by Nemotron") -> None:
        self.delay_s = delay_s
        self.text = text
        self.cancelled = False

    async def complete(self, frame_b64, mime="image/jpeg", prompt=None):
        try:
            await asyncio.sleep(self.delay_s)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.text


class FallbackUnitTest(unittest.IsolatedAsyncioTestCase):
    async def test_slow_nemotron_falls_back_to_gemini(self):
        slow = SlowNemotron(delay_s=5)
        gemini = StubGeminiPageReader("Text read by Gemini", model=GEMINI_MODEL)
        text = await read_page_with_fallback(FRAME, primary=slow, fallback=gemini, budget_s=0.05)
        self.assertEqual(text, "Text read by Gemini")
        self.assertIsInstance(text, PageText)
        self.assertEqual(text.model, GEMINI_MODEL)
        self.assertTrue(slow.cancelled)
        self.assertEqual(gemini.calls[0]["frame_b64"], FRAME["b64"])
        self.assertEqual(gemini.calls[0]["mime"], "image/jpeg")

    async def test_fast_nemotron_skips_gemini(self):
        gemini = StubGeminiPageReader("Text read by Gemini", model=GEMINI_MODEL)
        text = await read_page_with_fallback(
            FRAME, primary=SlowNemotron(delay_s=0), fallback=gemini, budget_s=1)
        self.assertEqual(text, "Text read by Nemotron")
        self.assertEqual(text.model, NEMOTRON_MODEL)
        self.assertEqual(gemini.calls, [])

    async def test_no_text_found_is_an_answer_not_a_failure(self):
        gemini = StubGeminiPageReader("Text read by Gemini")
        with self.assertRaises(NoTextFoundError):
            await read_page_with_fallback(
                FRAME, primary=StubNemotronClient(default_response="NO_TEXT_FOUND"),
                fallback=gemini, budget_s=1)
        self.assertEqual(gemini.calls, [])

    async def test_nemotron_http_error_falls_back(self):
        nemotron = StubNemotronClient(default_response=PageReadError("Nemotron API returned HTTP 503"))
        gemini = StubGeminiPageReader("Text read by Gemini", model=GEMINI_MODEL)
        text = await read_page_with_fallback(FRAME, primary=nemotron, fallback=gemini, budget_s=1)
        self.assertEqual(text.model, GEMINI_MODEL)

    async def test_nemotron_timeout_error_falls_back(self):
        nemotron = StubNemotronClient(default_response=PageReadTimeoutError())
        gemini = StubGeminiPageReader("Text read by Gemini")
        text = await read_page_with_fallback(FRAME, primary=nemotron, fallback=gemini, budget_s=1)
        self.assertEqual(text, "Text read by Gemini")

    async def test_both_fail_raises_gemini_error(self):
        nemotron = StubNemotronClient(default_response=PageReadError("down"))
        for gemini_error, code in [
            (PageReadTimeoutError(), "model_timeout"),
            (PageReadError("down too"), "internal"),
            (NoTextFoundError(), "no_text_found"),
        ]:
            with self.subTest(code=code):
                with self.assertRaises(PageReadError) as ctx:
                    await read_page_with_fallback(
                        FRAME, primary=nemotron, fallback=StubGeminiPageReader(gemini_error), budget_s=1)
                self.assertEqual(ctx.exception.code, code)

    async def test_no_gemini_key_means_no_fallback_and_no_budget(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "READ_FALLBACK_AFTER_S": "0.01"}):
            with self.assertRaises(PageReadError) as ctx:
                await read_page_with_fallback(
                    FRAME, primary=StubNemotronClient(default_response=PageReadError("down")))
            self.assertEqual(str(ctx.exception), "down")
            # Without a fallback, a slow Nemotron is not cut off at the fallback budget.
            text = await read_page_with_fallback(FRAME, primary=SlowNemotron(delay_s=0.05))
        self.assertEqual(text.model, NEMOTRON_MODEL)

    async def test_budget_and_model_come_from_env(self):
        env = {"GEMINI_API_KEY": "dummy", "READ_FALLBACK_AFTER_S": "0.05", "MODEL_READ_FALLBACK": GEMINI_MODEL}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(page_reader, "GeminiPageReader",
                                  side_effect=lambda: StubGeminiPageReader("g", model=os.environ["MODEL_READ_FALLBACK"])):
            text = await read_page_with_fallback(FRAME, primary=SlowNemotron(delay_s=5))
        self.assertEqual(text.model, GEMINI_MODEL)
        with mock.patch.dict(os.environ, env):
            self.assertEqual(GeminiPageReader().model, GEMINI_MODEL)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy", "MODEL_READ_FALLBACK": ""}):
            self.assertEqual(GeminiPageReader().model, DEFAULT_MODEL_READ_FALLBACK)


async def _noop_send_stage(stage):
    pass


class FallbackThroughPipelineTest(unittest.IsolatedAsyncioTestCase):
    """The acceptance check: Gemini's text reaches the card and models.read names Gemini."""

    def setUp(self):
        self.invoke = Invoke(type="invoke", request_id="r-83", session_id="s-83",
                             frame=Frame(mime="image/jpeg", b64="QUFBQQ=="), text="explain")
        env = mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key", "GEMINI_API_KEY": "dummy",
                                           "MODEL_READ": NEMOTRON_MODEL, "READ_FALLBACK_AFTER_S": "0.05"})
        env.start()
        self.addCleanup(env.stop)

        async def think_echo(command, page_text, session_id, **kwargs):
            return {"title": "Read page", "caption": page_text, "speech_text": page_text,
                    "image_prompt": "page", "book": {"title": "B", "author": "A", "location": "P"}}

        for target, value in [("think", think_echo), ("draw", mock.AsyncMock(return_value=None)),
                              ("speak", mock.AsyncMock(return_value=None))]:
            patcher = mock.patch.object(pipeline, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def readers(self, nemotron, gemini):
        a = mock.patch.object(page_reader, "NemotronClient", return_value=nemotron)
        b = mock.patch.object(page_reader, "GeminiPageReader", return_value=gemini)
        a.start(); b.start()
        self.addCleanup(a.stop); self.addCleanup(b.stop)

    async def test_slow_nemotron_card_carries_gemini_text_and_model(self):
        gemini = StubGeminiPageReader("Text read by Gemini", model=GEMINI_MODEL)
        self.readers(SlowNemotron(delay_s=5), gemini)
        card = await pipeline.run(self.invoke, _noop_send_stage)
        self.assertEqual(card.caption, "Text read by Gemini")
        self.assertEqual(card.models["read"], GEMINI_MODEL)
        self.assertEqual(len(gemini.calls), 1)

    async def test_fast_nemotron_card_names_nemotron(self):
        gemini = StubGeminiPageReader("Text read by Gemini", model=GEMINI_MODEL)
        self.readers(StubNemotronClient(default_response="Text read by Nemotron"), gemini)
        card = await pipeline.run(self.invoke, _noop_send_stage)
        self.assertEqual(card.caption, "Text read by Nemotron")
        self.assertEqual(card.models["read"], NEMOTRON_MODEL)
        self.assertEqual(gemini.calls, [])

    async def test_nemotron_no_text_found_is_not_retried(self):
        gemini = StubGeminiPageReader("Text read by Gemini")
        self.readers(StubNemotronClient(default_response="NO_TEXT_FOUND"), gemini)
        with self.assertRaises(pipeline.PipelineError) as ctx:
            await pipeline.run(self.invoke, _noop_send_stage)
        self.assertEqual(ctx.exception.code, "no_text_found")
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(gemini.calls, [])


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://example.invalid"))


class GeminiPageReaderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reader = GeminiPageReader(api_key="secret-key-123", model=GEMINI_MODEL)

    async def post_with(self, response):
        post = mock.AsyncMock(return_value=response)
        with mock.patch("httpx.AsyncClient.post", post):
            text = await self.reader.complete("QUFBQQ==", mime="image/png")
        return text, post

    async def test_request_shape_keeps_key_out_of_url(self):
        body = {"candidates": [{"content": {"parts": [{"text": "  To be, or not to be.  "}]}}]}
        text, post = await self.post_with(_response(200, body))
        self.assertEqual(text, "To be, or not to be.")
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertTrue(url.endswith(f"/models/{GEMINI_MODEL}:generateContent"))
        self.assertNotIn("secret-key-123", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "secret-key-123")
        parts = kwargs["json"]["contents"][0]["parts"]
        self.assertEqual(parts[0], {"inline_data": {"mime_type": "image/png", "data": "QUFBQQ=="}})
        self.assertEqual(parts[1]["text"], page_reader.DEFAULT_PROMPT)

    async def test_no_text_found_reply(self):
        body = {"candidates": [{"content": {"parts": [{"text": "NO_TEXT_FOUND"}]}}]}
        with self.assertRaises(NoTextFoundError):
            await self.post_with(_response(200, body))

    async def test_thought_parts_are_ignored(self):
        body = {"candidates": [{"content": {"parts": [
            {"text": "thinking about it", "thought": True}, {"text": "Page text"}]}}]}
        text, _ = await self.post_with(_response(200, body))
        self.assertEqual(text, "Page text")

    async def test_http_error_maps_to_internal_without_key(self):
        with self.assertRaises(PageReadError) as ctx:
            await self.post_with(_response(500, {"error": {"message": "boom"}}))
        self.assertEqual(ctx.exception.code, "internal")
        self.assertNotIn("secret-key-123", str(ctx.exception))

    async def test_no_candidates_is_internal(self):
        with self.assertRaises(PageReadError) as ctx:
            await self.post_with(_response(200, {"promptFeedback": {"blockReason": "OTHER"}}))
        self.assertEqual(ctx.exception.code, "internal")

    async def test_httpx_timeout_maps_to_model_timeout(self):
        with mock.patch("httpx.AsyncClient.post", mock.AsyncMock(side_effect=httpx.ReadTimeout("slow"))):
            with self.assertRaises(PageReadTimeoutError):
                await self.reader.complete("QUFBQQ==")

    def test_requires_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(ValueError):
                GeminiPageReader()


if __name__ == "__main__":
    unittest.main()
