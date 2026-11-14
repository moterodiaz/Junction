"""Gemini Decisions API module (PRD section 2, section 4, section 5, #185).

Provides single-pass decision routing using Gemini Decisions API
(`gemini-decision-1` on v1beta via `client.aio.decisions.create`).
Evaluates structured questions (action, task_tier, needs_image, speak_only)
against student utterance and context, with clean fallback to heuristic routing
on error, timeout, low confidence, or missing API key.

Privacy requirement REQ-PRIV-02:
Logs and error messages NEVER contain user text, transcripts, or page text.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import os
from typing import Any, Dict, List, Optional, Protocol, Union

from .session import BookSession

try:
    from stt.commands import match_command
except ImportError:
    match_command = None

log = logging.getLogger("metalab.ai.decision")

DEFAULT_MODEL_DECISION = "gemini-decision-1"
DEFAULT_MODEL_FAST = "gemini-3.5-flash-lite"
DEFAULT_MODEL_BALANCED = "gemini-4-argon"
DEFAULT_MODEL_DEEP = "gemini-4-carbon"
DEFAULT_DECISION_TIMEOUT_S = 2.0
MIN_CONFIDENCE_THRESHOLD = 0.5


class DecisionError(RuntimeError):
    """Raised when decision evaluation fails."""


@dataclass
class DecisionQuestionSpec:
    """Specification for a decision question evaluated in Decisions API."""

    name: str
    question_type: str  # "choice", "noul", "score"
    instructions: str
    criteria: Optional[Dict[str, str]] = None
    default: Any = None


@dataclass
class DecisionResult:
    """Structured result of single-pass decision routing."""

    action: str  # explain, draw, who_is_this, question, clarify
    task_tier: str  # fast, balanced, deep
    recommended_model: str  # mapped from task_tier
    needs_image: bool
    speak_only: bool
    confidence: float
    fallback_used: bool
    raw_utterance: str
    extra_answers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "task_tier": self.task_tier,
            "recommended_model": self.recommended_model,
            "needs_image": self.needs_image,
            "speak_only": self.speak_only,
            "confidence": self.confidence,
            "fallback_used": self.fallback_used,
            "raw_utterance": self.raw_utterance,
            "extra_answers": dict(self.extra_answers),
        }


def _create_default_specs() -> Dict[str, DecisionQuestionSpec]:
    return {
        "action": DecisionQuestionSpec(
            name="action",
            question_type="choice",
            instructions="Classify the user intent into one primary action category.",
            criteria={
                "explain": "User asks for explanation, translation, or summary of the passage or concept",
                "draw": "User asks to draw, visualize, generate an illustration, or see what something looks like",
                "who_is_this": "User asks who a character/person is or asks about their identity",
                "question": "User asks a specific factual or contextual question about the scene or play",
                "clarify": "Utterance is ambiguous, inaudible, unintelligible, or requires clarification",
            },
            default="explain",
        ),
        "task_tier": DecisionQuestionSpec(
            name="task_tier",
            question_type="choice",
            instructions="Classify the reasoning complexity and latency tier required to handle this utterance.",
            criteria={
                "fast": "Simple factual question, definition, quick identity lookup, or concise answer",
                "balanced": "Standard literary explanation, scene context, character motivation, or visual illustration",
                "deep": "Complex thematic analysis, multi-layered literary comparison, historical context, or deep synthesis",
            },
            default="balanced",
        ),
        "needs_image": DecisionQuestionSpec(
            name="needs_image",
            question_type="noul",
            instructions="Does fulfilling the user request require generating a visual image or illustration?",
            default=False,
        ),
        "speak_only": DecisionQuestionSpec(
            name="speak_only",
            question_type="noul",
            instructions="Should the response be spoken audio only without updating or displaying a visual card or illustration?",
            default=False,
        ),
    }


# Modular registry for Order 2-5 extensibility
_QUESTION_REGISTRY: Dict[str, DecisionQuestionSpec] = _create_default_specs()


def register_question_spec(spec: DecisionQuestionSpec) -> None:
    """Register or override a question spec in the modular decision registry."""
    _QUESTION_REGISTRY[spec.name] = spec


def get_question_spec(name: str) -> Optional[DecisionQuestionSpec]:
    """Retrieve a registered question spec by name."""
    return _QUESTION_REGISTRY.get(name)


def get_all_question_specs() -> Dict[str, DecisionQuestionSpec]:
    """Return a copy of all registered question specs."""
    return dict(_QUESTION_REGISTRY)


def reset_question_specs() -> None:
    """Reset registry to the default core questions."""
    global _QUESTION_REGISTRY
    _QUESTION_REGISTRY = _create_default_specs()


def resolve_model_for_tier(task_tier: str) -> str:
    """Map task tier to recommended model using environment variables with defaults."""
    tier = (task_tier or "").lower().strip()
    if tier == "fast":
        return os.environ.get("MODEL_REASON_FAST", "").strip() or DEFAULT_MODEL_FAST
    elif tier == "deep":
        return os.environ.get("MODEL_REASON_DEEP", "").strip() or DEFAULT_MODEL_DEEP
    else:
        return os.environ.get("MODEL_REASON", "").strip() or DEFAULT_MODEL_BALANCED


def get_effective_timeout(timeout_s: Optional[float] = None) -> float:
    """Compute effective timeout, respecting DECISION_TIMEOUT_S <= 2.0s."""
    t = timeout_s if timeout_s is not None else DEFAULT_DECISION_TIMEOUT_S
    env_timeout = os.environ.get("DECISION_TIMEOUT_S")
    if env_timeout:
        try:
            env_val = float(env_timeout)
            t = min(t, env_val)
        except ValueError:
            pass
    return max(0.01, min(t, 2.0))


def fallback_decide(utterance: str) -> DecisionResult:
    """Heuristic fallback using match_command and safe keywords.
    
    Safe fallback: NEVER raises and NEVER logs utterance text.
    """
    cmd = None
    if match_command is not None:
        try:
            cmd = match_command(utterance)
        except Exception:
            cmd = None

    if cmd == "explain":
        action = "explain"
        task_tier = "balanced"
        needs_image = False
        speak_only = False
    elif cmd == "draw":
        action = "draw"
        task_tier = "fast"
        needs_image = True
        speak_only = False
    elif cmd == "who_is_this":
        action = "who_is_this"
        task_tier = "fast"
        needs_image = False
        speak_only = False
    else:
        text = (utterance or "").strip().lower()
        if not text:
            action = "clarify"
            task_tier = "fast"
            needs_image = False
            speak_only = True
        elif any(w in text for w in ("draw", "paint", "sketch", "picture", "illustration", "show me")):
            action = "draw"
            task_tier = "fast"
            needs_image = True
            speak_only = False
        elif any(w in text for w in ("who is", "who's", "whose", "who are", "who was", "who were")):
            action = "who_is_this"
            task_tier = "fast"
            needs_image = False
            speak_only = False
        elif "?" in text or text.startswith(("what", "why", "how", "where", "when", "is ", "can ", "could ", "does ")):
            action = "question"
            task_tier = "balanced"
            needs_image = False
            speak_only = False
        else:
            action = "explain"
            task_tier = "balanced"
            needs_image = False
            speak_only = False

    rec_model = resolve_model_for_tier(task_tier)

    extra: Dict[str, Any] = {}
    for name, spec in get_all_question_specs().items():
        if name not in ("action", "task_tier", "needs_image", "speak_only"):
            extra[name] = spec.default

    return DecisionResult(
        action=action,
        task_tier=task_tier,
        recommended_model=rec_model,
        needs_image=needs_image,
        speak_only=speak_only,
        confidence=0.0,
        fallback_used=True,
        raw_utterance=utterance,
        extra_answers=extra,
    )


def _parse_decision_response(
    response: Any,
    utterance: str,
    specs: Dict[str, DecisionQuestionSpec],
    active_names: List[str],
) -> DecisionResult:
    answers = getattr(response, "answers", None)
    if answers is None and isinstance(response, dict):
        answers = response.get("answers", {})
    if not answers:
        raise DecisionError("Decisions API returned no answers")

    def _get_val_and_conf(ans_obj: Any, q_type: str, default_val: Any) -> tuple[Any, float]:
        if ans_obj is None:
            return default_val, 1.0
        if isinstance(ans_obj, dict):
            conf = float(ans_obj.get("confidence", 1.0))
            if q_type == "choice":
                return ans_obj.get("choice", default_val), conf
            elif q_type == "noul":
                raw_noul = ans_obj.get("noul", default_val)
                return bool(float(raw_noul) >= 0.5), conf
            elif q_type == "score":
                return ans_obj.get("score", default_val), conf
            return default_val, conf

        conf = float(getattr(ans_obj, "confidence", 1.0))
        if q_type == "choice":
            val = getattr(ans_obj, "choice", default_val)
            return val, conf
        elif q_type == "noul":
            val = getattr(ans_obj, "noul", default_val)
            try:
                return bool(float(val) >= 0.5), conf
            except (ValueError, TypeError):
                return bool(val), conf
        elif q_type == "score":
            return getattr(ans_obj, "score", default_val), conf
        return default_val, conf

    # action
    act_spec = specs.get("action", DecisionQuestionSpec("action", "choice", "", default="explain"))
    action_val, action_conf = _get_val_and_conf(answers.get("action"), act_spec.question_type, act_spec.default)
    if action_val not in ("explain", "draw", "who_is_this", "question", "clarify"):
        action_val = act_spec.default

    # task_tier
    tier_spec = specs.get("task_tier", DecisionQuestionSpec("task_tier", "choice", "", default="balanced"))
    tier_val, tier_conf = _get_val_and_conf(answers.get("task_tier"), tier_spec.question_type, tier_spec.default)
    if tier_val not in ("fast", "balanced", "deep"):
        tier_val = tier_spec.default

    # needs_image
    img_spec = specs.get("needs_image", DecisionQuestionSpec("needs_image", "noul", "", default=False))
    needs_img_val, img_conf = _get_val_and_conf(answers.get("needs_image"), img_spec.question_type, img_spec.default)

    # speak_only
    spk_spec = specs.get("speak_only", DecisionQuestionSpec("speak_only", "noul", "", default=False))
    speak_val, speak_conf = _get_val_and_conf(answers.get("speak_only"), spk_spec.question_type, spk_spec.default)

    extra: Dict[str, Any] = {}
    extra_confs: List[float] = []
    for name in active_names:
        if name in ("action", "task_tier", "needs_image", "speak_only"):
            continue
        spec = specs.get(name)
        q_type = spec.question_type if spec else "choice"
        def_val = spec.default if spec else None
        v, c = _get_val_and_conf(answers.get(name), q_type, def_val)
        extra[name] = v
        extra_confs.append(c)

    all_confs = [action_conf, tier_conf, img_conf, speak_conf] + extra_confs
    overall_confidence = min(all_confs) if all_confs else 1.0
    rec_model = resolve_model_for_tier(tier_val)

    return DecisionResult(
        action=str(action_val),
        task_tier=str(tier_val),
        recommended_model=rec_model,
        needs_image=bool(needs_img_val),
        speak_only=bool(speak_val),
        confidence=float(overall_confidence),
        fallback_used=False,
        raw_utterance=utterance,
        extra_answers=extra,
    )


class DecisionClient(Protocol):
    """Protocol for decision routing clients."""

    async def decide(
        self,
        utterance: str,
        page_text: str = "",
        session: Optional[BookSession] = None,
        model: Optional[str] = None,
        timeout_s: float = 2.0,
        enabled_checks: Optional[List[str]] = None,
    ) -> DecisionResult:
        ...


class GeminiDecisionClient:
    """Real client invoking Google Gemini Decisions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = DEFAULT_MODEL_DECISION,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model

    async def decide(
        self,
        utterance: str,
        page_text: str = "",
        session: Optional[BookSession] = None,
        model: Optional[str] = None,
        timeout_s: float = 2.0,
        enabled_checks: Optional[List[str]] = None,
    ) -> DecisionResult:
        key = self.api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise DecisionError("GEMINI_API_KEY is not set")

        try:
            from google import genai
        except ImportError as exc:
            raise DecisionError("google-genai is not installed") from exc

        client = genai.Client(api_key=key)
        if not hasattr(client, "aio") or not hasattr(client.aio, "decisions"):
            raise DecisionError("google.genai client does not support client.aio.decisions")

        # Format input without logging
        parts: List[str] = []
        if session and getattr(session, "book", None):
            title = getattr(session.book, "title", "")
            author = getattr(session.book, "author", "")
            location = getattr(session.book, "location", "")
            parts.append(f"Book: {title} ({author})\nLocation: {location}")
        if page_text:
            parts.append(f"Page Text:\n{page_text}")
        parts.append(f"Student Utterance: {utterance}")
        shared_input = "\n\n".join(parts)

        all_specs = get_all_question_specs()
        active_names = (
            [name for name in enabled_checks if name in all_specs]
            if enabled_checks is not None
            else list(all_specs.keys())
        )
        if not active_names:
            active_names = ["action", "task_tier", "needs_image", "speak_only"]

        questions_payload: Dict[str, Any] = {}
        for name in active_names:
            spec = all_specs.get(name)
            if not spec:
                continue
            if spec.question_type == "choice":
                questions_payload[name] = {
                    "type": "choice",
                    "instructions": spec.instructions,
                    "criteria": spec.criteria or {},
                }
            elif spec.question_type == "noul":
                questions_payload[name] = {
                    "type": "noul",
                    "instructions": spec.instructions,
                }
            elif spec.question_type == "score":
                questions_payload[name] = {
                    "type": "score",
                    "instructions": spec.instructions,
                }

        model_name = model or self.default_model
        model_target = model_name if model_name.startswith("models/") else f"models/{model_name}"

        try:
            response = await client.aio.decisions.create(
                input=shared_input,
                model=model_target,
                questions=questions_payload,
                api_version="v1beta",
                timeout=timeout_s,
            )
        except Exception as exc:
            raise DecisionError(f"Decisions API request failed: {type(exc).__name__}") from exc

        return _parse_decision_response(
            response=response,
            utterance=utterance,
            specs=all_specs,
            active_names=active_names,
        )


class StubDecisionClient:
    """Stub client for tests that simulates Gemini Decisions API responses."""

    def __init__(
        self,
        default_result: Optional[DecisionResult] = None,
        default_answers: Optional[Dict[str, Any]] = None,
        fail: bool = False,
        timeout: bool = False,
        latency_s: float = 0.0,
    ) -> None:
        self.default_result = default_result
        self.default_answers = default_answers
        self.fail = fail
        self.timeout = timeout
        self.latency_s = latency_s
        self.calls: List[Dict[str, Any]] = []

    async def decide(
        self,
        utterance: str,
        page_text: str = "",
        session: Optional[BookSession] = None,
        model: Optional[str] = None,
        timeout_s: float = 2.0,
        enabled_checks: Optional[List[str]] = None,
    ) -> DecisionResult:
        self.calls.append({
            "utterance": utterance,
            "page_text": page_text,
            "session_id": getattr(session, "session_id", None) if session else None,
            "model": model,
            "timeout_s": timeout_s,
            "enabled_checks": list(enabled_checks) if enabled_checks else None,
        })
        if self.latency_s > 0:
            await asyncio.sleep(self.latency_s)
        if self.timeout:
            raise asyncio.TimeoutError("Simulated decision timeout")
        if self.fail:
            raise DecisionError("Simulated decision failure")
        if self.default_result is not None:
            return self.default_result
        if self.default_answers is not None:
            all_specs = get_all_question_specs()
            active_names = (
                [name for name in enabled_checks if name in all_specs]
                if enabled_checks is not None
                else list(all_specs.keys())
            )
            return _parse_decision_response(
                {"answers": self.default_answers},
                utterance=utterance,
                specs=all_specs,
                active_names=active_names,
            )

        text = utterance.lower()
        if "draw" in text:
            action = "draw"
            task_tier = "fast"
            needs_image = True
            speak_only = False
        elif "who" in text:
            action = "who_is_this"
            task_tier = "fast"
            needs_image = False
            speak_only = False
        elif "?" in text:
            action = "question"
            task_tier = "balanced"
            needs_image = False
            speak_only = False
        else:
            action = "explain"
            task_tier = "balanced"
            needs_image = False
            speak_only = False

        rec_model = resolve_model_for_tier(task_tier)
        return DecisionResult(
            action=action,
            task_tier=task_tier,
            recommended_model=rec_model,
            needs_image=needs_image,
            speak_only=speak_only,
            confidence=0.95,
            fallback_used=False,
            raw_utterance=utterance,
        )


_decision_client: Optional[DecisionClient] = None


def get_decision_client() -> DecisionClient:
    """Return the configured decision client or lazily instantiate GeminiDecisionClient."""
    global _decision_client
    if _decision_client is None:
        model = os.environ.get("MODEL_DECISION", "").strip() or DEFAULT_MODEL_DECISION
        _decision_client = GeminiDecisionClient(default_model=model)
    return _decision_client


def set_decision_client(client: Optional[DecisionClient]) -> None:
    """Configure or replace the decision client (used in tests and dependency injection)."""
    global _decision_client
    _decision_client = client


async def decide(
    utterance: str,
    page_text: str = "",
    session: Optional[BookSession] = None,
    model: Optional[str] = None,
    timeout_s: float = 2.0,
    enabled_checks: Optional[List[str]] = None,
) -> DecisionResult:
    """Evaluate decision for utterance with single-pass Decisions API and graceful fallback.

    Respects DECISION_TIMEOUT_S <= 2.0s. Cleanly falls back on timeout, errors,
    missing API key, or low confidence (< 0.50). Never raises unhandled errors
    and never logs user utterances (REQ-PRIV-02).
    """
    effective_timeout = get_effective_timeout(timeout_s)
    client = get_decision_client()

    # Fast path: if real Gemini client is active but GEMINI_API_KEY is not set, fall back immediately
    if isinstance(client, GeminiDecisionClient) and not (client.api_key or os.environ.get("GEMINI_API_KEY")):
        log.debug("GEMINI_API_KEY unset, using heuristic decision fallback")
        return fallback_decide(utterance)

    try:
        result = await asyncio.wait_for(
            client.decide(
                utterance=utterance,
                page_text=page_text,
                session=session,
                model=model,
                timeout_s=effective_timeout,
                enabled_checks=enabled_checks,
            ),
            timeout=effective_timeout,
        )

        if result.confidence < MIN_CONFIDENCE_THRESHOLD:
            log.warning("Decision confidence below threshold (%.2f < %.2f), falling back",
                        result.confidence, MIN_CONFIDENCE_THRESHOLD)
            return fallback_decide(utterance)

        return result
    except asyncio.TimeoutError:
        log.warning("Decision evaluation timed out (limit=%.2fs), falling back", effective_timeout)
        return fallback_decide(utterance)
    except Exception as exc:
        log.warning("Decision evaluation failed (%s), falling back", type(exc).__name__)
        return fallback_decide(utterance)
