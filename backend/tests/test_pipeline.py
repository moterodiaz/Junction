"""Pipeline wiring tests: key-set uses ai.think; key-unset returns offline stub dict."""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest import mock

from ai.decision import DecisionResult, StubDecisionClient, set_decision_client
from ai import image
from ai.image import StubImageClient, set_image_client
from ai.reasoning import DEFAULT_MODEL_REASON, StubGeminiClient, parse_reasoning_json, set_reasoning_client
from ai.session import default_session_store
from app import pipeline
from app.messages import Audio, Frame, Invoke, Media

_STUB_ANSWER = {
    "title": "Hamlet, Act 3, Scene 1",
    "caption": "A test caption from reasoning.",
    "speech_text": "Test speech text.",
    "image_prompt": "Test image prompt, pure black background (#000000).",
    "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
    "sources": [],
}

_OFFLINE_DICT = {
    "title": "Hamlet, Act 3, Scene 1",
    "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
    "speech_text": "Hamlet is alone, weighing whether to keep living.",
    "image_prompt": "A lone prince on a dark stage, bright outline on black",
    "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
}


class PipelineThinkKeySetTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        default_session_store.clear()
        self._stub = StubGeminiClient(default_answer=_STUB_ANSWER)
        set_reasoning_client(self._stub)
        self._env_patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        set_reasoning_client(None)
        default_session_store.clear()

    async def test_key_set_delegates_to_ai_think(self):
        """When GEMINI_API_KEY is set, pipeline.think calls ai.think and returns its result."""
        answer = await pipeline.think("explain this", "To be or not to be", "sess-keyset")
        self.assertEqual(answer["caption"], _STUB_ANSWER["caption"])
        self.assertEqual(answer["speech_text"], _STUB_ANSWER["speech_text"])
        self.assertEqual(len(self._stub.calls), 1)
        self.assertEqual(self._stub.calls[0]["command"], "explain this")

    async def test_session_history_retained_on_second_invoke(self):
        """Second call in the same session receives the first call's question in history."""
        await pipeline.think("first question", "passage one", "sess-history")
        await pipeline.think("second question", "passage two", "sess-history")
        self.assertEqual(len(self._stub.calls), 2)
        self.assertEqual(self._stub.calls[1]["history_count"], 1)
        self.assertEqual(
            self._stub.calls[1]["history_snapshot"][0]["question"], "first question"
        )


class PipelineThinkKeyUnsetTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("NVIDIA_API_KEY", None)

    def tearDown(self):
        self._env_patch.stop()

    async def test_key_unset_returns_offline_stub_dict(self):
        """When GEMINI_API_KEY is absent, pipeline.think returns the fixed offline dict unchanged."""
        answer = await pipeline.think("any command", "any page", "s-offline")
        self.assertEqual(answer, _OFFLINE_DICT)


async def _noop_send_stage(stage):
    pass


_STUB_ANSWER_WITH_SOURCES = {
    "title": "Hamlet, Act 3, Scene 1",
    "caption": "Live caption.",
    "speech_text": "Live speech.",
    "image_prompt": "Live prompt, pure black background (#000000).",
    "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
    "sources": [{"title": "Project Gutenberg Hamlet", "url": "https://www.gutenberg.org/ebooks/1524"}],
}


class PipelineRunLivePathTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._invoke = Invoke(
            type="invoke", request_id="r-run", session_id="s-run",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        default_session_store.clear()
        self._stub = StubGeminiClient(default_answer=_STUB_ANSWER_WITH_SOURCES)
        set_reasoning_client(self._stub)
        self._env_patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"})
        self._env_patch.start()
        os.environ.pop("MODEL_REASON", None)  # restored when the patch stops; keeps default-model asserts hermetic

    def tearDown(self):
        del self._invoke
        self._env_patch.stop()
        set_reasoning_client(None)
        default_session_store.clear()

    async def test_sources_populated_and_reason_model_reported(self):
        """Live path: card.sources mirrors Gemini sources; models.reason is DEFAULT_MODEL_REASON."""
        # Use a real Hamlet passage so ground_passage verifies it and passage_match is not None;
        # sources are only preserved when a passage is verified (Thread 2 fix).
        hamlet_page = "To be, or not to be, that is the question"
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=hamlet_page):
            card = await pipeline.run(self._invoke, _noop_send_stage)
        self.assertEqual(len(card.sources), 1)
        self.assertEqual(card.sources[0].url, "https://www.gutenberg.org/ebooks/1524")
        self.assertEqual(card.sources[0].title, "Project Gutenberg Hamlet")
        self.assertEqual(card.models["reason"], DEFAULT_MODEL_REASON)

    async def test_malformed_source_entries_dropped(self):
        """Sources missing url are dropped; missing title gets default 'Source'; non-dicts dropped."""
        stub = StubGeminiClient(default_answer={
            **_STUB_ANSWER_WITH_SOURCES,
            "sources": [
                {"title": "Good", "url": "https://example.com/good"},
                {"title": "No URL"},
                {"url": "https://example.com/no-title"},
                "not a dict",
            ],
        })
        set_reasoning_client(stub)
        hamlet_page = "To be, or not to be, that is the question"
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=hamlet_page):
            card = await pipeline.run(self._invoke, _noop_send_stage)
        self.assertEqual(len(card.sources), 2)
        self.assertEqual(card.sources[0].url, "https://example.com/good")
        self.assertEqual(card.sources[1].url, "https://example.com/no-title")
        self.assertEqual(card.sources[1].title, "Source")

    async def test_model_reason_env_var_is_used_in_live_path(self):
        """Thread 1: MODEL_REASON env var is passed to ai.think and reflected in models.reason."""
        custom_model = "gemini-custom-7b"
        with mock.patch.dict(os.environ, {"MODEL_REASON": custom_model}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page"):
            card = await pipeline.run(self._invoke, _noop_send_stage)
        self.assertEqual(card.models["reason"], custom_model)
        self.assertEqual(self._stub.calls[0]["model"], custom_model)

    async def test_non_https_sources_are_dropped(self):
        """Thread 3: http:// and www. sources are dropped; only https:// passes through."""
        stub = StubGeminiClient(default_answer={
            **_STUB_ANSWER_WITH_SOURCES,
            "sources": [
                {"title": "HTTPS ok", "url": "https://example.com/ok"},
                {"title": "HTTP dropped", "url": "http://www.gutenberg.org/ebooks/1524"},
                {"title": "www dropped", "url": "www.gutenberg.org/ebooks/1524"},
                {"title": "No scheme dropped", "url": "example.com/page"},
            ],
        })
        set_reasoning_client(stub)
        hamlet_page = "To be, or not to be, that is the question"
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=hamlet_page):
            card = await pipeline.run(self._invoke, _noop_send_stage)
        self.assertEqual(len(card.sources), 1)
        self.assertEqual(card.sources[0].url, "https://example.com/ok")


class PipelineRunOfflinePathTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._invoke = Invoke(
            type="invoke", request_id="r-run", session_id="s-run",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("NVIDIA_API_KEY", None)

    def tearDown(self):
        del self._invoke
        self._env_patch.stop()

    async def test_sources_empty_and_reason_model_is_stub(self):
        """Offline path: card.sources is empty; models.reason is 'stub'."""
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
            card = await pipeline.run(self._invoke, _noop_send_stage)
        self.assertEqual(card.sources, [])
        self.assertEqual(card.models["reason"], "stub")


class PipelineDynamicRoutingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        default_session_store.clear()
        self._stub_reason = StubGeminiClient(default_answer=_STUB_ANSWER_WITH_SOURCES)
        set_reasoning_client(self._stub_reason)
        self._env_patch = mock.patch.dict(os.environ, {
            "GEMINI_API_KEY": "dummy",
            "DYNAMIC_MODEL_ROUTING": "true",
        })
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        set_reasoning_client(None)
        set_decision_client(None)
        default_session_store.clear()

    async def test_natural_question_routed_to_reasoning_with_recommended_model(self):
        """Natural student question routes cleanly through decision to reasoning."""
        utterance = "Why is Hamlet hesitating to take action against Claudius?"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-1", session_id="s-dyn-1",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="question",
            task_tier="deep",
            recommended_model="gemini-4-carbon",
            needs_image=False,
            speak_only=False,
            confidence=0.96,
            fallback_used=False,
            raw_utterance=utterance,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Act 3 Scene 1 passage"):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(card.models["reason"], "gemini-4-carbon")
        self.assertEqual(self._stub_reason.calls[0]["command"], utterance)
        self.assertEqual(self._stub_reason.calls[0]["model"], "gemini-4-carbon")
        # needs_image is False, so draw was skipped
        self.assertIsNone(card.image_url)
        self.assertEqual(card.models["image"], "stub")

    async def test_natural_question_with_image_calls_draw(self):
        """Decision with needs_image=True and speak_only=False calls draw() and populates image_url."""
        utterance = "Draw a vivid picture of the ghost on the battlements"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-2", session_id="s-dyn-2",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="draw",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,
            speak_only=False,
            confidence=0.91,
            fallback_used=False,
            raw_utterance=utterance,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"), \
             mock.patch.object(pipeline, "draw", new_callable=mock.AsyncMock, return_value="https://example.com/ghost.png"):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(card.image_url, "https://example.com/ghost.png")
        self.assertEqual(card.models["reason"], "gemini-3.5-flash-lite")
        self.assertEqual(card.models["image"], pipeline._image_model())

    async def test_speak_only_skips_draw_while_calling_speak(self):
        """Decision with speak_only=True skips draw() while synthesizing speech audio."""
        utterance = "Explain what Hamlet is saying, audio only"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-3", session_id="s-dyn-3",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="explain",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,  # even if needs_image was true, speak_only forces skip
            speak_only=True,
            confidence=0.95,
            fallback_used=False,
            raw_utterance=utterance,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        draw_mock = mock.AsyncMock(return_value="https://example.com/unused.png")
        speak_mock = mock.AsyncMock(return_value="https://example.com/answer.wav")
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"), \
             mock.patch.object(pipeline, "draw", draw_mock), \
             mock.patch.object(pipeline, "speak", speak_mock):
            card = await pipeline.run(invoke, _noop_send_stage)

        draw_mock.assert_not_called()
        speak_mock.assert_called_once()
        self.assertIsNone(card.image_url)
        self.assertEqual(card.models["image"], "stub")
        self.assertEqual(card.audio_url, "https://example.com/answer.wav")

    async def test_decision_timeout_falls_back_to_l0_rejection_for_natural_question(self):
        """When decision evaluation times out on a non-L0 question, pipeline raises stt_failed error."""
        utterance = "Tell me everything about the setting of Elsinore"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-4", session_id="s-dyn-4",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        set_decision_client(StubDecisionClient(timeout=True))

        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
            with self.assertRaises(pipeline.PipelineError) as ctx:
                await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(ctx.exception.code, "stt_failed")
        self.assertEqual(ctx.exception.message, pipeline.UNKNOWN_COMMAND)
        self.assertTrue(ctx.exception.retryable)

    async def test_decision_error_falls_back_to_l0_valid_command_success(self):
        """When decision fails on a valid L0 command (e.g. 'explain'), pipeline falls back cleanly."""
        utterance = "explain"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-5", session_id="s-dyn-5",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        set_decision_client(StubDecisionClient(fail=True))

        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertIsNotNone(card)
        self.assertEqual(card.book.title, "Hamlet")
        self.assertEqual(card.book.location, pipeline.NO_SOURCE_TEXT)  # "passage" matches no source line

    async def test_dynamic_routing_off_preserves_model_reason(self):
        """When DYNAMIC_MODEL_ROUTING is explicitly false, MODEL_REASON env override is preserved."""
        custom_model = "gemini-override-custom-tier"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-6", session_id="s-dyn-6",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        # Even with a stub decision client registered, DYNAMIC_MODEL_ROUTING=false disables it
        set_decision_client(StubDecisionClient(default_result=DecisionResult(
            action="explain",
            task_tier="deep",
            recommended_model="gemini-4-carbon",
            needs_image=False,
            speak_only=False,
            confidence=0.99,
            fallback_used=False,
            raw_utterance="explain",
        )))

        with mock.patch.dict(os.environ, {
            "DYNAMIC_MODEL_ROUTING": "false",
            "MODEL_REASON": custom_model,
        }), mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(card.models["reason"], custom_model)
        self.assertEqual(self._stub_reason.calls[0]["model"], custom_model)

    async def test_transcribed_audio_with_dynamic_routing(self):
        """Audio invoke preserves transcribed natural question and routes to decision."""
        audio_invoke = Invoke(
            type="invoke", request_id="r-dyn-7", session_id="s-dyn-7",
            frame=Frame(mime="image/jpeg", b64="AAAA"),
            audio=Audio(mime="audio/wav", b64="AAAA"),
        )
        natural_utterance = "Who are Rosencrantz and Guildenstern?"
        dec_result = DecisionResult(
            action="who_is_this",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=False,
            speak_only=False,
            confidence=0.94,
            fallback_used=False,
            raw_utterance=natural_utterance,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        with mock.patch.object(pipeline, "transcribe", new_callable=mock.AsyncMock, return_value=natural_utterance), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
            card = await pipeline.run(audio_invoke, _noop_send_stage)

        self.assertEqual(card.models["reason"], "gemini-3.5-flash-lite")
        self.assertEqual(self._stub_reason.calls[0]["command"], natural_utterance)

    async def test_dynamic_routing_passes_style_preset_gothic_oil_to_image_draw(self):
        """REQ-IMG-01, REQ-VOICE-02: dynamic routing style_preset gothic_oil is passed to image.draw / format_display_prompt preserving #000000 background."""
        utterance = "Draw a dramatic scene of the ghost on the battlements"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-style-1", session_id="s-dyn-style-1",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="draw",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,
            speak_only=False,
            confidence=0.93,
            fallback_used=False,
            raw_utterance=utterance,
            style_preset="gothic_oil",
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))
        stub_image = StubImageClient(billing_enabled=True)
        set_image_client(stub_image)
        try:
            with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": "https://example.com"}), \
                 mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
                card = await pipeline.run(invoke, _noop_send_stage)

            self.assertIsNotNone(card.image_url)
            self.assertTrue(card.image_url.startswith("https://example.com/img/"))
            self.assertEqual(len(stub_image.calls), 1)
            prompt = stub_image.calls[0]["prompt"]
            self.assertIn("#000000", prompt)
            self.assertIn("gothic oil", prompt)
            self.assertIn("Stylistic suggestion: subtle gothic oil aesthetic.", prompt)
        finally:
            set_image_client(None)
            image.clear_all_images()
            image.reset_billing_state()

    async def test_dynamic_routing_passes_style_preset_ink_woodcut_to_image_draw(self):
        """REQ-IMG-01, REQ-VOICE-02: dynamic routing style_preset ink_woodcut is passed to image.draw / format_display_prompt preserving #000000 background."""
        utterance = "Draw the duel scene in woodcut style"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-style-2", session_id="s-dyn-style-2",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="draw",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,
            speak_only=False,
            confidence=0.91,
            fallback_used=False,
            raw_utterance=utterance,
            style_preset="ink_woodcut",
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))
        stub_image = StubImageClient(billing_enabled=True)
        set_image_client(stub_image)
        try:
            with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": "https://example.com"}), \
                 mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"):
                card = await pipeline.run(invoke, _noop_send_stage)

            self.assertIsNotNone(card.image_url)
            self.assertTrue(card.image_url.startswith("https://example.com/img/"))
            self.assertEqual(len(stub_image.calls), 1)
            prompt = stub_image.calls[0]["prompt"]
            self.assertIn("#000000", prompt)
            self.assertIn("ink woodcut", prompt)
            self.assertIn("Stylistic suggestion: subtle ink woodcut aesthetic.", prompt)
        finally:
            set_image_client(None)
            image.clear_all_images()
            image.reset_billing_state()

    async def test_dynamic_routing_style_preset_with_legacy_2arg_draw_monkeypatch(self):
        """REQ-IMG-01: monkeypatched 2-arg pipeline.draw test stubs still pass untouched without TypeError."""
        utterance = "Draw a scene with 2-arg stub"
        invoke = Invoke(
            type="invoke", request_id="r-dyn-style-3", session_id="s-dyn-style-3",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text=utterance,
        )
        dec_result = DecisionResult(
            action="draw",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,
            speak_only=False,
            confidence=0.90,
            fallback_used=False,
            raw_utterance=utterance,
            style_preset="gothic_oil",
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        two_arg_called = False

        async def legacy_2arg_draw(image_prompt: str, session_id: str) -> str:
            nonlocal two_arg_called
            two_arg_called = True
            return "https://example.com/legacy_draw.png"

        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="passage"), \
             mock.patch.object(pipeline, "draw", legacy_2arg_draw):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertTrue(two_arg_called)
        self.assertEqual(card.image_url, "https://example.com/legacy_draw.png")

    async def test_pipeline_draw_accepts_style_preset_and_forwards_to_image(self):
        """pipeline.draw directly accepts style_preset and forwards to image.draw."""
        stub_image = StubImageClient(billing_enabled=True)
        set_image_client(stub_image)
        try:
            with mock.patch.dict(os.environ, {"IMAGE_BASE_URL": "https://example.com"}):
                url = await pipeline.draw("A dark tower", "sess-test", style_preset="noir_sketch")
            self.assertIsNotNone(url)
            self.assertEqual(len(stub_image.calls), 1)
            prompt = stub_image.calls[0]["prompt"]
            self.assertIn("#000000", prompt)
            self.assertIn("noir sketch", prompt)
        finally:
            set_image_client(None)
            image.clear_all_images()
            image.reset_billing_state()


class PipelineGroundingAndBookClassificationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        default_session_store.clear()
        self._stub_reason = StubGeminiClient()
        set_reasoning_client(self._stub_reason)
        self._env_patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        set_reasoning_client(None)
        set_decision_client(None)
        default_session_store.clear()

    async def test_hamlet_grounding_wired_through_pipeline_run(self):
        """REQ-SRC-01: Hamlet grounding via ground_passage wired through pipeline.run."""
        invoke = Invoke(
            type="invoke", request_id="r-hamlet-gr", session_id="s-hamlet-gr",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        hamlet_passage = "To be, or not to be, that is the question: Whether 'tis nobler in the mind to suffer"
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=hamlet_passage):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(card.book.title, "Hamlet")
        self.assertEqual(card.book.author, "William Shakespeare")
        self.assertIn("Act 3, Scene 1", card.book.location)
        self.assertIn("64", card.book.location)
        self.assertTrue(len(card.sources) > 0)
        self.assertEqual(card.sources[0].url, "https://www.gutenberg.org/ebooks/1524")
        self.assertEqual(len(self._stub_reason.calls), 1)
        self.assertIsNotNone(self._stub_reason.calls[0]["passage_match"])
        self.assertEqual(self._stub_reason.calls[0]["passage_match"]["play"], "Hamlet")

        session = default_session_store.get("s-hamlet-gr")
        self.assertIsNotNone(session)
        self.assertEqual(session.book.title, "Hamlet")
        self.assertIn("Act 3, Scene 1", session.book.location)

    async def test_unknown_book_explicit_no_source_path(self):
        """REQ-SRC-01: Unknown-book passage (passage_match is None): explicit no-source path (no invented Hamlet citations)."""
        invoke = Invoke(
            type="invoke", request_id="r-gatsby", session_id="s-gatsby",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        session = default_session_store.get_or_create("s-gatsby")
        session.set_active_book("The Great Gatsby", "F. Scott Fitzgerald", "Chapter 1")

        unknown_passage = "In my younger and more vulnerable years my father gave me some advice"
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=unknown_passage):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertIsNone(self._stub_reason.calls[0]["passage_match"])
        self.assertEqual(card.book.title, "The Great Gatsby")
        self.assertEqual(card.sources, [])

    async def test_mid_session_book_switch_classification(self):
        """REQ-INTENT-01: Mid-session book switch classification updates session.book without triggering clarify."""
        invoke = Invoke(
            type="invoke", request_id="r-switch-1", session_id="s-switch-1",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what does Macbeth say about dagger?",
        )
        session = default_session_store.get_or_create("s-switch-1")
        self.assertEqual(session.book.title, "Hamlet")

        dec_result = DecisionResult(
            action="explain",
            task_tier="balanced",
            recommended_model="gemini-4-argon",
            needs_image=False,
            speak_only=False,
            confidence=0.92,
            fallback_used=False,
            raw_utterance="what does Macbeth say about dagger?",
            book_match="Macbeth",
            book_match_confidence=0.88,
            book_changed=True,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Is this a dagger which I see before me"):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(session.book.title, "Macbeth")
        self.assertEqual(card.book.title, "Macbeth")
        self.assertNotEqual(card.title, "Which book are you reading?")

    async def test_rare_clarify_path_when_low_grounding_and_low_confidence(self):
        """REQ-INTENT-01: Rare clarify path (passage_score < 0.65 and book_match_confidence < 0.70) returns clarifying Card."""
        invoke = Invoke(
            type="invoke", request_id="r-clarify-1", session_id="s-clarify-1",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what is this?",
        )
        dec_result = DecisionResult(
            action="clarify",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=True,
            speak_only=False,
            confidence=0.90,
            fallback_used=False,
            raw_utterance="what is this?",
            book_match="unknown",
            book_match_confidence=0.35,
            book_changed=False,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        draw_mock = mock.AsyncMock(return_value="https://example.com/not-used.png")
        speak_mock = mock.AsyncMock(return_value="https://example.com/clarify-audio.wav")
        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="xyzzy qwerty foobar blorp zzz"), \
             mock.patch.object(pipeline, "draw", draw_mock), \
             mock.patch.object(pipeline, "speak", speak_mock):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertEqual(card.title, "Which book are you reading?")
        self.assertIn("Which book are you reading", card.speech_text)
        self.assertIn("Which book are you reading", card.caption)
        draw_mock.assert_not_called()
        speak_mock.assert_called_once()
        self.assertIsNone(card.image_url)
        self.assertEqual(card.models["image"], "stub")
        self.assertEqual(card.models["reason"], "gemini-3.5-flash-lite")
        self.assertEqual(len(self._stub_reason.calls), 0)
        self.assertEqual(card.audio_url, "https://example.com/clarify-audio.wav")

    async def test_clarify_gate_not_triggered_when_passage_score_high(self):
        """REQ-INTENT-01: Clarify gate is NOT triggered when passage grounding succeeds (>= 0.65) even if action is clarify."""
        invoke = Invoke(
            type="invoke", request_id="r-clarify-high", session_id="s-clarify-high",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what is this?",
        )
        dec_result = DecisionResult(
            action="clarify",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=False,
            speak_only=False,
            confidence=0.50,
            fallback_used=False,
            raw_utterance="what is this?",
            book_match="unknown",
            book_match_confidence=0.40,
            book_changed=False,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        hamlet_passage = "To be, or not to be, that is the question:"
        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=hamlet_passage):
            card = await pipeline.run(invoke, _noop_send_stage)

        self.assertNotEqual(card.title, "Which book are you reading?")
        self.assertEqual(card.book.title, "Hamlet")
        self.assertEqual(len(self._stub_reason.calls), 1)

    async def test_clarify_reply_adds_unfamiliar_book_before_candidate_check_and_runs_think(self):
        """Greptile P1: clarification reply adds unfamiliar title before decide() and learns via think()."""
        seen_candidates: list[list[str]] = []

        class InspectingDecisionClient(StubDecisionClient):
            async def decide(self, utterance, page_text="", session=None, model=None, timeout_s=2.0, enabled_checks=None):
                seen_candidates.append([b.title for b in session.candidate_books] if session else [])
                return await super().decide(utterance, page_text, session, model=model, timeout_s=timeout_s, enabled_checks=enabled_checks)

        dec_result = DecisionResult(
            action="clarify",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=False,
            speak_only=False,
            confidence=0.90,
            fallback_used=False,
            raw_utterance="what is this?",
            book_match="unknown",
            book_match_confidence=0.35,
            book_changed=False,
        )
        set_decision_client(InspectingDecisionClient(default_result=dec_result))

        turn1 = Invoke(
            type="invoke", request_id="r-clr-1", session_id="s-clr-loop",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what is this?",
        )
        turn2 = Invoke(
            type="invoke", request_id="r-clr-2", session_id="s-clr-loop",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="I'm reading The Odyssey.",
        )
        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Tell me, Muse, of the man of many ways"), \
             mock.patch.object(pipeline, "draw", new_callable=mock.AsyncMock, return_value="https://example.com/odyssey.png"), \
             mock.patch.object(pipeline, "speak", new_callable=mock.AsyncMock, return_value="https://example.com/odyssey.wav"):
            card1 = await pipeline.run(turn1, _noop_send_stage)
            self.assertEqual(card1.title, "Which book are you reading?")
            session = default_session_store.get("s-clr-loop")
            self.assertTrue(session.awaiting_book_clarification)

            card2 = await pipeline.run(turn2, _noop_send_stage)

        self.assertIn("The Odyssey", seen_candidates[1])
        self.assertFalse(session.awaiting_book_clarification)
        self.assertEqual(session.book.title, "The Odyssey")
        self.assertNotEqual(card2.title, "Which book are you reading?")
        self.assertEqual(card2.book.title, "The Odyssey")
        self.assertEqual(card2.sources, [])
        self.assertEqual(len(self._stub_reason.calls), 1)

    async def test_clarify_reply_longer_title_does_not_match_existing_substring(self):
        """Greptile P1: 'I'm reading Hamlet's Mill' must add 'Hamlet's Mill', not select 'Hamlet'."""
        dec_result = DecisionResult(
            action="clarify",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=False,
            speak_only=False,
            confidence=0.90,
            fallback_used=False,
            raw_utterance="what is this?",
            book_match="unknown",
            book_match_confidence=0.35,
            book_changed=False,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        turn1 = Invoke(
            type="invoke", request_id="r-hm-1", session_id="s-hm-substr",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what is this?",
        )
        turn2 = Invoke(
            type="invoke", request_id="r-hm-2", session_id="s-hm-substr",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="I'm reading Hamlet's Mill.",
        )
        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Archaic myth and precession notes"), \
             mock.patch.object(pipeline, "draw", new_callable=mock.AsyncMock, return_value="https://example.com/hm.png"), \
             mock.patch.object(pipeline, "speak", new_callable=mock.AsyncMock, return_value="https://example.com/hm.wav"):
            card1 = await pipeline.run(turn1, _noop_send_stage)
            self.assertEqual(card1.title, "Which book are you reading?")
            card2 = await pipeline.run(turn2, _noop_send_stage)

        session = default_session_store.get("s-hm-substr")
        titles = [b.title for b in session.candidate_books]
        self.assertIn("Hamlet's Mill", titles)
        self.assertEqual(session.book.title, "Hamlet's Mill")
        self.assertEqual(card2.book.title, "Hamlet's Mill")

    async def test_cancelled_clarification_restores_pending_flag(self):
        """Greptile P1: cancelling mid-clarification leaves awaiting_book_clarification False."""
        dec_result = DecisionResult(
            action="clarify",
            task_tier="fast",
            recommended_model="gemini-3.5-flash-lite",
            needs_image=False,
            speak_only=False,
            confidence=0.90,
            fallback_used=False,
            raw_utterance="what is this?",
            book_match="unknown",
            book_match_confidence=0.35,
            book_changed=False,
        )
        set_decision_client(StubDecisionClient(default_result=dec_result))

        async def _cancel_speak(*args, **kwargs):
            raise asyncio.CancelledError()

        turn1 = Invoke(
            type="invoke", request_id="r-canc-1", session_id="s-canc-clr",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="what is this?",
        )
        turn2 = Invoke(
            type="invoke", request_id="r-canc-2", session_id="s-canc-clr",
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Unrecognized excerpt here"), \
             mock.patch.object(pipeline, "speak", new_callable=mock.AsyncMock, side_effect=_cancel_speak):
            with self.assertRaises(asyncio.CancelledError):
                await pipeline.run(turn1, _noop_send_stage)

        session = default_session_store.get("s-canc-clr")
        self.assertFalse(session.awaiting_book_clarification)

        with mock.patch.dict(os.environ, {"DYNAMIC_MODEL_ROUTING": "true"}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Unrecognized excerpt here"), \
             mock.patch.object(pipeline, "speak", new_callable=mock.AsyncMock, return_value=None):
            await pipeline.run(turn2, _noop_send_stage)

        self.assertNotEqual(session.book.title, "explain")


class _ModelLikeReasoningClient:
    """Answers like a model that guesses Hamlet coordinates and a citation for every page, then
    applies the production parser, so these tests see what a live card would carry."""

    def __init__(self) -> None:
        self.calls: list = []

    async def generate_reasoning(self, command, page_text, session, model=DEFAULT_MODEL_REASON, passage_match=None):
        self.calls.append(passage_match)
        guessed = json.dumps({
            "title": "Hamlet, Act 4, Scene 7",
            "caption": "A guessed caption.",
            "speech_text": "A guessed explanation.",
            "image_prompt": "A guessed prompt, pure black background (#000000).",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 4, Scene 7, line 1"},
            "sources": [{"title": "Invented edition", "url": "https://example.com/hamlet"}],
        })
        return parse_reasoning_json(guessed, session, passage_match=passage_match)


# Act/scene from the standard Hamlet act and scene division (Folger/Arden), not from our corpus.
# Line numbers differ between editions, so only act and scene are checked against the reference.
_HAMLET_REFERENCE = [
    ("Frailty, thy name is woman!", "Act 1, Scene 2"),
    ("Neither a borrower nor a lender be", "Act 1, Scene 3"),
    ("Something is rotten in the state of Denmark.", "Act 1, Scene 4"),
    ("Brevity is the soul of wit", "Act 2, Scene 2"),
    ("To be, or not to be, that is the question", "Act 3, Scene 1"),
    ("The lady doth protest too much, methinks.", "Act 3, Scene 2"),
    ("Alas, poor Yorick! I knew him, Horatio", "Act 5, Scene 1"),
]

_NOT_HAMLET = [
    "Call me Ishmael. Some years ago, never mind how long precisely",
    "It is a truth universally acknowledged, that a single man in possession of a good fortune",
    "Is this a dagger which I see before me, the handle toward my hand?",
]


class PipelineCitationReferenceTest(unittest.IsolatedAsyncioTestCase):
    """REQ-SRC-01, REQ-BASE-01: citations on the card come from the source text, never the model."""

    def setUp(self):
        default_session_store.clear()
        self._client = _ModelLikeReasoningClient()
        set_reasoning_client(self._client)
        self._env_patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"})
        self._env_patch.start()
        os.environ.pop("DYNAMIC_MODEL_ROUTING", None)

    def tearDown(self):
        self._env_patch.stop()
        set_reasoning_client(None)
        default_session_store.clear()

    async def _card_for(self, page: str, session_id: str):
        invoke = Invoke(
            type="invoke", request_id=f"r-{session_id}", session_id=session_id,
            frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain",
        )
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value=page), \
             mock.patch.object(pipeline, "draw", new_callable=mock.AsyncMock, return_value=None), \
             mock.patch.object(pipeline, "speak", new_callable=mock.AsyncMock, return_value=None):
            return await pipeline.run(invoke, _noop_send_stage)

    async def test_reference_passages_cite_act_scene_line_and_source_text(self):
        for i, (page, act_scene) in enumerate(_HAMLET_REFERENCE):
            with self.subTest(page=page):
                card = await self._card_for(page, f"s-ref-{i}")
                self.assertEqual(card.book.title, "Hamlet")
                self.assertTrue(card.book.location.startswith(act_scene + ", line"), card.book.location)
                self.assertRegex(card.book.location, r", lines? \d+(-\d+)?$")
                self.assertEqual(card.title, f"Hamlet, {card.book.location}")
                self.assertEqual(card.sources[0].url, "https://www.gutenberg.org/ebooks/1524")

    async def test_other_books_take_the_no_source_path(self):
        for i, page in enumerate(_NOT_HAMLET):
            with self.subTest(page=page):
                card = await self._card_for(page, f"s-other-{i}")
                self.assertIsNone(self._client.calls[-1])
                self.assertEqual(card.sources, [])
                self.assertEqual(card.book.location, pipeline.NO_SOURCE_TEXT)
                self.assertNotRegex(card.title, r"Act \d|Scene \d|line \d")


class PipelineTerminalReplyTest(unittest.IsolatedAsyncioTestCase):
    """#133 part 2: a request that does not end in a card leaves the book session exactly as it
    found it (history, active book, candidates, location), and no spoken clip outlives it."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "DYNAMIC_MODEL_ROUTING": "false"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session_id = f"s-terminal-{self._testMethodName}"
        self.session = default_session_store.get_or_create(self.session_id)
        self.session.add_exchange(question="earlier", answer="earlier answer")
        self.history = list(self.session.history)
        self.book = self.session.book
        self.candidates = list(self.session.candidate_books)
        self.fields = [(b.title, b.author, b.location) for b in self.candidates]

    def invoke(self):
        return Invoke(type="invoke", request_id="r-terminal", session_id=self.session_id,
                      frame=Frame(mime="image/jpeg", b64="AAAA"), text="explain")

    async def think_that_records(self, command, page_text, session_id, *, model=None, passage_match=None):
        # What ai.think does to the session before the picture is drawn.
        session = default_session_store.get_or_create(session_id)
        session.add_exchange(question=command, answer="unseen answer")
        session.update_location("Act 9, Scene 9")
        session.set_active_book("Moby-Dick", "Herman Melville", "Chapter 1")
        return dict(_STUB_ANSWER, sources=[{"title": "Gutenberg", "url": "https://www.gutenberg.org/ebooks/1524"}])

    def assert_session_untouched(self):
        self.assertEqual(self.session.history, self.history)
        self.assertIs(self.session.book, self.book)
        self.assertEqual(self.session.candidate_books, self.candidates)
        self.assertEqual([(b.title, b.author, b.location) for b in self.candidates], self.fields)

    def patches(self, draw, speak=None):
        return (mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="Some page text"),
                mock.patch.object(pipeline, "_ai_think", self.think_that_records),
                mock.patch.object(pipeline, "draw", draw),
                mock.patch.object(pipeline, "speak", speak or mock.AsyncMock(return_value=None)))

    async def run_with(self, draw, speak=None, request_timeout=None):
        p = self.patches(draw, speak)
        with p[0], p[1], p[2], p[3]:
            if request_timeout is None:
                return await pipeline.run(self.invoke(), mock.AsyncMock())
            with mock.patch.object(pipeline, "REQUEST_TIMEOUT_S", request_timeout):
                return await pipeline.run(self.invoke(), mock.AsyncMock())

    async def test_a_failed_request_restores_the_session(self):
        async def failing_draw(*args, **kwargs):
            raise pipeline.PipelineError("internal", "Something went wrong. Try again.", True)
        with self.assertRaises(pipeline.PipelineError):
            await self.run_with(failing_draw)
        self.assert_session_untouched()

    async def test_a_request_timeout_restores_the_session(self):
        async def slow_draw(*args, **kwargs):
            await asyncio.sleep(5)
        with self.assertRaises(pipeline.PipelineError) as caught:
            await self.run_with(slow_draw, request_timeout=0.2)
        self.assertEqual(caught.exception.code, "model_timeout")
        self.assert_session_untouched()

    async def test_a_cancelled_request_restores_the_book_too(self):
        started = asyncio.Event()

        async def slow_draw(*args, **kwargs):
            started.set()
            await asyncio.sleep(5)
        p = self.patches(slow_draw)
        with p[0], p[1], p[2], p[3]:
            task = asyncio.create_task(pipeline.run(self.invoke(), mock.AsyncMock()))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assert_session_untouched()

    async def test_a_timeout_while_waiting_for_speech_stops_the_speech(self):
        stopped = asyncio.Event()

        async def slow_speak(*args, **kwargs):
            try:
                await asyncio.sleep(5)
            finally:
                stopped.set()
        with self.assertRaises(pipeline.PipelineError):
            await self.run_with(mock.AsyncMock(return_value=None), slow_speak, request_timeout=0.2)
        await asyncio.sleep(0)
        self.assertTrue(stopped.is_set(), "the speech task kept running after the request ended")
        self.assert_session_untouched()

    async def test_a_draw_failure_stops_the_speech(self):
        stopped = asyncio.Event()

        async def slow_speak(*args, **kwargs):
            try:
                await asyncio.sleep(5)
            finally:
                stopped.set()

        async def failing_draw(*args, **kwargs):
            await asyncio.sleep(0)
            raise pipeline.PipelineError("internal", "Something went wrong. Try again.", True)
        with self.assertRaises(pipeline.PipelineError):
            await self.run_with(failing_draw, slow_speak)
        await asyncio.sleep(0)
        self.assertTrue(stopped.is_set(), "the speech task kept running after the draw failed")
        self.assert_session_untouched()

    async def test_a_failure_after_speech_discards_the_clip(self):
        clip = "https://example.modal.run/audio/clip-1.wav"
        with mock.patch.object(pipeline, "discard_clip") as discard, \
             mock.patch.object(pipeline, "contract_card", side_effect=ValueError("bad card")):
            with self.assertRaises(ValueError):
                await self.run_with(mock.AsyncMock(return_value=None), mock.AsyncMock(return_value=clip))
        discard.assert_called_once_with(clip)
        self.assert_session_untouched()

    async def test_a_failed_request_does_not_advance_the_reading_horizon(self):
        # #197 adds max_position and seen_passages; a failed request must not move them.
        self.session.max_position = (1, 2, 30)
        self.session.seen_passages = ["an earlier page"]

        async def think_that_reads_ahead(command, page_text, session_id, *, model=None, passage_match=None):
            session = default_session_store.get_or_create(session_id)
            session.max_position = (5, 1, 1)
            session.seen_passages.append("a later page")
            return dict(_STUB_ANSWER)

        async def failing_draw(*args, **kwargs):
            raise pipeline.PipelineError("internal", "Something went wrong. Try again.", True)
        p = self.patches(failing_draw)
        with p[0], mock.patch.object(pipeline, "_ai_think", think_that_reads_ahead), p[2], p[3]:
            with self.assertRaises(pipeline.PipelineError):
                await pipeline.run(self.invoke(), mock.AsyncMock())
        self.assertEqual(self.session.max_position, (1, 2, 30))
        self.assertEqual(self.session.seen_passages, ["an earlier page"])

    async def test_a_card_keeps_the_new_exchange(self):
        card = await self.run_with(mock.AsyncMock(return_value=None))
        self.assertEqual(card.type, "card")
        self.assertEqual(len(self.session.history), len(self.history) + 1)
        self.assertEqual(self.session.book.title, "Moby-Dick")


if __name__ == "__main__":
    unittest.main()
