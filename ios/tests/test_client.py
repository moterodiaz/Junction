#!/usr/bin/env python3
"""Behavioral checks for the thin client. Mirrors MetaLabCore so CI can run without Xcode."""

import json
import unittest


STAGES = ("transcribing", "reading", "thinking", "drawing")
ERROR_CODES = ("no_text_found", "stt_failed", "model_timeout", "internal")


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


if __name__ == "__main__":
    unittest.main()
