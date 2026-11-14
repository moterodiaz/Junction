"""Per-stage latency (PRD section 9: measure each stage before optimising anything)."""

from __future__ import annotations

import logging
import time

log = logging.getLogger("metalab.latency")
clock = time.perf_counter


class StageTimer:
    """A stage runs from its start() until the next start() or finish()."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.began = clock()
        self.current: tuple[str, float] | None = None
        self.durations: dict[str, float] = {}

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
        log.info("latency request=%s outcome=%s %s", self.request_id, outcome, parts)

    def _close(self, now: float) -> None:
        if self.current is not None:
            stage, started = self.current
            self.durations[stage] = round(now - started, 3)
            self.current = None
