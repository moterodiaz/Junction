"""Unit tests for Nemotron 3.5 Super VL page reading."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

import httpx

from ai.page_reader import (
    DEFAULT_MODEL_READ,
    DEFAULT_NVIDIA_BASE_URL,
    GeminiPageReader,
    NemotronClient,
    NoTextFoundError,
    PageReadError,
    PageReadTimeoutError,
    StubNemotronClient,
    extract_frame_data,
    read_page,
)


class DummyMedia:
    def __init__(self, b64: str, mime: str = "image/jpeg"):
        self.b64 = b64
        self.mime = mime


class PageReaderTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ")
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("MODEL_READ", None)

    def test_extract_frame_data_various_types(self):
        # Dict
        mime, b64 = extract_frame_data({"b64": "QUFBQQ==", "mime": "image/jpeg"})
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(b64, "QUFBQQ==")

        # Object with attributes
        dummy = DummyMedia("QkJCQg==")
        mime, b64 = extract_frame_data(dummy)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(b64, "QkJCQg==")

        # Raw bytes
        raw = b"hello image"
        mime, b64 = extract_frame_data(raw)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(b64, base64.b64encode(raw).decode("ascii"))

        # Base64 string
        mime, b64 = extract_frame_data("QUFBQQ==")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(b64, "QUFBQQ==")

        # Data URL
        mime, b64 = extract_frame_data("data:image/png;base64,Q0NDQw==")
        self.assertEqual(mime, "image/png")
        self.assertEqual(b64, "Q0NDQw==")

    def test_extract_frame_data_empty_raises_no_text(self):
        for bad in (None, "", {}, {"b64": ""}, DummyMedia("")):
            with self.subTest(bad=bad):
                with self.assertRaises(NoTextFoundError) as ctx:
                    extract_frame_data(bad)
                self.assertEqual(ctx.exception.code, "no_text_found")
                self.assertTrue(ctx.exception.retryable)

    def test_read_page_with_stub_client(self):
        client = StubNemotronClient(
            default_response="To be, or not to be, that is the question."
        )
        text = asyncio.run(read_page({"b64": "QUFBQQ=="}, client=client))
        self.assertEqual(text, "To be, or not to be, that is the question.")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["frame_b64"], "QUFBQQ==")

    def test_read_page_no_text_found_cases(self):
        no_text_responses = [
            "",
            "   ",
            "NO_TEXT_FOUND",
            "no_text_found",
            "NO TEXT FOUND",
            "No readable text found.",
            "There is no text",
            "blank page",
            "empty page",
        ]
        for resp in no_text_responses:
            with self.subTest(resp=resp):
                client = StubNemotronClient(default_response=resp)
                with self.assertRaises(NoTextFoundError) as ctx:
                    asyncio.run(read_page("QUFBQQ==", client=client))
                self.assertEqual(ctx.exception.code, "no_text_found")
                self.assertTrue(ctx.exception.retryable)
                self.assertEqual(ctx.exception.message, "No readable text was found on the page.")

    def test_read_page_timeout_error(self):
        client = StubNemotronClient(default_response=PageReadTimeoutError("timed out"))
        with self.assertRaises(PageReadTimeoutError) as ctx:
            asyncio.run(read_page("QUFBQQ==", client=client))
        self.assertEqual(ctx.exception.code, "model_timeout")
        self.assertTrue(ctx.exception.retryable)

    def test_missing_api_key_raises_value_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                NemotronClient()
            self.assertIn("NVIDIA_API_KEY is required", str(ctx.exception))

    def test_client_payload_structure(self):
        client = NemotronClient(api_key="test-key", base_url="https://api.nvidia.com/v1")
        self.assertEqual(client.base_url, "https://api.nvidia.com/v1")
        self.assertEqual(client.model, DEFAULT_MODEL_READ)

        # Mock _send_request to verify payload sent
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "A horse! a horse! my kingdom for a horse!"
                    }
                }
            ]
        }
        with mock.patch.object(client, "_send_request", return_value=mock_response) as mock_send:
            res = asyncio.run(client.complete("QUFBQQ==", mime="image/jpeg"))
            self.assertEqual(res, "A horse! a horse! my kingdom for a horse!")
            mock_send.assert_called_once()
            url, headers, payload = mock_send.call_args[0]
            self.assertEqual(url, "https://api.nvidia.com/v1/chat/completions")
            self.assertEqual(headers["Authorization"], "Bearer test-key")
            self.assertEqual(payload["model"], DEFAULT_MODEL_READ)
            self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
            msg_content = payload["messages"][0]["content"]
            self.assertEqual(msg_content[0]["type"], "image_url")
            self.assertEqual(msg_content[0]["image_url"]["url"], "data:image/jpeg;base64,QUFBQQ==")


class LogCaptureContext:
    def __init__(self, logger_name: str = ""):
        self.logger = logging.getLogger(logger_name)
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)

    def __enter__(self):
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, *args):
        self.logger.removeHandler(self.handler)

    @property
    def output(self) -> str:
        return self.stream.getvalue()


class PageReaderPrivacyLeakTest(unittest.IsolatedAsyncioTestCase):
    """Verify that HTTP error bodies, network error strings, and timeouts carrying secrets

    never leak into PageReadError / PageReadTimeoutError messages or logs (REQ-PRIV-02).
    """

    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key", "GEMINI_API_KEY": "test-gemini-key"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = NemotronClient(api_key="test-key")
        self.gemini = GeminiPageReader(api_key="test-gemini-key")

    async def test_nemotron_httpx_http_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://api.nvidia.com/v1/chat/completions")
        resp = httpx.Response(500, text='{"error": "SECRET_NEMOTRON_BODY"}', request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(return_value=resp)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")
        self.assertIn("HTTP 500", err_str)

    async def test_nemotron_httpx_network_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://api.nvidia.com/v1/chat/completions")
        err = httpx.ConnectError("SECRET_NETWORK_REASON", request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(side_effect=err)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")
        self.assertIn("ConnectError", err_str)

    async def test_nemotron_httpx_timeout_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://api.nvidia.com/v1/chat/completions")
        err = httpx.ReadTimeout("SECRET_TIMEOUT_REASON", request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(side_effect=err)):
                with self.assertRaises(PageReadTimeoutError) as ctx:
                    await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "model_timeout")
        self.assertIn("ReadTimeout", err_str)

    async def test_nemotron_httpx_invalid_json_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://api.nvidia.com/v1/chat/completions")
        resp = httpx.Response(200, text='{SECRET_INVALID_JSON', request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(return_value=resp)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")

    async def test_nemotron_urllib_http_error_does_not_leak_secret(self):
        err = urllib.error.HTTPError(
            "https://api.nvidia.com/v1/chat/completions",
            500,
            "Internal Server Error",
            {},
            io.BytesIO(b"SECRET_URLLIB_HTTP_BODY"),
        )
        with mock.patch.dict(sys.modules, {"httpx": None}):
            with LogCaptureContext() as log_ctx:
                with mock.patch.object(urllib.request, "urlopen", side_effect=err):
                    with self.assertRaises(PageReadError) as ctx:
                        await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")
        self.assertIn("HTTP 500", err_str)

    async def test_nemotron_urllib_network_error_does_not_leak_secret(self):
        err = urllib.error.URLError("SECRET_URLLIB_NETWORK_REASON")
        with mock.patch.dict(sys.modules, {"httpx": None}):
            with LogCaptureContext() as log_ctx:
                with mock.patch.object(urllib.request, "urlopen", side_effect=err):
                    with self.assertRaises(PageReadTimeoutError) as ctx:
                        await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "model_timeout")
        self.assertIn("URLError", err_str)

    async def test_nemotron_urllib_timeout_error_does_not_leak_secret(self):
        err = TimeoutError("SECRET_URLLIB_TIMEOUT_REASON")
        with mock.patch.dict(sys.modules, {"httpx": None}):
            with LogCaptureContext() as log_ctx:
                with mock.patch.object(urllib.request, "urlopen", side_effect=err):
                    with self.assertRaises(PageReadTimeoutError) as ctx:
                        await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "model_timeout")
        self.assertIn("TimeoutError", err_str)

    async def test_nemotron_urllib_invalid_json_does_not_leak_secret(self):
        class MockUrllibResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return b"{SECRET_INVALID_JSON"

        with mock.patch.dict(sys.modules, {"httpx": None}):
            with LogCaptureContext() as log_ctx:
                with mock.patch.object(urllib.request, "urlopen", return_value=MockUrllibResponse()):
                    with self.assertRaises(PageReadError) as ctx:
                        await self.client.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")

    async def test_gemini_http_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-hydrogen:generateContent")
        resp = httpx.Response(500, text='{"error": "SECRET_GEMINI_BODY"}', request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(return_value=resp)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.gemini.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")
        self.assertIn("HTTP 500", err_str)

    async def test_gemini_network_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-hydrogen:generateContent")
        err = httpx.ConnectError("SECRET_GEMINI_NETWORK_REASON", request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(side_effect=err)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.gemini.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")
        self.assertIn("ConnectError", err_str)

    async def test_gemini_timeout_error_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-hydrogen:generateContent")
        err = httpx.ReadTimeout("SECRET_GEMINI_TIMEOUT_REASON", request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(side_effect=err)):
                with self.assertRaises(PageReadTimeoutError) as ctx:
                    await self.gemini.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "model_timeout")
        self.assertIn("ReadTimeout", err_str)

    async def test_gemini_invalid_json_does_not_leak_secret(self):
        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-hydrogen:generateContent")
        resp = httpx.Response(200, text='{SECRET_INVALID_JSON', request=req)
        with LogCaptureContext() as log_ctx:
            with mock.patch.object(httpx.AsyncClient, "post", mock.AsyncMock(return_value=resp)):
                with self.assertRaises(PageReadError) as ctx:
                    await self.gemini.complete("QUFBQQ==")
        err_str = str(ctx.exception)
        self.assertNotIn("SECRET", err_str)
        self.assertNotIn("SECRET", ctx.exception.message)
        self.assertNotIn("SECRET", log_ctx.output)
        self.assertEqual(ctx.exception.code, "internal")


if __name__ == "__main__":
    unittest.main()
