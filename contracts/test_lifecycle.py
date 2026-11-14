"""PROPOSED protocol tests only. No backend imports, real timers, deletion or auth.

Hand-authored trace outputs/snapshots are checked against a small test-only model.
They are future implementation acceptance examples, not runtime conformance.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
LEGACY = json.loads((ROOT / "ws-messages.schema.json").read_text())
LIFECYCLE = json.loads((ROOT / "ws-lifecycle.schema.json").read_text())
LEGACY_VALIDATOR = Draft202012Validator(LEGACY)
LIFECYCLE_VALIDATOR = Draft202012Validator(LIFECYCLE)
CLIENT_TYPES = {"invoke", "cancel", "session_end"}
SERVER_TYPES = {"status", "card", "error", "cancelled", "session_ended", "lifecycle_error"}
TTL_MS = 900_000
CLEANUP_MS = 5_000


def wire_allowed(message: dict, direction: str, negotiated: bool) -> bool:
    types = CLIENT_TYPES if direction == "client" else SERVER_TYPES
    if message.get("type") not in types:
        return False
    if not (LEGACY_VALIDATOR.is_valid(message) or (
        negotiated and LIFECYCLE_VALIDATOR.is_valid(message)
    )):
        return False
    if negotiated and message.get("type") == "invoke":
        for field in ("request_id", "session_id"):
            val = message.get(field, "")
            if not (isinstance(val, str) and val.strip()):
                return False
    return True


def handshake(case: dict) -> tuple[bool, bool, int | None]:
    """Abstract rollout table, not a credential parser or production verifier."""
    if case.get("credential_location", "header") != "header":
        return False, False, None
    if case.get("enabled", False):
        if not all(case.get(k, False) for k in ("ios_verified", "rollout_agreed")):
            return False, False, None
        if not case.get("tls") or not all(
            case.get(k, True) for k in ("verifier_ready", "configured")
        ):
            return False, False, None
        if case["credential"] != "valid":
            return False, False, 401
    selected = case.get("selected")
    if selected is not None and (
        selected != "metalab.v2" or selected not in case.get("offered", [])
    ):
        return False, False, None
    upgraded = case.get("handshake_ok", True)
    return upgraded, upgraded and selected == "metalab.v2", None


class ProposedLifecycleModel:
    """Synthetic IDs and media markers only; never used by backend code."""

    def __init__(self) -> None:
        self.now = 0
        self.connected = True
        self.context = "owner-a"
        self.sessions: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.end_ids: dict[str, str] = {}
        self.conn_ids: set[str] = set()

    def session(self, sid: str) -> dict:
        return self.sessions.setdefault(sid, {
            "owner": self.context, "last": self.now, "deleted": False, "clean": False,
            "cleanup_by": None, "history": [], "cache": [], "media": [],
            "staged": [], "ends": [],
        })

    def pending(self, sid: str) -> list[str]:
        return sorted(r for r, v in self.requests.items()
                      if v["session"] == sid and v["result"] == "pending")

    def stop(self, sid: str, out: list[str]) -> None:
        session = self.sessions[sid]
        for rid in self.pending(sid):
            self.requests[rid]["result"] = "cancelled" if self.connected else "abandoned"
            if self.connected:
                out.append(f"cancelled:{rid}")
        session["staged"].clear()

    def delete(self, sid: str, out: list[str], expiry: bool = False) -> None:
        session = self.sessions[sid]
        session["deleted"] = True
        if expiry:
            session["cleanup_by"] = session["last"] + TTL_MS + CLEANUP_MS
        self.stop(sid, out)

    def step(self, event: dict) -> list[str]:
        now = event.get("at_ms", self.now)
        assert now >= self.now, "server monotonic clock moved backwards"
        self.now = now
        out: list[str] = []
        for sid, session in self.sessions.items():
            if not session["deleted"] and now >= session["last"] + TTL_MS:
                self.delete(sid, out, expiry=True)
            if session["cleanup_by"] is not None and not session["clean"]:
                assert now <= session["cleanup_by"], "cleanup exceeded five seconds"

        op = event["op"]
        sid, rid = event.get("session"), event.get("request")
        session = self.sessions.get(sid)
        if op == "invoke":
            assert self.connected, "invoke on closed socket"
            session = self.session(sid)
            if session["deleted"] or session["owner"] != self.context:
                out.append(f"session_unavailable:{rid}")
            elif rid in self.conn_ids:
                out.append(f"duplicate_request:{rid}")
            else:
                session["last"] = now
                session["staged"].append(rid)
                self.requests[rid] = {"session": sid, "result": "pending"}
                self.conn_ids.add(rid)
        elif op == "cancel":
            assert self.connected, "cancel on closed socket"
            request = self.requests.get(rid)
            if session is None or session["deleted"] or session["owner"] != self.context:
                out.append(f"session_unavailable:{rid}")
            elif request is None:
                out.append(f"unknown_request:{rid}")
            elif request["session"] != sid:
                out.append(f"session_mismatch:{rid}")
            elif request["result"] == "pending":
                request["result"] = "cancelled"
                session["staged"].remove(rid)
                out.append(f"cancelled:{rid}")
        elif op == "complete":
            request = self.requests[rid]
            session = self.sessions[request["session"]]
            if request["result"] == "pending":
                assert self.connected and not session["deleted"]
                result = event.get("result", "card")
                assert result in {"card", "error"}
                request["result"] = result
                session["staged"].remove(rid)
                if result == "card":
                    for key in ("history", "cache", "media"):
                        session[key].append(rid)
                out.append(f"{result}:{rid}")
        elif op == "status":
            assert self.connected and self.requests[rid]["result"] == "pending", "status after terminal"
            out.append(f"status:{rid}")
        elif op == "end":
            assert self.connected, "end on closed socket"
            if session is None:
                session = self.session(sid)
            if session["owner"] != self.context:
                out.append(f"session_unavailable:{rid}")
            elif rid in self.conn_ids and not (rid in self.end_ids and self.end_ids[rid] == sid):
                out.append(f"duplicate_request:{rid}")
            else:
                self.end_ids[rid] = sid
                self.conn_ids.add(rid)
                if not session["deleted"]:
                    self.delete(sid, out)
                if session["clean"]:
                    out.append(f"session_ended:{rid}")
                elif rid not in session["ends"]:
                    session["ends"].append(rid)
        elif op == "cleanup":
            assert session is not None and session["deleted"], "cleanup of live session"
            for key in ("history", "cache", "media", "staged"):
                session[key].clear()
            session["clean"] = True
            if self.connected and session["owner"] == self.context:
                out.extend(f"session_ended:{end}" for end in session["ends"])
            session["ends"].clear()
        elif op == "disconnect":
            assert self.connected
            self.connected = False
            for owned_sid, owned in self.sessions.items():
                if owned["owner"] == self.context:
                    self.stop(owned_sid, out)
        elif op == "connect":
            assert not self.connected
            self.connected = True
            self.context = event.get("context", self.context)
            self.conn_ids = set()
        elif op == "resume":
            assert self.connected
            allowed = session is not None and not session["deleted"] and session["owner"] == self.context
            assert allowed == event["allowed"], "incorrect resume availability"
        elif op == "read":
            assert event["resource"] in {"text", "cache", "image", "audio"}
            allowed = session is not None and not session["deleted"] and session["owner"] == self.context
            key = {"text": "history", "cache": "cache", "image": "media", "audio": "media"}[event["resource"]]
            readable = allowed and rid in session[key]
            assert bool(readable) == event["allowed"], "incorrect state/media accessibility"
        elif op not in {"tick", "wall_jump", "ping", "rejected", "check"}:
            raise AssertionError(f"unknown trace operation: {op}")

        assert out == event.get("out", []), f"terminal/control order: {out} != {event.get('out', [])}"
        for check_sid, expected in event.get("state", {}).items():
            actual = self.sessions[check_sid]
            for key, value in expected.items():
                got = self.pending(check_sid) if key == "pending" else actual[key]
                assert got == value, f"{check_sid}.{key}: {got!r} != {value!r}"
        return out


class ProposedLifecycleSchemaTests(unittest.TestCase):
    def test_separate_schema_and_fixtures(self) -> None:
        Draft202012Validator.check_schema(LIFECYCLE)
        seen = set()
        for validity in ("valid", "invalid"):
            paths = sorted((ROOT / "fixtures" / "lifecycle" / validity).glob("*.json"))
            self.assertTrue(paths)
            for path in paths:
                with self.subTest(fixture=path.name, validity=validity):
                    message = json.loads(path.read_text())
                    self.assertEqual(LIFECYCLE_VALIDATOR.is_valid(message), validity == "valid")
                    self.assertFalse(LEGACY_VALIDATOR.is_valid(message))
                    if validity == "valid":
                        seen.add(message["type"])
        self.assertEqual(seen, {"cancel", "cancelled", "session_end", "session_ended", "lifecycle_error"})

    def test_lifecycle_directions_and_negotiation(self) -> None:
        for path in (ROOT / "fixtures" / "lifecycle" / "valid").glob("*.json"):
            message = json.loads(path.read_text())
            direction = "client" if message["type"] in CLIENT_TYPES else "server"
            wrong = "server" if direction == "client" else "client"
            with self.subTest(fixture=path.name):
                self.assertTrue(wire_allowed(message, direction, negotiated=True))
                self.assertFalse(wire_allowed(message, wrong, negotiated=True))
                self.assertFalse(wire_allowed(message, direction, negotiated=False))

    def test_all_legacy_fixtures_still_work_on_both_protocols(self) -> None:
        for path in (ROOT / "fixtures" / "valid").glob("*.json"):
            message = json.loads(path.read_text())
            direction = "client" if message["type"] == "invoke" else "server"
            for negotiated in (False, True):
                with self.subTest(fixture=path.name, v2=negotiated):
                    self.assertTrue(wire_allowed(message, direction, negotiated))
                    self.assertFalse(LIFECYCLE_VALIDATOR.is_valid(message))

    def test_v2_invoke_rejects_whitespace_ids(self) -> None:
        base = json.loads((ROOT / "fixtures" / "valid" / "invoke.json").read_text())
        for field in ("request_id", "session_id"):
            blank = {**base, field: "   "}
            with self.subTest(field=field):
                self.assertFalse(wire_allowed(blank, "client", negotiated=True))
                self.assertTrue(wire_allowed(blank, "client", negotiated=False))

    def test_lifecycle_fields_do_not_leak_into_legacy_messages(self) -> None:
        for name, extra in (
            ("invoke-text-mode", {"authorization": "REDACTED"}),
            ("card", {"session_id": "session-a"}),
            ("error-internal", {"code": "cancelled"}),
        ):
            message = json.loads((ROOT / "fixtures" / "valid" / f"{name}.json").read_text())
            with self.subTest(fixture=name):
                self.assertFalse(LEGACY_VALIDATOR.is_valid({**message, **extra}))

    def test_each_error_code_has_an_example(self) -> None:
        for code in ("unknown_request", "session_unavailable", "session_mismatch", "duplicate_request"):
            self.assertTrue(LIFECYCLE_VALIDATOR.is_valid({
                "type": "lifecycle_error", "session_id": "session-a", "request_id": "req-a", "code": code,
            }))


class ProposedLifecycleTraceTests(unittest.TestCase):
    def test_hand_authored_protocol_traces(self) -> None:
        cases = json.loads((ROOT / "lifecycle-traces.json").read_text())["cases"]
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            with self.subTest(trace=case["name"]):
                model = ProposedLifecycleModel()
                if "reject" in case:
                    with self.assertRaisesRegex(AssertionError, case["reject"]):
                        for event in case["events"]:
                            model.step(event)
                else:
                    for event in case["events"]:
                        model.step(event)
                    for session in model.sessions.values():
                        if session["deleted"]:
                            self.assertTrue(session["clean"], "trace must demonstrate final cleanup")
                    self.assertFalse(any(v["result"] == "pending" for v in model.requests.values()),
                                     "trace must resolve/abandon all invocations")

    def test_expiry_values_match_requirement(self) -> None:
        self.assertEqual(TTL_MS, 15 * 60 * 1000)
        self.assertEqual(CLEANUP_MS, 5 * 1000)


class ProposedAuthRolloutTests(unittest.TestCase):
    def test_handshake_decision_table(self) -> None:
        cases = json.loads((ROOT / "auth-scenarios.json").read_text())["cases"]
        for case in cases:
            with self.subTest(scenario=case["name"]):
                self.assertEqual(handshake(case), (
                    case["upgrade"], case.get("controls", False), case.get("http"),
                ))

    def test_credentials_never_extend_message_schemas(self) -> None:
        paths = list((ROOT / "fixtures" / "valid").glob("*.json"))
        paths += list((ROOT / "fixtures" / "lifecycle" / "valid").glob("*.json"))
        for path in paths:
            message = json.loads(path.read_text())
            for key in ("Authorization", "authorization", "token", "credential"):
                with self.subTest(fixture=path.name, field=key):
                    with_credential = {**message, key: "REDACTED"}
                    self.assertFalse(LEGACY_VALIDATOR.is_valid(with_credential))
                    self.assertFalse(LIFECYCLE_VALIDATOR.is_valid(with_credential))

    def test_credentials_are_header_only_even_when_auth_is_off(self) -> None:
        forbidden = json.loads((ROOT / "auth-scenarios.json").read_text())["forbidden_credential_locations"]
        self.assertEqual(set(forbidden), {"json", "query", "path", "subprotocol", "log"})
        for location in forbidden:
            for enabled in (False, True):
                with self.subTest(location=location, enabled=enabled):
                    case = {
                        "enabled": enabled, "tls": True, "ios_verified": True,
                        "rollout_agreed": True, "credential": "valid",
                        "credential_location": location,
                    }
                    self.assertEqual(handshake(case), (False, False, None))


if __name__ == "__main__":
    unittest.main()
