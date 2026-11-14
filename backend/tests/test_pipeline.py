"""Pipeline wiring tests: key-set uses ai.think; key-unset returns offline stub dict."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from ai.reasoning import DEFAULT_MODEL_REASON, StubGeminiClient, set_reasoning_client
from ai.session import default_session_store
from app import pipeline
from app.messages import Invoke, Media

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


_INVOKE = Invoke(
    type="invoke",
    request_id="r-run",
    session_id="s-run",
    frame=Media(mime="image/jpeg", b64="AAAA"),
    text="explain",
)

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
        default_session_store.clear()
        self._stub = StubGeminiClient(default_answer=_STUB_ANSWER_WITH_SOURCES)
        set_reasoning_client(self._stub)
        self._env_patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"})
        self._env_patch.start()
        os.environ.pop("MODEL_REASON", None)  # restored when the patch stops; keeps default-model asserts hermetic

    def tearDown(self):
        self._env_patch.stop()
        set_reasoning_client(None)
        default_session_store.clear()

    async def test_sources_populated_and_reason_model_reported(self):
        """Live path: card.sources mirrors Gemini sources; models.reason is DEFAULT_MODEL_REASON."""
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
            card = await pipeline.run(_INVOKE, _noop_send_stage)
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
            card = await pipeline.run(_INVOKE, _noop_send_stage)
        self.assertEqual(len(card.sources), 2)
        self.assertEqual(card.sources[0].url, "https://example.com/good")
        self.assertEqual(card.sources[1].url, "https://example.com/no-title")
        self.assertEqual(card.sources[1].title, "Source")

    async def test_model_reason_env_var_is_used_in_live_path(self):
        """Thread 1: MODEL_REASON env var is passed to ai.think and reflected in models.reason."""
        custom_model = "gemini-custom-7b"
        with mock.patch.dict(os.environ, {"MODEL_REASON": custom_model}), \
             mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page"):
            card = await pipeline.run(_INVOKE, _noop_send_stage)
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
            card = await pipeline.run(_INVOKE, _noop_send_stage)
        self.assertEqual(len(card.sources), 1)
        self.assertEqual(card.sources[0].url, "https://example.com/ok")


class PipelineRunOfflinePathTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("NVIDIA_API_KEY", None)

    def tearDown(self):
        self._env_patch.stop()

    async def test_sources_empty_and_reason_model_is_stub(self):
        """Offline path: card.sources is empty; models.reason is 'stub'."""
        with mock.patch.object(pipeline, "read_page", new_callable=mock.AsyncMock, return_value="page text"):
            card = await pipeline.run(_INVOKE, _noop_send_stage)
        self.assertEqual(card.sources, [])
        self.assertEqual(card.models["reason"], "stub")


if __name__ == "__main__":
    unittest.main()
