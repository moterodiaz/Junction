"""Tests for Gemini Decisions API module (backend/ai/decision.py, Issue #185).

Offline tests covering:
1. DecisionQuestionSpec registry and modular registration
2. DecisionResult dataclass and model resolution by tier
3. Heuristic fallback (L0 commands via match_command + safe keywords)
4. StubDecisionClient for offline testing and dependency injection
5. decide() behavior: timeout, error handling, low-confidence fallback, no API key
6. GeminiDecisionClient interaction formatting and response parsing
7. REQ-PRIV-02 privacy verification: user text and page text never logged
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import unittest
from unittest import mock

from ai.decision import (
    DEFAULT_MODEL_BALANCED,
    DEFAULT_MODEL_DECISION,
    DEFAULT_MODEL_DEEP,
    DEFAULT_MODEL_FAST,
    DecisionError,
    DecisionQuestionSpec,
    DecisionResult,
    GeminiDecisionClient,
    StubDecisionClient,
    decide,
    fallback_decide,
    get_all_question_specs,
    get_decision_client,
    get_effective_timeout,
    get_question_spec,
    register_question_spec,
    reset_question_specs,
    resolve_model_for_tier,
    set_decision_client,
)
from ai.session import BookInfo, BookSession


class DecisionRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_question_specs()

    def tearDown(self) -> None:
        reset_question_specs()

    def test_default_specs_registered(self) -> None:
        specs = get_all_question_specs()
        self.assertIn("action", specs)
        self.assertIn("task_tier", specs)
        self.assertIn("needs_image", specs)
        self.assertIn("speak_only", specs)

        action_spec = get_question_spec("action")
        self.assertIsNotNone(action_spec)
        self.assertEqual(action_spec.question_type, "choice")
        self.assertIn("explain", action_spec.criteria)
        self.assertIn("draw", action_spec.criteria)
        self.assertIn("who_is_this", action_spec.criteria)

    def test_custom_spec_registration_and_reset(self) -> None:
        custom = DecisionQuestionSpec(
            name="reading_level",
            question_type="choice",
            instructions="Identify the reader grade level",
            criteria={"hs": "High school", "college": "College"},
            default="hs",
        )
        register_question_spec(custom)
        self.assertEqual(get_question_spec("reading_level"), custom)

        reset_question_specs()
        self.assertIsNone(get_question_spec("reading_level"))


class DecisionResultAndTierTest(unittest.TestCase):
    def test_result_dataclass_and_to_dict(self) -> None:
        res = DecisionResult(
            action="explain",
            task_tier="balanced",
            recommended_model="gemini-4-argon",
            needs_image=False,
            speak_only=False,
            confidence=0.98,
            fallback_used=False,
            raw_utterance="explain line 5",
            extra_answers={"topic": "ghost"},
        )
        d = res.to_dict()
        self.assertEqual(d["action"], "explain")
        self.assertEqual(d["task_tier"], "balanced")
        self.assertEqual(d["recommended_model"], "gemini-4-argon")
        self.assertFalse(d["needs_image"])
        self.assertFalse(d["speak_only"])
        self.assertAlmostEqual(d["confidence"], 0.98)
        self.assertFalse(d["fallback_used"])
        self.assertEqual(d["raw_utterance"], "explain line 5")
        self.assertEqual(d["extra_answers"], {"topic": "ghost"})

    def test_resolve_model_for_tier_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_model_for_tier("fast"), DEFAULT_MODEL_FAST)
            self.assertEqual(resolve_model_for_tier("balanced"), DEFAULT_MODEL_BALANCED)
            self.assertEqual(resolve_model_for_tier("deep"), DEFAULT_MODEL_DEEP)
            self.assertEqual(resolve_model_for_tier("unknown"), DEFAULT_MODEL_BALANCED)

    def test_resolve_model_for_tier_overrides(self) -> None:
        env = {
            "MODEL_REASON_FAST": "custom-fast",
            "MODEL_REASON": "custom-balanced",
            "MODEL_REASON_DEEP": "custom-deep",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_model_for_tier("fast"), "custom-fast")
            self.assertEqual(resolve_model_for_tier("balanced"), "custom-balanced")
            self.assertEqual(resolve_model_for_tier("deep"), "custom-deep")

    def test_resolve_model_for_tier_blank_falls_back(self) -> None:
        env = {"MODEL_REASON_FAST": "  ", "MODEL_REASON": "", "MODEL_REASON_DEEP": " "}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_model_for_tier("fast"), DEFAULT_MODEL_FAST)
            self.assertEqual(resolve_model_for_tier("balanced"), DEFAULT_MODEL_BALANCED)
            self.assertEqual(resolve_model_for_tier("deep"), DEFAULT_MODEL_DEEP)

    def test_get_decision_client_reads_model_decision(self) -> None:
        from ai.decision import get_decision_client, set_decision_client

        set_decision_client(None)
        try:
            with mock.patch.dict(os.environ, {"MODEL_DECISION": "custom-decision"}):
                client = get_decision_client()
            self.assertEqual(client.default_model, "custom-decision")
        finally:
            set_decision_client(None)

    def test_effective_timeout(self) -> None:
        # Respect upper bound <= 2.0s
        self.assertEqual(get_effective_timeout(1.5), 1.5)
        self.assertEqual(get_effective_timeout(5.0), 2.0)
        self.assertEqual(get_effective_timeout(None), 2.0)

        with mock.patch.dict(os.environ, {"DECISION_TIMEOUT_S": "1.2"}):
            self.assertEqual(get_effective_timeout(2.0), 1.2)
            self.assertEqual(get_effective_timeout(0.8), 0.8)


class FallbackDecideTest(unittest.TestCase):
    def test_l0_commands_via_match_command(self) -> None:
        res_explain = fallback_decide("could you explain what this means?")
        self.assertEqual(res_explain.action, "explain")
        self.assertEqual(res_explain.task_tier, "balanced")
        self.assertFalse(res_explain.needs_image)
        self.assertFalse(res_explain.speak_only)
        self.assertTrue(res_explain.fallback_used)
        self.assertEqual(res_explain.confidence, 0.0)

        res_draw = fallback_decide("please draw Hamlet seeing his father")
        self.assertEqual(res_draw.action, "draw")
        self.assertEqual(res_draw.task_tier, "fast")
        self.assertTrue(res_draw.needs_image)
        self.assertTrue(res_draw.fallback_used)

        res_who = fallback_decide("who is this character on stage?")
        self.assertEqual(res_who.action, "who_is_this")
        self.assertEqual(res_who.task_tier, "fast")
        self.assertFalse(res_who.needs_image)
        self.assertTrue(res_who.fallback_used)

    def test_keyword_fallback(self) -> None:
        res_empty = fallback_decide("")
        self.assertEqual(res_empty.action, "clarify")
        self.assertTrue(res_empty.speak_only)

        res_question = fallback_decide("why does he hesitate to act?")
        self.assertEqual(res_question.action, "question")
        self.assertEqual(res_question.task_tier, "balanced")

        res_draw_kw = fallback_decide("can you sketch a picture of the castle?")
        self.assertEqual(res_draw_kw.action, "draw")
        self.assertTrue(res_draw_kw.needs_image)


class DecideAsyncTest(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        set_decision_client(None)

    async def test_stub_client_normal_invocation(self) -> None:
        stub = StubDecisionClient()
        set_decision_client(stub)

        session = BookSession(
            session_id="s1",
            book=BookInfo(title="Hamlet", author="Shakespeare", location="Act 3, Scene 1"),
        )
        res = await decide("draw the ghost", page_text="Enter Ghost.", session=session)

        self.assertEqual(res.action, "draw")
        self.assertTrue(res.needs_image)
        self.assertFalse(res.fallback_used)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.calls[0]["session_id"], "s1")
        self.assertEqual(stub.calls[0]["page_text"], "Enter Ghost.")

    async def test_stub_client_answers_parsing(self) -> None:
        answers = {
            "action": {"type": "choice", "choice": "who_is_this", "confidence": 0.95},
            "task_tier": {"type": "choice", "choice": "fast", "confidence": 0.91},
            "needs_image": {"type": "noul", "noul": 0.0, "confidence": 0.99},
            "speak_only": {"type": "noul", "noul": 0.0, "confidence": 0.98},
        }
        stub = StubDecisionClient(default_answers=answers)
        set_decision_client(stub)

        res = await decide("who is Claudius?")
        self.assertEqual(res.action, "who_is_this")
        self.assertEqual(res.task_tier, "fast")
        self.assertEqual(res.recommended_model, DEFAULT_MODEL_FAST)
        self.assertFalse(res.needs_image)
        self.assertFalse(res.fallback_used)
        self.assertAlmostEqual(res.confidence, 0.91)

    async def test_timeout_falls_back_gracefully(self) -> None:
        stub = StubDecisionClient(latency_s=0.5)
        set_decision_client(stub)

        # Timeout set to 0.05s, shorter than latency
        res = await decide("draw the sword", timeout_s=0.05)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.action, "draw")
        self.assertTrue(res.needs_image)

    async def test_exception_falls_back_gracefully(self) -> None:
        stub = StubDecisionClient(fail=True)
        set_decision_client(stub)

        res = await decide("explain line 10")
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.action, "explain")

    async def test_low_confidence_falls_back_gracefully(self) -> None:
        low_conf_result = DecisionResult(
            action="clarify",
            task_tier="balanced",
            recommended_model=DEFAULT_MODEL_BALANCED,
            needs_image=False,
            speak_only=False,
            confidence=0.35,  # below 0.50 threshold
            fallback_used=False,
            raw_utterance="explain this clearly",
        )
        stub = StubDecisionClient(default_result=low_conf_result)
        set_decision_client(stub)

        res = await decide("explain this clearly")
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.action, "explain")

    async def test_missing_api_key_uses_fast_fallback(self) -> None:
        set_decision_client(GeminiDecisionClient(api_key=""))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=True):
            res = await decide("draw an apple")
            self.assertTrue(res.fallback_used)
            self.assertEqual(res.action, "draw")


class GeminiDecisionClientIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_client_mock_aio_decisions(self) -> None:
        client = GeminiDecisionClient(api_key="test-key")

        mock_answer_action = mock.Mock()
        mock_answer_action.choice = "explain"
        mock_answer_action.confidence = 0.96

        mock_answer_tier = mock.Mock()
        mock_answer_tier.choice = "balanced"
        mock_answer_tier.confidence = 0.94

        mock_answer_img = mock.Mock()
        mock_answer_img.noul = 0.0
        mock_answer_img.confidence = 0.98

        mock_answer_spk = mock.Mock()
        mock_answer_spk.noul = 0.0
        mock_answer_spk.confidence = 0.97

        mock_response = mock.Mock()
        mock_response.answers = {
            "action": mock_answer_action,
            "task_tier": mock_answer_tier,
            "needs_image": mock_answer_img,
            "speak_only": mock_answer_spk,
        }

        mock_create = mock.AsyncMock(return_value=mock_response)
        mock_aio_decisions = mock.Mock()
        mock_aio_decisions.create = mock_create

        mock_genai_client = mock.Mock()
        mock_genai_client.aio.decisions = mock_aio_decisions

        with mock.patch("google.genai.Client", return_value=mock_genai_client):
            res = await client.decide(
                utterance="explain the passage",
                page_text="To be or not to be",
                model="gemini-decision-1",
            )

            self.assertEqual(res.action, "explain")
            self.assertEqual(res.task_tier, "balanced")
            self.assertEqual(res.recommended_model, DEFAULT_MODEL_BALANCED)
            self.assertFalse(res.needs_image)
            self.assertFalse(res.speak_only)
            self.assertAlmostEqual(res.confidence, 0.94)
            self.assertFalse(res.fallback_used)

            mock_create.assert_awaited_once()
            _, kwargs = mock_create.call_args
            self.assertIn("Student Utterance: explain the passage", kwargs["input"])
            self.assertIn("Page Text:\nTo be or not to be", kwargs["input"])
            self.assertEqual(kwargs["model"], "models/gemini-decision-1")
            self.assertEqual(kwargs["api_version"], "v1beta")
            self.assertIn("action", kwargs["questions"])
            self.assertIn("task_tier", kwargs["questions"])
            self.assertIn("needs_image", kwargs["questions"])
            self.assertIn("speak_only", kwargs["questions"])


class PrivacyReqTest(unittest.IsolatedAsyncioTestCase):
    """REQ-PRIV-02: Logs and error replies never contain user text, audio or frame data."""

    def tearDown(self) -> None:
        set_decision_client(None)

    async def test_user_utterance_and_page_text_never_logged_on_failure(self) -> None:
        secret_utterance = "SECRET_STUDENT_QUESTION_XYZZY"
        secret_page_text = "SECRET_PAGE_CONTENT_98765"

        stub = StubDecisionClient(fail=True)
        set_decision_client(stub)

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("metalab.ai.decision")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            res = await decide(secret_utterance, page_text=secret_page_text)
            self.assertTrue(res.fallback_used)
        finally:
            logger.removeHandler(handler)

        logs = log_capture.getvalue()
        self.assertNotIn(secret_utterance, logs, "User utterance must never appear in logs (REQ-PRIV-02)")
        self.assertNotIn(secret_page_text, logs, "Page text must never appear in logs (REQ-PRIV-02)")

    async def test_user_utterance_and_page_text_never_logged_on_timeout(self) -> None:
        secret_utterance = "SECRET_UTTERANCE_TIMEOUT_FOOBAR"
        secret_page_text = "SECRET_PAGE_TIMEOUT_BARBAZ"

        stub = StubDecisionClient(latency_s=0.5)
        set_decision_client(stub)

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("metalab.ai.decision")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            res = await decide(secret_utterance, page_text=secret_page_text, timeout_s=0.02)
            self.assertTrue(res.fallback_used)
        finally:
            logger.removeHandler(handler)

        logs = log_capture.getvalue()
        self.assertNotIn(secret_utterance, logs, "User utterance must never appear in logs (REQ-PRIV-02)")
        self.assertNotIn(secret_page_text, logs, "Page text must never appear in logs (REQ-PRIV-02)")


if __name__ == "__main__":
    unittest.main()
