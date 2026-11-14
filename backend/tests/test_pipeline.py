"""Pipeline wiring tests: key-set uses ai.think; key-unset returns offline stub dict."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from ai.decision import DecisionResult, StubDecisionClient, set_decision_client
from ai.reasoning import DEFAULT_MODEL_REASON, StubGeminiClient, set_reasoning_client
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
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
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
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
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
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
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
        self.assertEqual(card.title, "Hamlet, Act 3, Scene 1")

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


if __name__ == "__main__":
    unittest.main()
