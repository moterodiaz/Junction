#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


DENY_COMMAND_PATTERNS = [
    (re.compile(r"\bgit\s+push\b.*(--force\b|-f\b)", re.IGNORECASE), "git push --force is prohibited by AGENTS.md rules."),
    (re.compile(r"\bgit\s+push\b.*\borigin\s+main\b", re.IGNORECASE), "Pushing directly to origin main is prohibited."),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "git reset --hard is prohibited."),
    (re.compile(r"\bgit\s+clean\b", re.IGNORECASE), "git clean is prohibited."),
    (re.compile(r"\bgit\s+commit\s+--amend\b", re.IGNORECASE), "git commit --amend is prohibited."),
    (re.compile(r"\bgh\s+pr\s+merge\b", re.IGNORECASE), "gh pr merge is prohibited (only claude-fix auto-merges per AGENTS.md)."),
    (re.compile(r"\bgh\s+pr\s+review\b.*--approve\b", re.IGNORECASE), "Approving PRs via gh CLI is prohibited for agents."),
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive\s+--force)\b", re.IGNORECASE), "rm -rf is blocked for safety."),
]


def check_tool_call(tool_call):
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    # Check shell commands
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        # Check command patterns
        for pattern, reason in DENY_COMMAND_PATTERNS:
            if pattern.search(cmd):
                return False, reason
        # Check access to .env in command lines
        if re.search(r"(^|\s)(cat|head|tail|less|more|source|vi|vim|nano|tee|\.|bash|sh)\s+.*?(\.env|\.env\.[a-zA-Z0-9._-]+)", cmd):
            return False, "Accessing .env via shell commands is prohibited."

    # Check file operations
    if name in ("read_file", "edit_file", "write_file"):
        path = args.get("Path", "")
        p = Path(path)
        if p.name == ".env" or p.name.startswith(".env."):
            return False, f"Direct access to {p.name} is prohibited."

    return True, ""


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        payload = {}

    tool_call = payload.get("toolCall", {})
    allowed, reason = check_tool_call(tool_call)

    if allowed:
        result = {"decision": "allow"}
    else:
        result = {"decision": "deny", "reason": reason}

    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
