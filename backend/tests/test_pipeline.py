"""Pipeline wiring tests: key-set uses ai.think; key-unset returns offline stub dict."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from ai.reasoning import StubGeminiClient, set_reasoning_client
from ai.session import default_session_store
from app import pipeline

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


if __name__ == "__main__":
    unittest.main()
