"""Opt-in STT debug log (REQ-OBS-02): one JSON line per transcription, for glasses test runs.

Off by default. With STT_DEBUG_LOG=on every clip's transcript and engine details are appended
to STT_DEBUG_LOG_PATH (on Modal a Volume mounted at /stt-logs). This is the only place user
speech is written down (the exception to REQ-PRIV-01/02), so it exists only while the flag is on.
Logging must never break a request: every failure is swallowed and only its type is logged.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
import time
from typing import Any, Callable

_log = logging.getLogger("metalab")

DEFAULT_PATH = "/stt-logs/transcripts.jsonl"
COMMIT_INTERVAL_S = 10.0
_ON = ("on", "1", "true", "yes")

_write_lock = threading.Lock()
_commit_lock = threading.Lock()
_commit_hook: Callable[[], Any] | None = None
_last_commit = 0.0
_dirty = False


def enabled() -> bool:
    return os.environ.get("STT_DEBUG_LOG", "").strip().lower() in _ON


def path() -> str:
    return os.environ.get("STT_DEBUG_LOG_PATH", "").strip() or DEFAULT_PATH


def set_commit_hook(fn: Callable[[], Any] | None) -> Callable[[], Any] | None:
    """Register a function that persists written lines (Modal: volume.commit); return the old one."""
    global _commit_hook
    previous, _commit_hook = _commit_hook, fn
    return previous


def record(**fields: Any) -> None:
    """Append one JSON line. Never raises."""
    global _dirty
    try:
        line = json.dumps(fields, ensure_ascii=False, default=str) + "\n"
        target = path()
        with _write_lock:
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(line)
            _dirty = True
    except Exception as exc:
        _log.debug("stt debug log write skipped: %s", type(exc).__name__)
        return
    _commit_in_background()


_worker: threading.Thread | None = None


def _commit_in_background() -> None:
    """Commit off the caller's thread: a slow Volume commit must never delay a transcript."""
    global _worker
    if _commit_hook is None:
        return
    _worker = threading.Thread(target=_maybe_commit, daemon=True)
    _worker.start()


def wait_for_commit() -> None:
    """Block until the latest background commit attempt finishes (tests)."""
    worker = _worker
    if worker is not None:
        worker.join()


def _maybe_commit(force: bool = False) -> None:
    global _last_commit, _dirty
    hook = _commit_hook
    if hook is None:
        return
    # A commit uploads the volume's changes, so run at most one at a time and at most every
    # COMMIT_INTERVAL_S; the shutdown commit catches whatever the throttle held back.
    if not _commit_lock.acquire(blocking=force):
        return
    try:
        now = time.monotonic()
        if not _dirty:
            return
        wait = COMMIT_INTERVAL_S - (now - _last_commit)
        if not force and wait > 0:
            _schedule(wait)  # a quiet test run must not leave its last lines uncommitted
            return
        _dirty = False
        _last_commit = now
        try:
            hook()
        except Exception as exc:
            _dirty = True
            _log.debug("stt debug log commit skipped: %s", type(exc).__name__)
    finally:
        _commit_lock.release()


_timer: threading.Timer | None = None


def _schedule(delay: float) -> None:
    global _timer
    if _timer is not None and _timer.is_alive() and _timer is not threading.current_thread():
        return
    _timer = threading.Timer(delay, _maybe_commit)
    _timer.daemon = True
    _timer.start()


def flush() -> None:
    """Commit any lines written since the last commit (called at shutdown)."""
    try:
        _maybe_commit(force=True)
    except Exception as exc:
        _log.debug("stt debug log flush skipped: %s", type(exc).__name__)


atexit.register(flush)
