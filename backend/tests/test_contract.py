"""#32: invokes are checked as strictly as the contract, and every reply matches it (PRD section 7)."""

import json
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

import stt
from app.main import app
from app.messages import Invoke

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / "ws-messages.schema.json").read_text()))
FIXTURES = CONTRACTS / "fixtures"

FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}
AUDIO = {"mime": "audio/wav", "b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="}


def invoke(**overrides):
    msg = {"type": "invoke", "request_id": "r1", "session_id": "s1", "frame": FRAME,
           "audio": None, "text": "explain"}
    msg.update(overrides)
    return msg


def replies_to(message, until=("card", "error")):
    """Send one message; collect replies up to and including the first card or error."""
    out = []
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json(message) if not isinstance(message, str) else ws.send_text(message)
        while True:
            out.append(ws.receive_json())
            if out[-1]["type"] in until:
                return out


def fixtures(kind, prefix):
    return sorted((FIXTURES / kind).glob(f"{prefix}*.json"))


class ContractInputTest(unittest.TestCase):
    def test_valid_invoke_fixtures_are_accepted(self):
        for path in fixtures("valid", "invoke"):
            with self.subTest(path.name):
                Invoke.model_validate(json.loads(path.read_text()))

    def test_invalid_invoke_fixtures_are_rejected(self):
        for path in fixtures("invalid", "invoke"):
            with self.subTest(path.name), self.assertRaises(ValidationError):
                Invoke.model_validate(json.loads(path.read_text()))

    def test_extra_fields_and_blank_ids_are_rejected(self):
        for bad in (invoke(extra=1), invoke(request_id=""), invoke(session_id="")):
            with self.subTest(bad), self.assertRaises(ValidationError):
                Invoke.model_validate(bad)


class RepliesMatchSchemaTest(unittest.TestCase):
    """Every reply the backend sends validates against contracts/ws-messages.schema.json."""

    def setUp(self):
        self.addCleanup(stt.set_engine, stt.set_engine(lambda audio: "draw this"))
        patcher = mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_schema_valid(self, replies):
        for reply in replies:
            errors = [e.message for e in SCHEMA.iter_errors(reply)]
            self.assertEqual(errors, [], reply)

    def test_text_and_audio_flows(self):
        for message in (invoke(), invoke(text=None, audio=AUDIO)):
            with self.subTest(message):
                replies = replies_to(message)
                self.assertEqual(replies[-1]["type"], "card")
                self.assert_schema_valid(replies)

    def test_every_error_path(self):
        cases = {
            "not json": "nope",
            "invalid invoke": invoke(text=None),
            "unknown command": invoke(text="sing"),
        }
        for name, message in cases.items():
            with self.subTest(name):
                replies = replies_to(message)
                self.assertEqual(replies[-1]["type"], "error")
                self.assert_schema_valid(replies)


if __name__ == "__main__":
    unittest.main()
