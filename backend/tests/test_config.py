import unittest

from app.config import DEFAULTS, ConfigError, Settings, load_settings

KEYS = {"NVIDIA_API_KEY": "nv-secret", "GEMINI_API_KEY": "gm-secret"}


class LoadSettingsTest(unittest.TestCase):
    def test_defaults_apply_when_only_keys_set(self):
        s = load_settings(KEYS)
        self.assertEqual(s.nvidia_api_key, "nv-secret")
        self.assertEqual(s.gemini_api_key, "gm-secret")
        self.assertEqual(s.model_read, DEFAULTS["MODEL_READ"])
        self.assertEqual(s.model_reason, DEFAULTS["MODEL_REASON"])
        self.assertEqual(s.nvidia_base_url, DEFAULTS["NVIDIA_BASE_URL"])
        self.assertEqual(s.model_decision, DEFAULTS["MODEL_DECISION"])
        self.assertEqual(s.model_reason_fast, DEFAULTS["MODEL_REASON_FAST"])
        self.assertEqual(s.model_reason_deep, DEFAULTS["MODEL_REASON_DEEP"])
        self.assertEqual(s.dynamic_model_routing, DEFAULTS["DYNAMIC_MODEL_ROUTING"])

    def test_overrides_win(self):
        s = load_settings({
            **KEYS,
            "MODEL_REASON": "gemini-4-hydrogen",
            "MODEL_DECISION": "custom-decision",
            "MODEL_REASON_FAST": "gemini-fast-custom",
            "MODEL_REASON_DEEP": "gemini-deep-custom",
            "DYNAMIC_MODEL_ROUTING": "true",
        })
        self.assertEqual(s.model_reason, "gemini-4-hydrogen")
        self.assertEqual(s.model_decision, "custom-decision")
        self.assertEqual(s.model_reason_fast, "gemini-fast-custom")
        self.assertEqual(s.model_reason_deep, "gemini-deep-custom")
        self.assertEqual(s.dynamic_model_routing, "true")

    def test_positional_settings_backward_compatibility(self):
        # Existing callers instantiating Settings with 7 positional fields
        s = Settings("nv-k", "gm-k", "https://url", "read-m", "reason-m", "img-m", "tts-m")
        self.assertEqual(s.model_reason, "reason-m")
        self.assertEqual(s.model_decision, "gemini-decision-1")
        self.assertEqual(s.model_reason_fast, "gemini-3.5-flash-lite")
        self.assertEqual(s.model_reason_deep, "gemini-4-carbon")
        self.assertEqual(s.dynamic_model_routing, "false")

    def test_blank_override_falls_back_to_default(self):
        s = load_settings({**KEYS, "MODEL_IMAGE": "  "})
        self.assertEqual(s.model_image, DEFAULTS["MODEL_IMAGE"])

    def test_missing_keys_fail_fast_naming_all_of_them(self):
        with self.assertRaises(ConfigError) as ctx:
            load_settings({})
        msg = str(ctx.exception)
        self.assertIn("NVIDIA_API_KEY", msg)
        self.assertIn("GEMINI_API_KEY", msg)
        self.assertIn("metalab", msg)

    def test_whitespace_key_counts_as_missing(self):
        with self.assertRaises(ConfigError) as ctx:
            load_settings({**KEYS, "GEMINI_API_KEY": "   "})
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))
        self.assertNotIn("NVIDIA_API_KEY", str(ctx.exception))

    def test_repr_hides_secrets(self):
        r = repr(load_settings(KEYS))
        self.assertNotIn("nv-secret", r)
        self.assertNotIn("gm-secret", r)


if __name__ == "__main__":
    unittest.main()
