import unittest

from app.config import DEFAULTS, ConfigError, Settings, auth_config, load_settings, max_connections

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


class DeployValidationTest(unittest.TestCase):
    """A deploy fails at startup, naming each problem, on config that would break the phone's
    deadlines or the auth contract (#133). Secret values never appear in the message."""

    def problems(self, **env):
        with self.assertRaises(ConfigError) as ctx:
            load_settings({**KEYS, **env})
        return str(ctx.exception)

    def test_valid_overrides_pass(self):
        load_settings({**KEYS, "STAGE_TIMEOUT_S": "20", "REQUEST_TIMEOUT_S": "80", "WS_AUTH": "off",
                       "WS_MAX_CONNECTIONS": "5"})
        load_settings({**KEYS, "WS_AUTH": "on", "WS_AUTH_TOKEN": "s3cret"})

    def test_timeouts_must_fit_inside_the_phone_limits(self):
        self.assertIn("STAGE_TIMEOUT_S must be below the phone's 30 s idle limit", self.problems(STAGE_TIMEOUT_S="30"))
        self.assertIn("REQUEST_TIMEOUT_S must be below the phone's 90 s limit", self.problems(REQUEST_TIMEOUT_S="95"))
        self.assertIn("STAGE_TIMEOUT_S must not exceed REQUEST_TIMEOUT_S",
                      self.problems(STAGE_TIMEOUT_S="25", REQUEST_TIMEOUT_S="20"))

    def test_timeouts_must_be_positive_numbers(self):
        self.assertIn("STAGE_TIMEOUT_S must be a number of seconds", self.problems(STAGE_TIMEOUT_S="soon"))
        self.assertIn("REQUEST_TIMEOUT_S must be above 0", self.problems(REQUEST_TIMEOUT_S="0"))

    def test_non_finite_timeouts_are_rejected(self):
        for value in ("nan", "inf"):
            self.assertIn("STAGE_TIMEOUT_S must be above 0", self.problems(STAGE_TIMEOUT_S=value))
            self.assertIn("REQUEST_TIMEOUT_S must be above 0", self.problems(REQUEST_TIMEOUT_S=value))

    def test_every_problem_is_named_at_once(self):
        msg = self.problems(STAGE_TIMEOUT_S="40", WS_AUTH="on", WS_MAX_CONNECTIONS="0")
        for part in ("STAGE_TIMEOUT_S", "WS_AUTH is on but WS_AUTH_TOKEN is empty", "WS_MAX_CONNECTIONS"):
            self.assertIn(part, msg)

    def test_auth_mode_must_be_on_or_off(self):
        self.assertIn("WS_AUTH must be on or off", self.problems(WS_AUTH="maybe", WS_AUTH_TOKEN="s3cret"))

    def test_messages_never_contain_secret_values(self):
        msg = self.problems(WS_AUTH="maybe", WS_AUTH_TOKEN="s3cret", STAGE_TIMEOUT_S="99")
        for secret in ("s3cret", "nv-secret", "gm-secret"):
            self.assertNotIn(secret, msg)


class AuthConfigTest(unittest.TestCase):
    def test_off_unless_turned_on(self):
        for mode in ("", "off", "0", "false", "no", "OFF"):
            self.assertFalse(auth_config({"WS_AUTH": mode, "WS_AUTH_TOKEN": "t"}).enabled)

    def test_on_needs_a_token_to_be_ready(self):
        self.assertTrue(auth_config({"WS_AUTH": "on", "WS_AUTH_TOKEN": "t"}).ready)
        self.assertFalse(auth_config({"WS_AUTH": "on"}).ready)

    def test_unknown_mode_is_enabled_but_not_ready(self):
        auth = auth_config({"WS_AUTH": "maybe", "WS_AUTH_TOKEN": "t"})
        self.assertTrue(auth.enabled)
        self.assertFalse(auth.ready)

    def test_repr_hides_the_token(self):
        self.assertNotIn("s3cret", repr(auth_config({"WS_AUTH": "on", "WS_AUTH_TOKEN": "s3cret"})))

    def test_connection_cap_defaults_to_modal_concurrency(self):
        self.assertEqual(max_connections({}), 20)
        self.assertEqual(max_connections({"WS_MAX_CONNECTIONS": "3"}), 3)
        self.assertEqual(max_connections({"WS_MAX_CONNECTIONS": "lots"}), 20)
        self.assertEqual(max_connections({"WS_MAX_CONNECTIONS": "0"}), 20)


if __name__ == "__main__":
    unittest.main()
