"""Backend configuration: every environment variable the backend reads.

On Modal the values come from the Modal secret named in MODAL_SECRET_NAME;
locally they must be exported in the shell (names listed in backend/.env.example;
this module does not read .env files).
Secrets never live in the repo.
"""

from __future__ import annotations

import math
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
    "MODEL_DECISION": "gemini-decision-1",
    "MODEL_REASON_FAST": "gemini-3.5-flash-lite",
    "MODEL_REASON_DEEP": "gemini-4-carbon",
    "DYNAMIC_MODEL_ROUTING": "false",
    "STT_ENGINE": "whisper",
}


# The phone gives up after 30 s without a message and 90 s in total (PRD section 7).
PHONE_IDLE_LIMIT_S = 30.0
PHONE_TOTAL_LIMIT_S = 90.0
DEFAULT_MAX_CONNECTIONS = 20  # matches @modal.concurrent(max_inputs=20) in modal_app.py
ON, OFF = ("on", "1", "true", "yes"), ("", "off", "0", "false", "no")


class ConfigError(RuntimeError):
    """A required environment variable is missing, empty or invalid."""


@dataclass(frozen=True)
class AuthConfig:
    """Optional bearer auth on the /ws handshake (contracts/LIFECYCLE.md, "Optional auth handoff").

    Off by default. Enable (WS_AUTH=on) only after the iOS client is shown to send the
    Authorization header over WSS and the owners agree the rollout. `ready` is False when auth
    is on but cannot verify (no token, unknown WS_AUTH value): every handshake then fails closed.
    """

    enabled: bool
    ready: bool
    token: str = field(repr=False, default="")


def auth_config(env: Mapping[str, str] | None = None) -> AuthConfig:
    env = os.environ if env is None else env
    mode = env.get("WS_AUTH", "").strip().lower()
    token = env.get("WS_AUTH_TOKEN", "").strip()
    if mode in OFF:
        return AuthConfig(enabled=False, ready=True)
    return AuthConfig(enabled=True, ready=mode in ON and bool(token), token=token)


def trust_forwarded_proto(env: Mapping[str, str] | None = None) -> bool:
    """Whether X-Forwarded-Proto may prove TLS. Turn on only where every request reaches the app
    through a proxy that sets it (Modal); off, only the server's own connection scheme counts."""
    env = os.environ if env is None else env
    return env.get("WS_TRUST_FORWARDED_PROTO", "").strip().lower() in ON


def max_connections(env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    try:
        value = int(env.get("WS_MAX_CONNECTIONS", "").strip() or DEFAULT_MAX_CONNECTIONS)
    except ValueError:
        return DEFAULT_MAX_CONNECTIONS
    return value if value >= 1 else DEFAULT_MAX_CONNECTIONS


def config_problems(env: Mapping[str, str]) -> list[str]:
    """Deployed-config mistakes that would break the phone's deadlines or the auth contract.
    Messages name the variable, never a secret value."""
    problems = []

    def seconds(name: str, default: float) -> float | None:
        raw = env.get(name, "").strip()
        try:
            value = float(raw) if raw else default
        except ValueError:
            problems.append(f"{name} must be a number of seconds")
            return None
        if not math.isfinite(value) or value <= 0:
            problems.append(f"{name} must be a finite number above 0")
            return None
        return value

    stage = seconds("STAGE_TIMEOUT_S", 25.0)
    request = seconds("REQUEST_TIMEOUT_S", 85.0)
    if stage is not None and stage >= PHONE_IDLE_LIMIT_S:
        problems.append(f"STAGE_TIMEOUT_S must be below the phone's {PHONE_IDLE_LIMIT_S:g} s idle limit")
    if request is not None and request >= PHONE_TOTAL_LIMIT_S:
        problems.append(f"REQUEST_TIMEOUT_S must be below the phone's {PHONE_TOTAL_LIMIT_S:g} s limit")
    if stage is not None and request is not None and stage > request:
        problems.append("STAGE_TIMEOUT_S must not exceed REQUEST_TIMEOUT_S")

    mode = env.get("WS_AUTH", "").strip().lower()
    if mode not in ON + OFF:
        problems.append("WS_AUTH must be on or off")
    elif mode in ON and not env.get("WS_AUTH_TOKEN", "").strip():
        problems.append("WS_AUTH is on but WS_AUTH_TOKEN is empty")

    if env.get("WS_TRUST_FORWARDED_PROTO", "").strip().lower() not in ON + OFF:
        problems.append("WS_TRUST_FORWARDED_PROTO must be on or off")

    raw = env.get("WS_MAX_CONNECTIONS", "").strip()
    if raw and (not raw.isdigit() or int(raw) < 1):
        problems.append("WS_MAX_CONNECTIONS must be a whole number of at least 1")
    return problems


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str = field(repr=False)
    gemini_api_key: str = field(repr=False)
    nvidia_base_url: str
    model_read: str
    model_reason: str
    model_image: str
    model_tts: str
    model_decision: str = "gemini-decision-1"
    model_reason_fast: str = "gemini-3.5-flash-lite"
    model_reason_deep: str = "gemini-4-carbon"
    dynamic_model_routing: str = "false"
    stt_engine: str = "whisper"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from env (default os.environ); raise ConfigError listing every missing
    variable, then every invalid one (config_problems)."""
    env = os.environ if env is None else env

    def get(name: str) -> str:
        return env.get(name, "").strip()

    missing = [name for name in REQUIRED if not get(name)]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"On Modal, add them to the '{MODAL_SECRET_NAME}' secret; "
            "locally, export them in your shell (see backend/.env.example for the names); "
            "this module does not read .env files."
        )
    problems = config_problems(env)
    if problems:
        raise ConfigError("Invalid configuration: " + "; ".join(problems) + ".")

    return Settings(
        nvidia_api_key=get("NVIDIA_API_KEY"),
        gemini_api_key=get("GEMINI_API_KEY"),
        **{name.lower(): get(name) or default for name, default in DEFAULTS.items()},
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for the running process. Call once at startup so a missing secret fails fast."""
    return load_settings()
