"""INTENT-D1 (#142): proposed metalab.v2.intent contract for natural requests, frame-free
follow-ups, clarification, reset and cancel.

Everything here is a PROPOSED protocol check except ``LiveLegacyIntentTests``, which replays
the old-client exchanges against the actual current backend. Nothing new is negotiated by
default: the intent capability is off unless a server explicitly enables it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "ws-messages.schema.json").read_text(encoding="utf-8"))
LIFECYCLE = json.loads((ROOT / "ws-lifecycle.schema.json").read_text(encoding="utf-8"))
LEGACY_VALIDATOR = Draft202012Validator(SCHEMA)
LIFECYCLE_VALIDATOR = Draft202012Validator(LIFECYCLE)
INTENT_VALIDATOR = Draft202012Validator(
    {**SCHEMA, "oneOf": [{"$ref": "#/$defs/intentProtocolMessage"}]})

INTENT_FIXTURES = ROOT / "fixtures" / "intent"
INTENT_EXCHANGES = ROOT / "exchanges" / "intent"

V2 = "metalab.v2"
INTENT = "metalab.v2.intent"
STAGES = ["transcribing", "reading", "thinking", "drawing"]
CLIENT_TYPES = {"invoke", "cancel", "session_end"}
SERVER_TYPES = {"status", "card", "error", "clarify", "cancelled", "session_ended", "lifecycle_error"}
LIFECYCLE_TYPES = {"cancel", "cancelled", "session_end", "session_ended", "lifecycle_error"}
TERMINALS = {"card", "error", "clarify"}
# Current phone deadlines (PRD section 7); follow-ups and clarification get no larger budget.
DEADLINES = {"phone_idle_s": 30, "phone_overall_s": 90}
INVALID_REQUEST = {"type": "error", "code": "internal", "message": "Invalid request.", "retryable": False}

# Every $def and the root of ws-messages.schema.json before INTENT-D1. Their canonical JSON
# digest pins the legacy contract: an old strict client must see exactly the same schema.
LEGACY_DEFS = {
    "audioPayload", "base64String", "bookInfo", "cardMessage", "errorCode", "errorMessage",
    "framePayload", "httpsUrl", "invokeMessage", "modelInfo", "nonEmptyString", "sourceItem",
    "statusMessage", "statusStage",
}
LEGACY_DIGEST = "3e25b66a50b3c259f2e724d0bb10f9026979fa55b3949c07554d1aaa5a7fd6f6"
INTENT_DEFS = {
    "intentName", "clarifyReason", "followUpInvokeMessage", "intentCardMessage", "clarifyMessage",
    "intentProtocolMessage",
}


def select_subprotocol(offered: list[str], server: dict) -> str | None:
    """Server-side selection. ``server["intent"]`` is the INTENT runtime flag, default off."""
    if server.get("v2", False) and server.get("intent", False) and INTENT in offered:
        return INTENT
    if server.get("v2", False) and V2 in offered:
        return V2
    return None


def wire_allowed(message: dict, direction: str, selected: str | None) -> bool:
    types = CLIENT_TYPES if direction == "client" else SERVER_TYPES
    kind = message.get("type")
    if kind not in types:
        return False
    if kind in LIFECYCLE_TYPES:
        return selected in (V2, INTENT) and LIFECYCLE_VALIDATOR.is_valid(message)
    if selected == INTENT:
        return INTENT_VALIDATOR.is_valid(message)
    return LEGACY_VALIDATOR.is_valid(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def exchanges() -> dict[str, dict]:
    return {p.stem: load_json(p) for p in sorted(INTENT_EXCHANGES.glob("*.json"))}


class ExchangeChecker:
    """Test-only model of the proposed per-connection rules; not used by backend code."""

    def __init__(self, exchange: dict) -> None:
        self.selected = exchange["selected"]
        self.enabled = set(exchange["enabled_intents"])
        self.queue: list[dict] = []
        self.used_ids: set[str] = set()
        self.terminated: set[str] = set()
        self.ended: set[str] = set()
        self.ending: dict[str, str] = {}
        self.context: dict[str, bool] = {}
        self.rejections: list[tuple[str, str, str]] = []
        self.cancel_asked: set[str] = set()

    def run(self, steps: list[dict]) -> None:
        for i, step in enumerate(steps):
            try:
                if "send" in step:
                    self.send(step["send"], step.get("invalid", False))
                else:
                    self.receive(step["receive"])
            except AssertionError as exc:
                raise AssertionError(f"step {i}: {exc}") from None
        assert not self.queue, f"invocations without a terminal: {[r['id'] for r in self.queue]}"
        assert not self.rejections, f"missing admission rejections: {self.rejections}"
        assert not self.ending, f"unacknowledged session_end: {self.ending}"

    def send(self, msg: dict, invalid: bool) -> None:
        allowed = wire_allowed(msg, "client", self.selected)
        assert allowed != invalid, f"send validity {allowed} but invalid={invalid}"
        kind = msg["type"]
        if invalid:
            assert kind == "invoke", "only invokes are expected to be rejected as invalid"
            self.queue.append({"id": msg.get("request_id"), "invalid": True})
            return
        rid, sid = msg["request_id"], msg["session_id"]
        if kind == "invoke":
            if self.selected is not None:
                if rid in self.used_ids:
                    self.rejections.append((rid, sid, "duplicate_request"))
                    return
                if sid in self.ended:
                    self.rejections.append((rid, sid, "session_unavailable"))
                    return
            self.used_ids.add(rid)
            self.queue.append({
                "id": rid, "session": sid, "invalid": False, "frame_free": msg["frame"] is None,
                "text": msg.get("text"), "audio": msg.get("audio") is not None, "stages": [],
            })
        elif kind == "cancel":
            self.cancel_asked.add(rid)
        elif kind == "session_end":
            self.used_ids.add(rid)
            self.ending[rid] = sid

    def receive(self, msg: dict) -> None:
        assert wire_allowed(msg, "server", self.selected), f"server message not allowed: {msg}"
        kind = msg["type"]
        if kind == "lifecycle_error":
            key = (msg["request_id"], msg["session_id"], msg["code"])
            assert key in self.rejections, f"unexpected lifecycle_error {key}"
            self.rejections.remove(key)
            return
        if kind == "session_ended":
            sid = self.ending.pop(msg["request_id"], None)
            assert sid == msg["session_id"], "session_ended without a matching session_end"
            assert not any(r.get("session") == sid for r in self.queue), "ack before pending were cancelled"
            self.ended.add(sid)
            self.context[sid] = False
            return
        if kind == "cancelled":
            match = [r for r in self.queue if r["id"] == msg["request_id"] and not r["invalid"]]
            assert match, f"cancelled for a request that is not pending: {msg['request_id']}"
            req = match[0]
            assert req["session"] == msg["session_id"], "cancelled names the wrong session"
            assert req["id"] in self.cancel_asked or req["session"] in self.ending.values(), \
                "cancelled without a cancel or session_end"
            self.queue.remove(req)
            self.terminated.add(req["id"])
            return

        assert self.queue, f"{kind} with no pending invocation"
        head = self.queue[0]
        assert msg["request_id"] == head["id"], \
            f"{kind} for {msg['request_id']!r} but {head['id']!r} is running (one at a time, in order)"
        if head["invalid"]:
            assert {k: msg.get(k) for k in INVALID_REQUEST} == INVALID_REQUEST, "expected legacy invalid-request error"
            self.queue.pop(0)
            return
        if kind == "status":
            stage = msg["stage"]
            if head["stages"]:
                assert STAGES.index(stage) > STAGES.index(head["stages"][-1]), "stage out of PRD order"
            elif head["audio"]:
                assert stage == "transcribing", "audio requests start with transcribing"
            assert not (head["frame_free"] and stage == "reading"), "a frame-free follow-up has no reading stage"
            assert not (head["text"] is not None and stage == "transcribing"), "typed requests skip transcribing"
            head["stages"].append(stage)
            return

        self.queue.pop(0)
        self.terminated.add(head["id"])
        sid = head["session"]
        has_context = self.context.get(sid, False)
        if kind == "error":
            return
        if head["audio"]:
            assert "transcribing" in head["stages"], "spoken request answered without transcribing"
        if not head["frame_free"]:
            assert "reading" in head["stages"], "framed request answered without reading the frame"
        if self.selected == INTENT:
            if head["text"] is not None:
                assert msg["utterance"] == head["text"], "utterance is not the full typed request"
        if kind == "card":
            if self.selected == INTENT:
                assert msg["intent"] in self.enabled, f"card for disabled intent {msg['intent']}"
            assert not head["frame_free"] or has_context, "frame-free card without session context"
            self.context[sid] = True
            return
        # clarify
        assert msg["session_id"] == sid, "clarify names the wrong session"
        assert set(msg["options"]) <= self.enabled, "clarify offers a disabled intent"
        if msg["reason"] == "ambiguous_intent":
            assert len(self.enabled) >= 2, "ambiguous_intent needs two enabled intents"
        no_context = head["frame_free"] and not has_context
        assert (msg["reason"] == "needs_frame") == no_context, "needs_frame iff frame-free without context"
        if msg["reason"] in ("ambiguous_intent", "ambiguous_book") and not head["frame_free"]:
            self.context[sid] = True  # page text retained session-only to resolve the reply


class LegacyContractUnchangedTests(unittest.TestCase):
    def test_root_and_legacy_defs_are_byte_identical(self) -> None:
        self.assertEqual(SCHEMA["oneOf"], [
            {"$ref": "#/$defs/invokeMessage"}, {"$ref": "#/$defs/statusMessage"},
            {"$ref": "#/$defs/cardMessage"}, {"$ref": "#/$defs/errorMessage"},
        ])
        self.assertEqual(set(SCHEMA["$defs"]), LEGACY_DEFS | INTENT_DEFS)
        legacy_view = {**SCHEMA, "$defs": {k: SCHEMA["$defs"][k] for k in LEGACY_DEFS}}
        digest = hashlib.sha256(
            json.dumps(legacy_view, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, LEGACY_DIGEST, "legacy contract changed; old strict clients would break")

    def test_new_defs_are_unreachable_from_legacy_validation(self) -> None:
        legacy_text = json.dumps({**SCHEMA, "$defs": {k: SCHEMA["$defs"][k] for k in LEGACY_DEFS}})
        for name in INTENT_DEFS:
            with self.subTest(defn=name):
                self.assertNotIn(f"#/$defs/{name}\"", legacy_text)

    def test_old_fixtures_still_validate_unchanged(self) -> None:
        for path in sorted((ROOT / "fixtures" / "valid").glob("*.json")):
            with self.subTest(fixture=path.name):
                self.assertTrue(LEGACY_VALIDATOR.is_valid(load_json(path)))
        for path in sorted((ROOT / "fixtures" / "invalid").glob("*.json")):
            with self.subTest(fixture=path.name):
                message = load_json(path)
                self.assertFalse(LEGACY_VALIDATOR.is_valid(message))
                self.assertFalse(INTENT_VALIDATOR.is_valid(message), "legacy-invalid shape accepted on intent")

    def test_legacy_messages_on_intent_protocol(self) -> None:
        for path in sorted((ROOT / "fixtures" / "valid").glob("*.json")):
            message = load_json(path)
            with self.subTest(fixture=path.name):
                # Intent connections always send intent cards; every other legacy message is unchanged.
                self.assertEqual(INTENT_VALIDATOR.is_valid(message), message["type"] != "card")

    def test_no_new_stage_or_error_code(self) -> None:
        defs = SCHEMA["$defs"]
        self.assertEqual(defs["statusStage"]["enum"], STAGES)
        self.assertEqual(defs["errorCode"]["enum"], ["no_text_found", "stt_failed", "model_timeout", "internal"])


class IntentSchemaTests(unittest.TestCase):
    def test_schema_is_valid(self) -> None:
        Draft202012Validator.check_schema(SCHEMA)

    def test_valid_intent_fixtures(self) -> None:
        paths = sorted((INTENT_FIXTURES / "valid").glob("*.json"))
        self.assertGreaterEqual(len(paths), 8)
        reasons, kinds = set(), set()
        for path in paths:
            message = load_json(path)
            with self.subTest(fixture=path.name):
                self.assertEqual(list(INTENT_VALIDATOR.iter_errors(message)), [])
                self.assertFalse(LEGACY_VALIDATOR.is_valid(message), "new shape leaked into legacy")
                self.assertFalse(LIFECYCLE_VALIDATOR.is_valid(message))
                kinds.add(message["type"])
                reasons.add(message.get("reason"))
        self.assertEqual(kinds, {"invoke", "card", "clarify"})
        self.assertEqual(reasons - {None}, set(SCHEMA["$defs"]["clarifyReason"]["enum"]))

    def test_invalid_intent_fixtures(self) -> None:
        paths = sorted((INTENT_FIXTURES / "invalid").glob("*.json"))
        self.assertGreaterEqual(len(paths), 10)
        for path in paths:
            message = load_json(path)
            with self.subTest(fixture=path.name):
                self.assertFalse(INTENT_VALIDATOR.is_valid(message))
                # A legacy-shaped card is valid for old connections, never on metalab.v2.intent.
                self.assertEqual(LEGACY_VALIDATOR.is_valid(message), path.stem == "intent-card-legacy-shape")

    def test_intent_card_keeps_card_field_meanings(self) -> None:
        defs = SCHEMA["$defs"]
        card, intent_card = defs["cardMessage"], defs["intentCardMessage"]
        self.assertEqual(set(intent_card["required"]), set(card["required"]) | {"intent", "utterance"})
        for key, subschema in card["properties"].items():
            with self.subTest(field=key):
                self.assertEqual(intent_card["properties"][key], subschema)

    def test_follow_up_invoke_differs_only_by_null_frame(self) -> None:
        defs = SCHEMA["$defs"]
        invoke, follow_up = copy.deepcopy(defs["invokeMessage"]), copy.deepcopy(defs["followUpInvokeMessage"])
        follow_up.pop("description")
        self.assertEqual(follow_up["properties"].pop("frame"), {"type": "null"})
        invoke["properties"].pop("frame")
        self.assertEqual(follow_up, invoke)

    def test_lifecycle_controls_need_v2_family(self) -> None:
        for path in sorted((ROOT / "fixtures" / "lifecycle" / "valid").glob("*.json")):
            message = load_json(path)
            direction = "client" if message["type"] in CLIENT_TYPES else "server"
            with self.subTest(fixture=path.name):
                self.assertTrue(wire_allowed(message, direction, INTENT))
                self.assertTrue(wire_allowed(message, direction, V2))
                self.assertFalse(wire_allowed(message, direction, None))
                self.assertFalse(INTENT_VALIDATOR.is_valid(message))

    def test_new_messages_never_reach_old_connections(self) -> None:
        for path in sorted((INTENT_FIXTURES / "valid").glob("*.json")):
            message = load_json(path)
            direction = "client" if message["type"] == "invoke" else "server"
            with self.subTest(fixture=path.name):
                self.assertTrue(wire_allowed(message, direction, INTENT))
                self.assertFalse(wire_allowed(message, direction, V2))
                self.assertFalse(wire_allowed(message, direction, None))


class NegotiationTests(unittest.TestCase):
    def test_selection_table(self) -> None:
        both = [INTENT, V2]
        cases = [
            ([], {}, None),
            ([], {"v2": True, "intent": True}, None),
            (both, {}, None),
            (both, {"v2": True}, V2),  # intent flag defaults off
            (both, {"v2": True, "intent": False}, V2),
            (both, {"v2": True, "intent": True}, INTENT),
            ([V2], {"v2": True, "intent": True}, V2),
            ([INTENT], {"v2": True}, None),
            ([INTENT], {"v2": False, "intent": True}, None),
        ]
        for offered, server, want in cases:
            with self.subTest(offered=offered, server=server):
                self.assertEqual(select_subprotocol(offered, server), want)


class IntentExchangeTests(unittest.TestCase):
    REQUIRED = {
        "natural-request", "natural-request-audio", "follow-up-without-frame",
        "follow-up-audio-without-frame", "follow-up-without-context", "reset", "reset-with-pending",
        "cancel", "cancel-keeps-earlier-context", "ambiguity-intent", "ambiguity-book",
        "unsupported-intent", "overlapping-request-ids", "v2-without-intent",
        "legacy-natural-request", "legacy-frame-free-rejected", "legacy-overlapping-request-ids",
        "legacy-offer-ignored",
    }

    def test_required_exchanges_exist(self) -> None:
        self.assertLessEqual(self.REQUIRED, set(exchanges()))

    def test_exchanges_follow_the_contract(self) -> None:
        for name, exchange in exchanges().items():
            with self.subTest(exchange=name):
                self.assertEqual(exchange["deadlines"], DEADLINES)
                self.assertEqual(select_subprotocol(exchange["offered"], exchange["server"]), exchange["selected"])
                self.assertIn("reading", exchange["enabled_intents"])
                if exchange["live"]:
                    self.assertIsNone(exchange["selected"], "only legacy exchanges replay against the backend")
                ExchangeChecker(exchange).run(exchange["steps"])

    def test_default_server_config_never_selects_intent(self) -> None:
        for name, exchange in exchanges().items():
            with self.subTest(exchange=name):
                self.assertNotEqual(select_subprotocol(exchange["offered"], {"v2": True}), INTENT)

    def mutated(self, name: str, mutate) -> dict:
        exchange = copy.deepcopy(exchanges()[name])
        mutate(exchange["steps"])
        return exchange

    def assert_rejected(self, exchange: dict, pattern: str) -> None:
        with self.assertRaisesRegex(AssertionError, pattern):
            ExchangeChecker(exchange).run(exchange["steps"])

    def test_checker_rejects_violations(self) -> None:
        def receives(steps, rid, kind):
            return [s for s in steps if s.get("receive", {}).get("request_id") == rid
                    and s["receive"]["type"] == kind]

        def reading_on_follow_up(steps):
            receives(steps, "r2", "status")[0]["receive"]["stage"] = "reading"

        def card_after_cancel(steps):
            index = steps.index(receives(steps, "r1", "cancelled")[0])
            steps.insert(index + 1, {"receive": copy.deepcopy(exchanges()["natural-request"]["steps"][-1]["receive"])})

        def truncated_utterance(steps):
            receives(steps, "r1", "card")[0]["receive"]["utterance"] = "explain"

        def reuse_ended_session(steps):
            steps.pop(steps.index(receives(steps, "r2", "lifecycle_error")[0]))

        def needs_frame_with_context(steps):
            card = receives(steps, "r2", "card")[0]
            index = steps.index(card)
            msg = card["receive"]
            steps[index] = {"receive": {
                "type": "clarify", "request_id": "r2", "session_id": "s1", "reason": "needs_frame",
                "utterance": msg["utterance"], "speech_text": "Look at the page.", "audio_url": None, "options": []}}

        def legacy_card_on_intent(steps):
            msg = receives(steps, "r1", "card")[0]["receive"]
            del msg["intent"], msg["utterance"]

        def second_terminal(steps):
            steps.append(copy.deepcopy(receives(steps, "r1", "card")[0]))

        def ack_before_cancelled(steps):
            a, b = receives(steps, "r1", "cancelled")[0], [s for s in steps if s.get("receive", {}).get("type") == "session_ended"][0]
            i, j = steps.index(a), steps.index(b)
            steps[i], steps[j] = steps[j], steps[i]

        def accept_duplicate(steps):
            steps.pop(steps.index(receives(steps, "r1", "lifecycle_error")[0]))

        def disabled_option(steps):
            receives(steps, "r1", "clarify")[0]["receive"]["options"] = ["reading", "document"]

        cases = [
            ("follow-up-without-frame", reading_on_follow_up, "no reading stage"),
            ("cancel", card_after_cancel, "card for 'r1'|with no pending"),
            ("natural-request", truncated_utterance, "full typed request"),
            ("reset", reuse_ended_session, "unexpected|missing admission"),
            ("follow-up-without-frame", needs_frame_with_context, "needs_frame iff"),
            ("natural-request", legacy_card_on_intent, "not allowed"),
            ("natural-request", second_terminal, "no pending invocation"),
            ("reset-with-pending", ack_before_cancelled, "ack before pending"),
            ("overlapping-request-ids", accept_duplicate, "missing admission|is running"),
            ("ambiguity-intent", disabled_option, "disabled intent"),
        ]
        for name, mutate, pattern in cases:
            with self.subTest(exchange=name, mutation=mutate.__name__):
                self.assert_rejected(self.mutated(name, mutate), pattern)


class LiveLegacyIntentTests(unittest.TestCase):
    """ACTUAL current backend: old clients and new-client offers see nothing new."""

    def setUp(self) -> None:
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        for key in ("GEMINI_API_KEY", "NVIDIA_API_KEY"):
            os.environ.pop(key, None)
        guard = mock.patch("urllib.request.urlopen", side_effect=AssertionError("offline contract test"))
        guard.start()
        self.addCleanup(guard.stop)

    def replay(self, exchange: dict) -> tuple[str | None, list[dict]]:
        from fastapi.testclient import TestClient
        from test_conformance import EXTRA_REPLY_TIMEOUT_S, TIMEOUT_S, app, deadline

        sends = [s["send"] for s in exchange["steps"] if "send" in s]
        count = sum("receive" in s for s in exchange["steps"])
        with deadline(TIMEOUT_S), TestClient(app).websocket_connect(
                "/ws", subprotocols=exchange["offered"]) as ws:
            for message in sends:
                ws.send_text(json.dumps(message))
            replies = [ws.receive_json() for _ in range(count)]
            try:
                with deadline(EXTRA_REPLY_TIMEOUT_S):
                    extra = ws.receive_json()
            except TimeoutError:
                pass
            else:
                raise AssertionError(f"unexpected reply after expected sequence: {extra}")
            return ws.accepted_subprotocol, replies

    def test_live_legacy_exchanges(self) -> None:
        live = {n: e for n, e in exchanges().items() if e["live"]}
        self.assertGreaterEqual(len(live), 4)
        for name, exchange in live.items():
            with self.subTest(exchange=name):
                selected, replies = self.replay(exchange)
                self.assertIsNone(selected)
                self.assertEqual(replies, [s["receive"] for s in exchange["steps"] if "receive" in s])
                for reply in replies:
                    self.assertTrue(LEGACY_VALIDATOR.is_valid(reply))
                    self.assertNotIn(reply["type"], {"clarify", *LIFECYCLE_TYPES})


if __name__ == "__main__":
    unittest.main()
