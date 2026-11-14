"""Actual CURRENT backend checks, not proposed v2 cleanup/auth conformance."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from test_conformance import app, deadline, drive, flow_problems, load, schema_problems
from test_lifecycle import ROOT


class ActualLegacyLifecycleRejectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        for key in ("GEMINI_API_KEY", "NVIDIA_API_KEY"):
            os.environ.pop(key, None)
        # Guard the reasoning adapter's HTTP boundary as well as removing keys.
        guard = mock.patch("urllib.request.urlopen", side_effect=AssertionError("offline contract test"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_current_backend_does_not_claim_v2_support(self) -> None:
        with deadline(10), TestClient(app).websocket_connect("/ws", subprotocols=["metalab.v2"]) as ws:
            self.assertIsNone(ws.accepted_subprotocol)
            ws.send_json({"type": "cancel", "request_id": "req-a", "session_id": "session-a"})
            reply = ws.receive_json()
            self.assertEqual(reply["type"], "error")
            self.assertEqual(reply["code"], "internal")
            self.assertFalse(reply["retryable"])
            self.assertEqual(schema_problems(reply, "actual legacy rejection"), [])

    def test_new_controls_are_rejected_without_breaking_legacy(self) -> None:
        legacy = load("text-invoke")
        for name in ("cancel", "session-end"):
            message = json.loads((ROOT / "fixtures" / "lifecycle" / "valid" / f"{name}.json").read_text())
            with self.subTest(control=name):
                # drive() also fails on any unsolicited/extra response.
                exchange = {"send": [{"text": message}, *legacy["send"]]}
                replies = drive(exchange, count=1 + len(legacy["receive"]))
                self.assertEqual(len(replies), 1 + len(legacy["receive"]))
                self.assertEqual(replies[0]["request_id"], message["request_id"])
                self.assertEqual(replies[0]["type"], "error")
                self.assertEqual(replies[0]["code"], "internal")
                self.assertFalse(replies[0]["retryable"])
                for i, reply in enumerate(replies):
                    self.assertEqual(schema_problems(reply, f"actual legacy receive[{i}]"), [])
                self.assertEqual(flow_problems(exchange, replies), [])
                self.assertEqual(replies[-1]["type"], "card")


if __name__ == "__main__":
    unittest.main()
