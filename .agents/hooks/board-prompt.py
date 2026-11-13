#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    cwd = payload.get("cwd") or str(Path(__file__).resolve().parent.parent.parent)
    board_issue = os.environ.get("BOARD_ISSUE", "1")
    board_tool = Path(cwd) / "tools" / "board"

    inject_steps = []
    if board_tool.exists():
        try:
            proc = subprocess.run(
                [str(board_tool), "unread"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                inject_steps.append({
                    "systemMessage": {
                        "systemMessage": f"New board posts (issue #{board_issue}):\n{proc.stdout.strip()}"
                    }
                })
        except Exception:
            pass

    result = {
        "injectSteps": inject_steps
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
