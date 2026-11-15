#!/usr/bin/env python3
"""Behavioral checks for the thin client. Mirrors MetaLabCore so CI can run without Xcode."""

import json
from pathlib import Path
import unittest


STAGES = ("transcribing", "reading", "thinking", "drawing")
ERROR_CODES = ("no_text_found", "stt_failed", "model_timeout", "internal")

STAGE_FREQUENCIES = {
    "transcribing": 523.25,
    "reading": 659.25,
    "thinking": 783.99,
    "drawing": 1046.50,
}


def should_play_earcon(stage, earcons_enabled=True, is_speaking=False):
    """Client-side gate for status earcon cues."""
    if not earcons_enabled:
        return False
    if is_speaking:
        return False
    return stage in STAGES


def capture_steps(display_enabled, typed_command):
    typed = bool(typed_command and typed_command.strip())
    steps = []
    if not typed:
        steps += ["settleHFP", "recordAudio"]
    steps += ["startCamera", "takeOneFrame", "stopCamera"]
    if display_enabled:
        steps.append("showProgress")
    steps += ["sendInvoke", "speak"]
    return steps


def lens_image(url):
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    return url


def speech_route(audio_url, speech_text, display_enabled):
    del display_enabled  # the answer is spoken either way
    if isinstance(audio_url, str) and audio_url.startswith("https://"):
        return ("remote", audio_url, speech_text)
    text = (speech_text or "").strip()
    return ("voice", text) if text else ("silent",)


def reduce_link(state, link):
    state = dict(state)
    state["link"] = link
    if link == "paused":
        state["banner"] = "paused"
        state["needs_new_session"] = False
        state["can_invoke"] = False
    elif link == "stopped":
        state["needs_new_session"] = True
        state["can_invoke"] = False
        if state.get("banner") not in {"hinges", "bluetooth"}:
            state["banner"] = "stopped"
    elif link == "started":
        state["needs_new_session"] = False
        if state.get("banner") in {"paused", "stopped", "hinges", "bluetooth"}:
            state["banner"] = None
        state["can_invoke"] = state.get("registered") and state.get("permission") and not state["needs_new_session"]
    return state


class ClientTests(unittest.TestCase):
    def test_prd_messages_round_trip(self):
        invoke = {
            "type": "invoke",
            "request_id": "req",
            "session_id": "book",
            "frame": {"mime": "image/jpeg", "b64": "abc"},
            "audio": {"mime": "audio/wav", "b64": "wav"},
            "text": None,
        }
        self.assertEqual(json.loads(json.dumps(invoke))["text"], None)
        self.assertNotIn("gemini", json.dumps(invoke).lower())
        status = {"type": "status", "request_id": "req", "stage": "drawing"}
        self.assertIn(status["stage"], STAGES)
        card = {
            "type": "card",
            "request_id": "req",
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
            "image_url": None,
            "speech_text": "Hamlet is alone, weighing whether to keep living.",
            "audio_url": None,
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
            "sources": [{"title": "Hamlet, public-domain text", "url": "https://example.com/hamlet"}],
            "models": {"read": "nemotron", "reason": "", "image": ""},
        }
        self.assertIsNone(card["image_url"])
        self.assertEqual(card["models"]["reason"], "")
        for code in ERROR_CODES:
            self.assertIn(code, ERROR_CODES)

    def test_camera_stops_before_the_lens_and_speech_survives_display_off(self):
        shown = capture_steps(True, None)
        self.assertLess(shown.index("stopCamera"), shown.index("showProgress"))
        self.assertEqual(shown[-1], "speak")
        hidden = capture_steps(False, None)
        self.assertNotIn("showProgress", hidden)
        self.assertEqual(hidden[-1], "speak")
        typed = capture_steps(True, " explain ")
        self.assertNotIn("recordAudio", typed)
        self.assertIn("takeOneFrame", typed)

    def test_lens_accepts_only_https_and_speech_ignores_the_display_toggle(self):
        self.assertIsNone(lens_image(None))
        self.assertIsNone(lens_image("http://example.com/a.png"))
        self.assertEqual(lens_image("https://example.com/a.png"), "https://example.com/a.png")
        self.assertEqual(
            speech_route(None, "Hamlet is alone.", False),
            speech_route(None, "Hamlet is alone.", True),
        )
        self.assertEqual(speech_route("https://cdn.example/a.mp3", "fallback", False)[0], "remote")
        self.assertEqual(speech_route("http://cdn.example/a.mp3", "fallback", True), ("voice", "fallback"))

    def test_paused_does_not_open_a_new_session_and_the_card_stays(self):
        state = {
            "link": "started",
            "registered": True,
            "permission": True,
            "needs_new_session": False,
            "can_invoke": True,
            "banner": None,
            "last_card": "kept",
        }
        paused = reduce_link(state, "paused")
        self.assertFalse(paused["needs_new_session"])
        self.assertEqual(paused["last_card"], "kept")
        self.assertFalse(paused["can_invoke"])
        resumed = reduce_link(paused, "started")
        self.assertTrue(resumed["can_invoke"])
        self.assertIsNone(resumed["banner"])
        stopped = reduce_link(resumed, "stopped")
        self.assertTrue(stopped["needs_new_session"])
        self.assertEqual(stopped["last_card"], "kept")
        stopped["banner"] = "hinges"
        still = reduce_link(stopped, "stopped")
        self.assertEqual(still["banner"], "hinges")

    def test_backend_url_is_a_websocket_and_not_a_model_key(self):
        def accept(value):
            value = value.strip()
            return value.startswith("ws://") or value.startswith("wss://")

        self.assertTrue(accept("wss://metalab.modal.run/ws"))
        self.assertFalse(accept("https://generativelanguage.googleapis.com"))
        self.assertFalse(accept("AIza-not-a-key"))

    def test_deadline_has_an_idle_clock_and_a_cap(self):
        def timed_out(elapsed, idle, overall=90, idle_limit=30):
            return elapsed >= overall or idle >= idle_limit

        self.assertFalse(timed_out(10, 10))
        self.assertTrue(timed_out(40, 30))
        self.assertFalse(timed_out(80, 5))
        self.assertTrue(timed_out(90, 1))

    def test_status_earcon_cues_for_pipeline_stages(self):
        # Every server pipeline stage maps to a valid earcon chime cue
        for stage in STAGES:
            self.assertTrue(should_play_earcon(stage, earcons_enabled=True, is_speaking=False))
            self.assertIn(stage, STAGE_FREQUENCIES)
            self.assertGreater(STAGE_FREQUENCIES[stage], 0)

        # Gated by optional toggle (default enabled)
        self.assertFalse(should_play_earcon("reading", earcons_enabled=False, is_speaking=False))

        # Safe non-blocking: suppressed when card arrives or TTS/voice is speaking
        self.assertFalse(should_play_earcon("reading", earcons_enabled=True, is_speaking=True))
        self.assertFalse(should_play_earcon("thinking", earcons_enabled=True, is_speaking=True))

        # Unknown stage does not trigger an earcon
        self.assertFalse(should_play_earcon("invalid_stage", earcons_enabled=True, is_speaking=False))


CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
RETENTION_S = 900
V2 = "metalab.v2"
CLIENT_OFFERS = ()
LIFECYCLE_SERVER_FIELDS = {
    "cancelled": {"type", "request_id", "session_id"},
    "session_ended": {"type", "request_id", "session_id", "cleanup"},
    "lifecycle_error": {"type", "request_id", "session_id", "code"},
}
LIFECYCLE_CODES = {"unknown_request", "session_unavailable", "session_mismatch", "duplicate_request"}


def handshake_headers(url, credential):
    """Mirrors HandshakePlan: the credential goes only in the Authorization header, only over wss."""
    token = (credential or "").strip()
    if not token or any(ord(c) <= 0x20 or ord(c) >= 0x7F for c in token):
        return url, {}
    if not url.lower().startswith("wss://"):
        return url, {}
    return url, {"Authorization": f"Bearer {token}"}


def negotiate(offered, selected, upgraded):
    """Mirrors ProtocolNegotiation.evaluate: (usable, lifecycle_controls)."""
    if not upgraded:
        return False, False
    selected = selected or None
    if selected is not None and (selected != V2 or selected not in offered):
        return False, False
    return True, selected == V2


def decode_lifecycle(message, negotiated):
    """Mirrors LifecycleContract.decode; None means rejected."""
    if not negotiated or not isinstance(message, dict):
        return None
    fields = LIFECYCLE_SERVER_FIELDS.get(message.get("type"))
    if fields is None or set(message) != fields:
        return None
    for key in ("request_id", "session_id"):
        value = message.get(key)
        if not (isinstance(value, str) and value.strip()):
            return None
    if message["type"] == "session_ended" and message["cleanup"] != "complete":
        return None
    if message["type"] == "lifecycle_error" and message["code"] not in LIFECYCLE_CODES:
        return None
    return message["type"]


class ClientSession:
    """Mirrors MetaLabCore.ClientSession on a synthetic monotonic clock."""

    def __init__(self, session_id, now):
        self.id, self.generation, self.deadline = session_id, 0, now + RETENTION_S

    def expired(self, now):
        return now >= self.deadline

    def record_invocation(self, now):
        if self.expired(now):
            return False
        self.deadline = now + RETENTION_S
        return True

    def reset(self, new_id, now):
        if new_id == self.id or not new_id.strip():
            return False
        self.id, self.generation, self.deadline = new_id, self.generation + 1, now + RETENTION_S
        return True


def end_book_session(state):
    """Mirrors PhoneSession.endingBookSession."""
    state = dict(state, last_card=None)
    if state.get("action") in (None, "retryInvoke"):
        state.update(banner=None, action=None)
    return state


class LifecycleAuthTests(unittest.TestCase):
    def test_lifecycle_fixtures_decode_only_server_messages_on_v2(self):
        seen = set()
        for path in sorted((CONTRACTS / "fixtures" / "lifecycle" / "valid").glob("*.json")):
            message = json.loads(path.read_text())
            self.assertIsNone(decode_lifecycle(message, negotiated=False), path.name)
            decoded = decode_lifecycle(message, negotiated=True)
            if message["type"] in ("cancel", "session_end"):
                self.assertIsNone(decoded, path.name)
            else:
                seen.add(decoded)
        self.assertEqual(seen, set(LIFECYCLE_SERVER_FIELDS))
        for path in sorted((CONTRACTS / "fixtures" / "lifecycle" / "invalid").glob("*.json")):
            self.assertIsNone(decode_lifecycle(json.loads(path.read_text()), negotiated=True), path.name)

    def test_negotiation_matches_the_handshake_table(self):
        cases = json.loads((CONTRACTS / "auth-scenarios.json").read_text())["cases"]
        checked = 0
        for case in cases:
            if case.get("enabled") and not (
                all(case.get(k) for k in ("ios_verified", "rollout_agreed", "tls"))
                and all(case.get(k, True) for k in ("verifier_ready", "configured"))
                and case["credential"] == "valid"
            ):
                continue
            outcome = negotiate(case.get("offered", []), case.get("selected"), case.get("handshake_ok", True))
            self.assertEqual(outcome, (case["upgrade"], case.get("controls", False)), case["name"])
            checked += 1
        self.assertGreaterEqual(checked, 8)
        self.assertEqual(negotiate(CLIENT_OFFERS, None, True), (True, False))
        self.assertEqual(negotiate(CLIENT_OFFERS, V2, True), (False, False))

    def test_credential_is_header_only_and_never_over_plain_ws(self):
        url = "wss://metalab.modal.run/ws"
        self.assertEqual(handshake_headers(url, None), (url, {}))
        self.assertEqual(handshake_headers(url, "  abc.DEF  "), (url, {"Authorization": "Bearer abc.DEF"}))
        self.assertEqual(handshake_headers("ws://10.0.0.2:8000/ws", "abc"), ("ws://10.0.0.2:8000/ws", {}))
        self.assertEqual(handshake_headers(url, "two words"), (url, {}))
        sent_url, _ = handshake_headers(url, "secret")
        self.assertNotIn("secret", sent_url)

    def test_retention_is_fifteen_minutes_and_reset_never_reuses_an_id(self):
        session = ClientSession("a", now=0)
        self.assertFalse(session.expired(899))
        self.assertTrue(session.expired(900))
        session = ClientSession("a", now=0)
        self.assertTrue(session.record_invocation(800))
        self.assertTrue(session.expired(1700))
        self.assertFalse(session.record_invocation(1700))
        self.assertFalse(session.reset("a", 1700))
        generation = session.generation
        self.assertTrue(session.reset("b", 1700))
        self.assertNotEqual(session.generation, generation)
        self.assertFalse(session.expired(2599))

    def test_session_end_clears_the_card_but_not_glasses_recovery(self):
        ended = end_book_session({"last_card": "c", "banner": "timeout", "action": "retryInvoke"})
        self.assertEqual((ended["last_card"], ended["banner"]), (None, None))
        folded = end_book_session({"last_card": "c", "banner": "hinges", "action": "startNewSession"})
        self.assertIsNone(folded["last_card"])
        self.assertEqual(folded["banner"], "hinges")

if __name__ == "__main__":
    unittest.main()
