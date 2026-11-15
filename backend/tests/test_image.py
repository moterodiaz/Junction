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
    STYLE_PRESETS,
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
    is_reserved,
    release,
    reserve,
    reset_billing_state,
    resolve_style_cue,
    set_image_client,
    store_image,
    sweep_idle_sessions,
    wait_for_image,
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
        self.assertTrue(any("ConnectionError" in msg for msg in cm.output))
        self.assertFalse(any("Upstream timeout" in msg for msg in cm.output))

    async def test_generation_error_with_secret_returns_none_and_redacts(self):
        stub = StubImageClient(billing_enabled=True)

        async def crash_generation(model, prompt):
            raise RuntimeError("SECRET upstream prompt quote: 'Draw Hamlet'")

        stub.generate_image = crash_generation

        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("Polonius behind tapestry", client=stub)

        self.assertIsNone(url)
        self.assertTrue(any("RuntimeError" in msg for msg in cm.output))
        for msg in cm.output:
            self.assertNotIn("SECRET", msg)

    async def test_billing_error_with_secret_returns_none_and_redacts(self):
        stub = StubImageClient(billing_enabled=True)

        async def fail_generation(model, prompt):
            raise BillingNotEnabledError("SECRET account billing suspended")

        stub.generate_image = fail_generation

        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("King Claudius kneeling", client=stub)

        self.assertIsNone(url)
        self.assertFalse(is_billing_enabled())
        self.assertTrue(any("BillingNotEnabledError" in msg for msg in cm.output))
        for msg in cm.output:
            self.assertNotIn("SECRET", msg)

    async def test_billing_check_error_with_secret_returns_none_and_redacts(self):
        stub = StubImageClient(billing_enabled=True)

        async def fail_check():
            raise RuntimeError("SECRET probe network timeout")

        stub.check_billing = fail_check

        with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
            url = await draw("Horatio on the platform", client=stub)

        self.assertIsNone(url)
        self.assertFalse(is_billing_enabled())
        self.assertTrue(any("RuntimeError" in msg for msg in cm.output))
        for msg in cm.output:
            self.assertNotIn("SECRET", msg)

    async def test_gemini_image_client_billing_error_does_not_leak_secret(self):
        fake_client = mock.MagicMock()
        fake_client.aio.models.generate_content.side_effect = Exception(
            "permission denied: SECRET token details quoted prompt"
        )

        with mock.patch("google.genai.Client", return_value=fake_client):
            client = image.GeminiImageClient(api_key="test-key", model="gemini-nano-banana-2.1")
            with self.assertRaises(BillingNotEnabledError) as ctx:
                await client.generate_image("gemini-nano-banana-2.1", "Prompt")
            self.assertNotIn("SECRET", str(ctx.exception))
            self.assertEqual(
                str(ctx.exception),
                "Billing or permission is not enabled for image generation.",
            )

    async def test_gemini_image_client_check_billing_does_not_leak_secret(self):
        with mock.patch("google.genai.Client", side_effect=Exception("billing account SECRET error")):
            client = image.GeminiImageClient(api_key="test-key")
            with self.assertLogs("metalab.image", level=logging.WARNING) as cm:
                res = await client.check_billing()
            self.assertFalse(res)
            self.assertTrue(any("Exception" in msg for msg in cm.output))
            for msg in cm.output:
                self.assertNotIn("SECRET", msg)

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

    def test_format_display_prompt_default_compatibility(self):
        base = format_display_prompt("A glowing chalice")
        self.assertEqual(base, format_display_prompt("A glowing chalice", style_preset=None))
        self.assertEqual(base, format_display_prompt("A glowing chalice", style_preset="default"))
        self.assertEqual(base, format_display_prompt("A glowing chalice", style_preset="DEFAULT"))
        self.assertEqual(base, format_display_prompt("A glowing chalice", style_preset=""))
        self.assertEqual(base, format_display_prompt("A glowing chalice", style_preset="   "))
        self.assertIn("#000000", base)
        self.assertNotIn("Stylistic suggestion", base)

    def test_format_display_prompt_soft_style_suggestion_known_presets(self):
        expected_cues = {
            "ink_woodcut": "subtle ink woodcut aesthetic",
            "gothic_oil": "subtle gothic oil aesthetic",
            "watercolor_botanical": "subtle watercolor botanical aesthetic",
            "noir_sketch": "subtle noir sketch aesthetic",
            "classical_etching": "subtle classical etching aesthetic",
        }
        for preset, expected_phrase in expected_cues.items():
            prompt = format_display_prompt("A skull on a table", style_preset=preset)
            self.assertIn(f"Stylistic suggestion: {expected_phrase}.", prompt)
            self.assertIn("#000000", prompt)
            self.assertIn("black background", prompt.lower())
            self.assertIn("additive optical", prompt.lower())
            self.assertIn("A skull on a table", prompt)

    def test_format_display_prompt_unknown_style_treated_as_soft_cue(self):
        prompt = format_display_prompt(
            "An hourglass with glowing sand",
            style_preset="cyberpunk_neon",
        )
        self.assertIn("Stylistic suggestion: subtle cyberpunk neon aesthetic.", prompt)
        self.assertIn("#000000", prompt)
        self.assertIn("An hourglass with glowing sand", prompt)

    def test_format_display_prompt_punctuation_spacing(self):
        # Prompt ending with period should not have double period
        prompt_with_dot = format_display_prompt(
            "A royal seal in wax.",
            style_preset="ink_woodcut",
        )
        self.assertIn("A royal seal in wax. Stylistic suggestion: subtle ink woodcut aesthetic.", prompt_with_dot)
        self.assertNotIn("..", prompt_with_dot)

        # Prompt without period gets dot-separated
        prompt_no_dot = format_display_prompt(
            "A royal seal in wax",
            style_preset="ink_woodcut",
        )
        self.assertIn("A royal seal in wax. Stylistic suggestion: subtle ink woodcut aesthetic.", prompt_no_dot)

    def test_all_presets_preserve_pure_black_background(self):
        for preset_name in STYLE_PRESETS:
            res = format_display_prompt("Sample artifact", style_preset=preset_name)
            self.assertIn("#000000", res)
            self.assertIn("Pure solid black background", res)

    def test_resolve_style_cue_behavior(self):
        self.assertEqual(resolve_style_cue(None), "")
        self.assertEqual(resolve_style_cue(""), "")
        self.assertEqual(resolve_style_cue("   "), "")
        self.assertEqual(resolve_style_cue("default"), "")
        self.assertEqual(resolve_style_cue("DEFAULT"), "")
        self.assertEqual(resolve_style_cue("default   "), "")

        self.assertEqual(resolve_style_cue("ink_woodcut"), "ink woodcut")
        self.assertEqual(resolve_style_cue("ink-woodcut"), "ink woodcut")
        self.assertEqual(resolve_style_cue("ink woodcut"), "ink woodcut")
        self.assertEqual(resolve_style_cue("INK_WOODCUT"), "ink woodcut")
        self.assertEqual(resolve_style_cue("gothic_oil"), "gothic oil")
        self.assertEqual(resolve_style_cue("watercolor_botanical"), "watercolor botanical")
        self.assertEqual(resolve_style_cue("noir_sketch"), "noir sketch")
        self.assertEqual(resolve_style_cue("classical_etching"), "classical etching")

        # Unknown presets normalized cleanly
        self.assertEqual(resolve_style_cue("steampunk_brass"), "steampunk brass")
        self.assertEqual(resolve_style_cue("mythic-fantasy"), "mythic-fantasy")

    async def test_draw_propagates_style_preset_to_client(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw(
            "Ghost king on castle battlements",
            session_id="style-sess-1",
            client=stub,
            style_preset="gothic_oil",
        )
        self.assertIsNotNone(url)
        self.assertEqual(len(stub.calls), 1)
        sent = stub.calls[0]["prompt"]
        self.assertIn("Stylistic suggestion: subtle gothic oil aesthetic.", sent)
        self.assertIn("#000000", sent)
        self.assertIn("Ghost king on castle battlements", sent)

    async def test_draw_with_default_style_preset_omits_suggestion(self):
        stub = StubImageClient(billing_enabled=True)
        url = await draw(
            "Ghost king on castle battlements",
            session_id="style-sess-2",
            client=stub,
            style_preset="default",
        )
        self.assertIsNotNone(url)
        self.assertEqual(len(stub.calls), 1)
        sent = stub.calls[0]["prompt"]
        self.assertNotIn("Stylistic suggestion", sent)
        self.assertIn("#000000", sent)
        self.assertIn("Ghost king on castle battlements", sent)

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


class ImageReservationTest(unittest.IsolatedAsyncioTestCase):
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

    async def _asgi_get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        sent_messages = []

        async def mock_receive():
            return {"type": "http.request"}

        async def mock_send(msg):
            sent_messages.append(msg)

        scope = {"type": "http", "path": path}
        await asgi_image_app(scope, mock_receive, mock_send)
        status = sent_messages[0]["status"]
        headers = {
            k.decode("utf-8"): v.decode("utf-8")
            for k, v in sent_messages[0].get("headers", [])
        }
        body = sent_messages[1]["body"] if len(sent_messages) > 1 else b""
        return status, headers, body

    async def test_reserved_id_blocks_then_200_after_store(self):
        """Acceptance 1: reserved id blocks then 200 after store."""
        res_id = reserve("sess-1")
        self.assertTrue(is_reserved(res_id))

        # 1. Test via asgi_image_app
        task = asyncio.create_task(self._asgi_get(f"/img/{res_id}.png"))
        await asyncio.sleep(0.02)
        self.assertFalse(task.done())

        store_image(res_id, b"stored-pixels", session_id="sess-1")
        status, headers, body = await task
        self.assertEqual(status, 200)
        self.assertEqual(body, b"stored-pixels")
        self.assertFalse(is_reserved(res_id))

        # 2. Test via draw(..., image_id=res_id) and serve_image_endpoint if available
        res_id2 = reserve("sess-2")
        stub = StubImageClient(billing_enabled=True, image_bytes=b"draw-pixels")
        task2 = asyncio.create_task(self._asgi_get(f"/img/{res_id2}"))
        await asyncio.sleep(0.02)
        self.assertFalse(task2.done())

        url = await draw("Hamlet", session_id="sess-2", client=stub, image_id=res_id2)
        self.assertEqual(url, f"https://images.test/img/{res_id2}.png")
        status2, headers2, body2 = await task2
        self.assertEqual(status2, 200)
        self.assertEqual(body2, b"draw-pixels")
        self.assertFalse(is_reserved(res_id2))

        # If image_router is present, verify serve_image_endpoint also blocks then 200s
        if image.serve_image_endpoint is not None:
            res_id3 = reserve("sess-3")
            task3 = asyncio.create_task(image.serve_image_endpoint(res_id3))
            await asyncio.sleep(0.02)
            self.assertFalse(task3.done())
            store_image(res_id3, b"router-pixels", session_id="sess-3")
            resp = await task3
            self.assertEqual(resp.body, b"router-pixels")

    async def test_released_id_404s_immediately(self):
        """Acceptance 2: released id 404s immediately and cannot be reused."""
        res_id = reserve("sess-1")
        self.assertTrue(is_reserved(res_id))

        # A: release drops reservation so in-flight waiters get fast 404
        task = asyncio.create_task(self._asgi_get(f"/img/{res_id}.png"))
        await asyncio.sleep(0.02)
        self.assertFalse(task.done())

        t0 = time.monotonic()
        released = release(res_id)
        self.assertTrue(released)
        status, _, body = await task
        t1 = time.monotonic()
        self.assertLess(t1 - t0, 0.5)
        self.assertEqual(status, 404)
        self.assertFalse(is_reserved(res_id))

        # B: request after release gets fast 404 immediately
        t0 = time.monotonic()
        status_after, _, _ = await self._asgi_get(f"/img/{res_id}.png")
        t1 = time.monotonic()
        self.assertLess(t1 - t0, 0.2)
        self.assertEqual(status_after, 404)

        if image.serve_image_endpoint is not None:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                await image.serve_image_endpoint(res_id)
            self.assertEqual(ctx.exception.status_code, 404)

        # C: ID can never be reused (store_image rejects, draw returns None)
        with self.assertRaises(ValueError):
            store_image(res_id, b"should-fail")

        stub = StubImageClient(billing_enabled=True)
        draw_url = await draw("Test reuse", client=stub, image_id=res_id)
        self.assertIsNone(draw_url)

    async def test_expiry_404s_after_image_wait_s(self):
        """Acceptance 3: expiry 404s after IMAGE_WAIT_S."""
        with mock.patch.dict("os.environ", {"IMAGE_WAIT_S": "0.05"}):
            res_id = reserve("sess-1")
            t0 = time.monotonic()
            status, _, _ = await self._asgi_get(f"/img/{res_id}.png")
            elapsed = time.monotonic() - t0
            self.assertEqual(status, 404)
            self.assertGreaterEqual(elapsed, 0.04)

            # Also check serve_image_endpoint
            if image.serve_image_endpoint is not None:
                from fastapi import HTTPException
                res_id2 = reserve("sess-1")
                t0 = time.monotonic()
                with self.assertRaises(HTTPException) as ctx:
                    await image.serve_image_endpoint(res_id2)
                elapsed = time.monotonic() - t0
                self.assertEqual(ctx.exception.status_code, 404)
                self.assertGreaterEqual(elapsed, 0.04)

    async def test_cleanup_session_releases_pending_ids(self):
        """Acceptance 4: cleanup_session releases pending ids."""
        res_id1 = reserve("sess-cleanup")
        res_id2 = reserve("sess-cleanup")
        self.assertTrue(is_reserved(res_id1))
        self.assertTrue(is_reserved(res_id2))

        # Waiter on res_id1
        task = asyncio.create_task(self._asgi_get(f"/img/{res_id1}.png"))
        await asyncio.sleep(0.02)
        self.assertFalse(task.done())

        cleanup_session("sess-cleanup")
        self.assertFalse(is_reserved(res_id1))
        self.assertFalse(is_reserved(res_id2))

        # In-flight waiter gets 404 immediately
        status1, _, _ = await task
        self.assertEqual(status1, 404)

        # Subsequent request gets 404 immediately
        status2, _, _ = await self._asgi_get(f"/img/{res_id2}.png")
        self.assertEqual(status2, 404)

        # Idle sweep also cleans up pending reservations
        res_id_idle = reserve("sess-idle-sweep")
        self.assertTrue(is_reserved(res_id_idle))
        ttl = 60.0
        sweep_idle_sessions(now=time.monotonic() + ttl + 10, ttl=ttl)
        self.assertFalse(is_reserved(res_id_idle))
        status_idle, _, _ = await self._asgi_get(f"/img/{res_id_idle}.png")
        self.assertEqual(status_idle, 404)

    async def test_draw_failure_releases_reserved_id(self):
        """Draw failure automatically releases the reserved id."""
        # 1. Billing check failure
        res_id1 = reserve("sess-fail-1")
        stub_fail = StubImageClient(billing_enabled=False)
        url1 = await draw("Test billing fail", client=stub_fail, image_id=res_id1)
        self.assertIsNone(url1)
        self.assertFalse(is_reserved(res_id1))
        status1, _, _ = await self._asgi_get(f"/img/{res_id1}.png")
        self.assertEqual(status1, 404)

        # 2. Generation exception failure
        reset_billing_state()
        res_id2 = reserve("sess-fail-2")
        stub_crash = StubImageClient(billing_enabled=True)

        async def crash_gen(model, prompt):
            raise RuntimeError("crash")

        stub_crash.generate_image = crash_gen
        url2 = await draw("Test crash", client=stub_crash, image_id=res_id2)
        self.assertIsNone(url2)
        self.assertFalse(is_reserved(res_id2))
        status2, _, _ = await self._asgi_get(f"/img/{res_id2}.png")
        self.assertEqual(status2, 404)

    async def test_already_stored_ids_behave_as_today(self):
        """Already stored IDs return 200 immediately without waiting."""
        store_image("instant-id", b"instant-data", mime_type="image/png")
        t0 = time.monotonic()
        status, headers, body = await self._asgi_get("/img/instant-id.png")
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.1)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"instant-data")


if __name__ == "__main__":
    unittest.main()
