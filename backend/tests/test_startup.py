"""#90: a deploy with a missing secret fails at startup, naming every missing key (PRD section 4)."""

import os
import unittest
from unittest import mock

from app import config
from app.config import ConfigError
from app.main import app, create_app


class StartupCheckTest(unittest.TestCase):
    def setUp(self):
        config.get_settings.cache_clear()
        self.addCleanup(config.get_settings.cache_clear)

    def test_missing_keys_fail_at_startup_naming_all_of_them(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""}):
            with self.assertRaises(ConfigError) as ctx:
                create_app(require_keys=True)
        self.assertIn("NVIDIA_API_KEY", str(ctx.exception))
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_complete_keys_start(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "nv", "GEMINI_API_KEY": "gm"}):
            self.assertIs(create_app(require_keys=True), app)

    def test_local_runs_and_tests_stay_keyless(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "", "GEMINI_API_KEY": ""}):
            self.assertIs(create_app(), app)


if __name__ == "__main__":
    unittest.main()
