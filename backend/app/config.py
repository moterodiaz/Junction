"""Backend configuration: every environment variable the backend reads.

On Modal the values come from the Modal secret named in MODAL_SECRET_NAME;
locally they come from the shell or a .env file (see backend/.env.example).
Secrets never live in the repo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Mapping

# Name of the Modal secret that holds the variables below.
MODAL_SECRET_NAME = "metalab"

REQUIRED = ("NVIDIA_API_KEY", "GEMINI_API_KEY")

# Optional overrides and their defaults (PRD section 4, Models).
DEFAULTS = {
    "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
    "MODEL_READ": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "MODEL_REASON": "gemini-4-argon",
    "MODEL_IMAGE": "gemini-nano-banana-2.1",
    "MODEL_TTS": "gemini-3.8-flash-tts",
}


class ConfigError(RuntimeError):
    """A required environment variable is missing or empty."""


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str = field(repr=False)
    gemini_api_key: str = field(repr=False)
    nvidia_base_url: str
    model_read: str
    model_reason: str
    model_image: str
    model_tts: str


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from env (default os.environ); raise ConfigError listing every missing variable."""
    env = os.environ if env is None else env

    def get(name: str) -> str:
        return env.get(name, "").strip()

    missing = [name for name in REQUIRED if not get(name)]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"On Modal, add them to the '{MODAL_SECRET_NAME}' secret; "
            "locally, export them or copy backend/.env.example to backend/.env."
        )

    return Settings(
        nvidia_api_key=get("NVIDIA_API_KEY"),
        gemini_api_key=get("GEMINI_API_KEY"),
        **{name.lower(): get(name) or default for name, default in DEFAULTS.items()},
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for the running process. Call once at startup so a missing secret fails fast."""
    return load_settings()
