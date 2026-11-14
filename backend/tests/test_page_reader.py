"""Unit tests for Nemotron 3.5 Super VL page reading."""

from __future__ import annotations

import asyncio
import base64
import unittest
from unittest import mock

from ai.page_reader import (
    DEFAULT_MODEL_READ,
    DEFAULT_NVIDIA_BASE_URL,
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
            self.assertFalse(payload["extra_body"]["chat_template_kwargs"]["enable_thinking"])
            msg_content = payload["messages"][0]["content"]
            self.assertEqual(msg_content[0]["type"], "image_url")
            self.assertEqual(msg_content[0]["image_url"]["url"], "data:image/jpeg;base64,QUFBQQ==")


if __name__ == "__main__":
    unittest.main()
