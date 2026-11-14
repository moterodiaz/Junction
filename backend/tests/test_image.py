import asyncio
import logging
import re
import unittest
from unittest import mock

from ai.image import (
    BillingNotEnabledError,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_IMAGE,
    DUMMY_PNG,
    StubImageClient,
    asgi_image_app,
    cleanup_session,
    clear_all_images,
    delete_image,
    draw,
    format_display_prompt,
    get_image,
    get_image_response,
    is_billing_enabled,
    reset_billing_state,
    set_image_client,
    store_image,
)


class ImageGenerationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_all_images()
        reset_billing_state()
        set_image_client(None)

    def tearDown(self):
        clear_all_images()
        reset_billing_state()
        set_image_client(None)

    async def test_draw_success_with_stub(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw("Hamlet holding Yorick's skull", session_id="sess-1", client=stub)

        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("/img/", url)
        self.assertTrue(url.endswith(".png"))

        # Verify contract regex: ^https://[^\s]*$
        self.assertTrue(re.match(r"^https://[^\s]*$", url))

        # Verify prompt passed to client has display conditioning
        self.assertEqual(len(stub.calls), 1)
        sent_prompt = stub.calls[0]["prompt"]
        self.assertIn("black background", sent_prompt)
        self.assertIn("additive optical", sent_prompt)
        self.assertIn("Hamlet holding Yorick's skull", sent_prompt)

        # Verify image is stored in memory
        match = re.search(r"/img/([a-zA-Z0-9_\-]+)\.png$", url)
        self.assertIsNotNone(match)
        img_id = match.group(1)
        stored = get_image(img_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.data, stub.image_bytes)
        self.assertEqual(stored.session_id, "sess-1")

    async def test_first_call_billing_check_disabled_returns_none(self):
        stub = StubImageClient(billing_enabled=False)
        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("Ghost on castle ramparts", client=stub)

        self.assertIsNone(url)
        self.assertFalse(is_billing_enabled())
        self.assertTrue(any("billing" in msg.lower() for msg in cm.output))

        # Subsequent call should immediately return None without calling client
        stub.calls.clear()
        url2 = await draw("Second prompt", client=stub)
        self.assertIsNone(url2)
        self.assertEqual(len(stub.calls), 0)

    async def test_first_call_billing_check_enabled_proceeds(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw("Ophelia by the willow tree", client=stub)
        self.assertIsNotNone(url)
        self.assertTrue(is_billing_enabled())

    async def test_billing_failure_during_generation_catches_gracefully(self):
        stub = StubImageClient(billing_enabled=True)

        async def fail_generation(model, prompt):
            raise BillingNotEnabledError("Billing disabled mid-stream")

        stub.generate_image = fail_generation

        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("King Claudius kneeling", client=stub)

        self.assertIsNone(url)
        self.assertFalse(is_billing_enabled())
        self.assertTrue(any("billing" in msg.lower() for msg in cm.output))

    async def test_generic_generation_error_returns_none_and_logs(self):
        stub = StubImageClient(billing_enabled=True)

        async def crash_generation(model, prompt):
            raise ConnectionError("Upstream timeout")

        stub.generate_image = crash_generation

        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("Polonius behind tapestry", client=stub)

        self.assertIsNone(url)
        self.assertTrue(any("Upstream timeout" in msg for msg in cm.output))

    async def test_session_cleanup(self):
        stub = StubImageClient(billing_enabled=True)
        url1 = await draw("Prompt 1", session_id="session-A", client=stub)
        url2 = await draw("Prompt 2", session_id="session-A", client=stub)
        url3 = await draw("Prompt 3", session_id="session-B", client=stub)

        id1 = re.search(r"/img/([a-zA-Z0-9_\-]+)\.png$", url1).group(1)
        id2 = re.search(r"/img/([a-zA-Z0-9_\-]+)\.png$", url2).group(1)
        id3 = re.search(r"/img/([a-zA-Z0-9_\-]+)\.png$", url3).group(1)

        self.assertIsNotNone(get_image(id1))
        self.assertIsNotNone(get_image(id2))
        self.assertIsNotNone(get_image(id3))

        # Cleanup session-A
        deleted_count = cleanup_session("session-A")
        self.assertEqual(deleted_count, 2)

        self.assertIsNone(get_image(id1))
        self.assertIsNone(get_image(id2))
        # session-B image should still exist
        self.assertIsNotNone(get_image(id3))

        # Cleanup session-B
        deleted_count = cleanup_session("session-B")
        self.assertEqual(deleted_count, 1)
        self.assertIsNone(get_image(id3))

    def test_single_image_deletion(self):
        item = store_image("test-123", b"pngdata", session_id="s1")
        self.assertIsNotNone(get_image("test-123"))
        deleted = delete_image("test-123")
        self.assertTrue(deleted)
        self.assertIsNone(get_image("test-123"))
        self.assertFalse(delete_image("test-123"))

    def test_format_display_prompt_enforces_black_background(self):
        prompt = format_display_prompt("A golden crown on dark stone")
        self.assertIn("black background", prompt.lower())
        self.assertIn("additive optical", prompt.lower())
        self.assertIn("A golden crown on dark stone", prompt)

    def test_get_image_response(self):
        store_image("img-abc", b"mybytes", mime_type="image/png")

        # Found with extension and without
        status, headers, body = get_image_response("img-abc")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(body, b"mybytes")

        status, headers, body = get_image_response("img-abc.png")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"mybytes")

        # Not found
        status, headers, body = get_image_response("nonexistent")
        self.assertEqual(status, 404)

    async def test_asgi_image_app(self):
        store_image("asgi-test", b"asgidata", mime_type="image/png")

        # 1. Test 200 OK
        sent_messages = []

        async def mock_receive():
            return {"type": "http.request"}

        async def mock_send(msg):
            sent_messages.append(msg)

        scope = {"type": "http", "path": "/img/asgi-test.png"}
        await asgi_image_app(scope, mock_receive, mock_send)

        self.assertEqual(sent_messages[0]["type"], "http.response.start")
        self.assertEqual(sent_messages[0]["status"], 200)
        self.assertEqual(sent_messages[1]["body"], b"asgidata")

        # 2. Test 404 Not Found
        sent_messages.clear()
        scope = {"type": "http", "path": "/img/nonexistent.png"}
        await asgi_image_app(scope, mock_receive, mock_send)

        self.assertEqual(sent_messages[0]["status"], 404)

    async def test_custom_base_url_and_https_enforcement(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw("Test prompt", base_url="http://custom.lens.local", client=stub)
        self.assertTrue(url.startswith("https://custom.lens.local/img/"))


if __name__ == "__main__":
    unittest.main()
