"""Per-stage latency and privacy-safe model choice distribution tracking (PRD section 6, 9; REQ-LAT-01, REQ-PRIV-02)."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
import threading
import time
from typing import Any

log = logging.getLogger("metalab.latency")
clock = time.perf_counter

DEFAULT_STAGES = ("decision", "read", "reason", "image", "tts")
_SAFE_STAGE_RE = re.compile(r"^[a-z0-9_\-]{1,32}$", re.IGNORECASE)
_SAFE_MODEL_RE = re.compile(r"^[a-zA-Z0-9_\-\.\/]{1,64}$")


def _validate_safe_identifier(value: Any, name: str, pattern: re.Pattern) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    val = value.strip()
    if not val or not pattern.match(val):
        raise ValueError(
            f"Unsafe {name} rejected by REQ-PRIV-02: must be safe identifier matching {pattern.pattern}"
        )
    return val


class ModelDistribution(dict):
    """Snapshot of model choice distribution counters (REQ-PRIV-02: stage/model IDs + ints only)."""

    def __missing__(self, key: str) -> Any:
        stages = self.get("stages", {})
        if isinstance(stages, dict) and key in stages:
            return stages[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        stages = super().get("stages", {})
        if isinstance(stages, dict) and key in stages:
            return stages[key]
        return default


class ModelChoiceTracker:
    """Thread-safe, in-memory telemetry tracker for model choice distribution and fallbacks."""

    def __init__(self, stages: tuple[str, ...] = DEFAULT_STAGES) -> None:
        self._lock = threading.Lock()
        self._stages: dict[str, dict[str, int]] = {s: {} for s in stages}
        self._fallbacks: dict[str, int] = {s: 0 for s in stages}
        self._fallback_total: int = 0
        self._total: int = 0

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    @property
    def fallback_total(self) -> int:
        with self._lock:
            return self._fallback_total

    def record_choice(self, stage: str, model_id: str, fallback: bool = False) -> None:
        """Record a single model choice for a stage."""
        if not isinstance(fallback, (bool, int)):
            raise TypeError("fallback must be a boolean")
        safe_stage = _validate_safe_identifier(stage, "stage", _SAFE_STAGE_RE).lower()
        safe_model = _validate_safe_identifier(model_id, "model_id", _SAFE_MODEL_RE)
        is_fallback = bool(fallback)

        with self._lock:
            if safe_stage not in self._stages:
                self._stages[safe_stage] = {}
                self._fallbacks[safe_stage] = 0

            self._stages[safe_stage][safe_model] = (
                self._stages[safe_stage].get(safe_model, 0) + 1
            )
            self._total += 1

            if is_fallback:
                self._fallbacks[safe_stage] += 1
                self._fallback_total += 1

    record_model_choice = record_choice

    def get_distribution(self) -> ModelDistribution:
        """Return a snapshot of distribution counters."""
        with self._lock:
            stages_copy = {s: dict(models) for s, models in self._stages.items()}
            fallbacks_copy = dict(self._fallbacks)
            return ModelDistribution(
                {
                    "stages": stages_copy,
                    "fallback_by_stage": fallbacks_copy,
                    "fallback_total": self._fallback_total,
                    "total": self._total,
                }
            )

    get_model_distribution = get_distribution

    def reset(self, stages: tuple[str, ...] = DEFAULT_STAGES) -> None:
        """Reset counters to zero."""
        with self._lock:
            self._stages = {s: {} for s in stages}
            self._fallbacks = {s: 0 for s in stages}
            self._fallback_total = 0
            self._total = 0

    reset_model_distribution = reset

    def log_summary(self) -> str:
        """Log a summary of model choices and fallback counts."""
        dist = self.get_distribution()
        total = dist["total"]
        fallback_total = dist["fallback_total"]

        parts = []
        for stage, models in sorted(dist["stages"].items()):
            fb = dist["fallback_by_stage"].get(stage, 0)
            if models:
                model_strs = [f"{m}={cnt}" for m, cnt in sorted(models.items())]
                parts.append(f"{stage}[{','.join(model_strs)},fallbacks={fb}]")
            elif fb > 0:
                parts.append(f"{stage}[fallbacks={fb}]")
            else:
                parts.append(f"{stage}[none]")

        summary_str = f"total={total} fallback_total={fallback_total} " + " ".join(parts)
        log.info("model_distribution %s", summary_str)
        return summary_str

    log_model_distribution_summary = log_summary


_DEFAULT_TRACKER = ModelChoiceTracker()


def record_model_choice(stage: str, model_id: str, fallback: bool = False) -> None:
    _DEFAULT_TRACKER.record_choice(stage, model_id, fallback)


def get_model_distribution() -> ModelDistribution:
    return _DEFAULT_TRACKER.get_distribution()


def reset_model_distribution() -> None:
    _DEFAULT_TRACKER.reset()


def log_model_distribution_summary() -> str:
    return _DEFAULT_TRACKER.log_summary()


_current_timer: ContextVar["StageTimer | None"] = ContextVar("metalab_stage_timer", default=None)


def note_stt_words(count: int) -> None:
    """Record the transcript's word count on this request's latency line (never the words)."""
    timer = _current_timer.get()
    if timer is not None:
        timer.stt_words = int(count)


class StageTimer:
    """A stage runs from its start() until the next start() or finish(). Creating one makes it
    the current request's timer for note_stt_words()."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.began = clock()
        self.current: tuple[str, float] | None = None
        self.durations: dict[str, float] = {}
        self.stt_words: int | None = None
        _current_timer.set(self)

    def start(self, stage: str) -> None:
        now = clock()
        self._close(now)
        self.current = (stage, now)

    def finish(self) -> dict[str, float]:
        now = clock()
        self._close(now)
        return {**self.durations, "total": round(now - self.began, 3)}

    def log(self, outcome: str) -> None:
        parts = " ".join(f"{name}={seconds:.3f}s" for name, seconds in self.finish().items())
        if self.stt_words is not None:
            parts += f" stt_words={self.stt_words}"
        log.info("latency request=%s outcome=%s %s", self.request_id, outcome, parts)

    def _close(self, now: float) -> None:
        if self.current is not None:
            stage, started = self.current
            self.durations[stage] = round(now - started, 3)
            self.current = None
