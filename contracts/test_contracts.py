from __future__ import annotations

import json
from pathlib import Path
import unittest

import jsonschema
from jsonschema import Draft202012Validator


CONTRACTS_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = CONTRACTS_DIR / "ws-messages.schema.json"
VALID_DIR = CONTRACTS_DIR / "fixtures" / "valid"
INVALID_DIR = CONTRACTS_DIR / "fixtures" / "invalid"


class WebSocketContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_schema_defines_expected_enums(self) -> None:
        defs = self.schema["$defs"]
        self.assertEqual(
            defs["statusStage"]["enum"],
            ["transcribing", "reading", "thinking", "drawing"],
        )
        self.assertEqual(
            defs["errorCode"]["enum"],
            ["no_text_found", "stt_failed", "model_timeout", "internal"],
        )

    def test_valid_fixtures_pass_schema(self) -> None:
        valid_files = sorted(VALID_DIR.glob("*.json"))
        self.assertGreaterEqual(len(valid_files), 4, "Expected valid fixtures for all 4 message types")
        seen_types: set[str] = set()
        for path in valid_files:
            with self.subTest(fixture=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.validator.validate(payload)
                seen_types.add(payload["type"])
        self.assertEqual(seen_types, {"invoke", "status", "card", "error"})

    def test_invalid_fixtures_fail_schema(self) -> None:
        invalid_files = sorted(INVALID_DIR.glob("*.json"))
        self.assertGreaterEqual(len(invalid_files), 4, "Expected invalid fixtures")
        for path in invalid_files:
            with self.subTest(fixture=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                with self.assertRaises(
                    jsonschema.ValidationError,
                    msg=f"Invalid fixture unexpectedly passed validation: {path.name}",
                ):
                    self.validator.validate(payload)

    def test_invoke_requires_exactly_one_of_audio_or_text(self) -> None:
        base = {
            "type": "invoke",
            "request_id": "req-1",
            "session_id": "sess-1",
            "frame": {"mime": "image/jpeg", "b64": "/9j/"},
        }
        audio = {"mime": "audio/wav", "b64": "UklGRg=="}
        cases = {
            "audio only": ({"audio": audio, "text": None}, True),
            "audio only, text omitted": ({"audio": audio}, True),
            "text only": ({"audio": None, "text": "explain"}, True),
            "text only, audio omitted": ({"text": "explain"}, True),
            "both set": ({"audio": audio, "text": "explain"}, False),
            "both null": ({"audio": None, "text": None}, False),
            "neither present": ({}, False),
        }
        for name, (extra, should_pass) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.validator.is_valid({**base, **extra}), should_pass)


if __name__ == "__main__":
    unittest.main()
