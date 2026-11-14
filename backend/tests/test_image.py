import asyncio
import logging
import re
import time
import unittest
from unittest import mock

from ai import image
from ai.image import (
    BillingNotEnabledError,
    DUMMY_PNG,
    ImageConfigError,
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
    sweep_idle_sessions,
)


class ImageGenerationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_all_images()
        reset_billing_state()
        set_image_client(None)
        self.base_url = mock.patch.dict(
            "os.environ", {"IMAGE_BASE_URL": "https://images.test"}
        )
        self.base_url.start()

    def tearDown(self):
        clear_all_images()
        reset_billing_state()
        set_image_client(None)
        self.base_url.stop()

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

    async def test_cleanup_discards_generation_that_finishes_afterward(self):
        started = asyncio.Event()
        finish = asyncio.Event()
        stub = StubImageClient(billing_enabled=True)

        async def delayed_generation(model, prompt):
            started.set()
            await finish.wait()
            return DUMMY_PNG

        stub.generate_image = delayed_generation
        task = asyncio.create_task(draw("Prompt", session_id="racing", client=stub))
        await started.wait()
        cleanup_session("racing")
        finish.set()

        self.assertIsNone(await task)
        self.assertFalse(any(item.session_id == "racing" for item in image._images.values()))
        self.assertNotIn("racing", image._session_epochs)

    async def test_missing_base_url_raises_configuration_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ImageConfigError, "IMAGE_BASE_URL"):
                await draw("Prompt", client=StubImageClient())

    def test_unowned_eviction_preserves_active_session_images(self):
        store_image("active", b"active", session_id="live")
        for index in range(image.MAX_STORED_IMAGES + 1):
            store_image(f"unowned-{index}", b"data")

        self.assertIsNotNone(get_image("active"))
        self.assertIsNone(get_image("unowned-0"))
        self.assertIsNotNone(get_image(f"unowned-{image.MAX_STORED_IMAGES}"))

    def test_cleanup_without_pending_generation_does_not_retain_epoch(self):
        for index in range(250):
            cleanup_session(f"finished-{index}")
        self.assertEqual(image._session_epochs, {})

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

    async def test_sweep_idle_sessions_removes_idle_session(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw("Idle prompt", session_id="idle-sess", client=stub)
        img_id = re.search(r"/img/([a-zA-Z0-9_\-]+)\.png$", url).group(1)
        self.assertIsNotNone(get_image(img_id))

        ttl = 60.0
        count = sweep_idle_sessions(now=time.monotonic() + ttl + 1, ttl=ttl)

        self.assertEqual(count, 1)
        self.assertIsNone(get_image(img_id))

    def test_sweep_active_session_is_kept(self):
        store_image("kept-img", b"data", session_id="active-sess")

        ttl = 60.0
        # Age the session beyond TTL, then refresh via get_image
        with image._lock:
            image._session_last_activity["active-sess"] = time.monotonic() - ttl - 10
        get_image("kept-img")  # touches _session_last_activity back to ~now

        count = sweep_idle_sessions(now=time.monotonic(), ttl=ttl)

        self.assertEqual(count, 0)
        self.assertIsNotNone(get_image("kept-img"))

    def test_sweep_skips_session_with_pending_generation(self):
        store_image("pending-img", b"data", session_id="pending-sess")
        with image._lock:
            image._pending_generations["pending-sess"] = 1
            image._session_last_activity["pending-sess"] = time.monotonic() - 7200

        count = sweep_idle_sessions(now=time.monotonic(), ttl=60.0)

        self.assertEqual(count, 0)
        self.assertIsNotNone(get_image("pending-img"))

        with image._lock:
            image._pending_generations.pop("pending-sess", None)

    def test_sweep_env_var_ttl_fallback_on_garbage(self):
        store_image("env-img", b"data", session_id="env-sess")
        with image._lock:
            image._session_last_activity["env-sess"] = time.monotonic() - 7200

        with mock.patch.dict("os.environ", {"IMAGE_SESSION_TTL_SECONDS": "not-a-number"}):
            count = sweep_idle_sessions()  # reads env var; falls back to 3600s default

        self.assertEqual(count, 1)
        self.assertIsNone(get_image("env-img"))

    async def test_gemini_image_client_uses_generate_content(self):
        fake_inline = mock.MagicMock(data=b"\x89PNG\r\n\x1a\nfake")
        fake_part = mock.MagicMock(inline_data=fake_inline)
        fake_candidate = mock.MagicMock(content=mock.MagicMock(parts=[fake_part]))
        fake_response = mock.MagicMock(candidates=[fake_candidate])

        fake_aio_models = mock.MagicMock()
        fake_aio_models.generate_content = mock.AsyncMock(return_value=fake_response)
        fake_client = mock.MagicMock()
        fake_client.aio.models = fake_aio_models

        with mock.patch("google.genai.Client", return_value=fake_client):
            client = image.GeminiImageClient(api_key="test-key", model="gemini-nano-banana-2.1")
            result = await client.generate_image("gemini-nano-banana-2.1", "A glowing skull on black")

        self.assertEqual(result, b"\x89PNG\r\n\x1a\nfake")
        fake_aio_models.generate_content.assert_awaited_once()
        call_kwargs = fake_aio_models.generate_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-nano-banana-2.1")
        self.assertEqual(call_kwargs["contents"], "A glowing skull on black")
        self.assertEqual(call_kwargs["config"].response_modalities, ["IMAGE"])


if __name__ == "__main__":
    unittest.main()
