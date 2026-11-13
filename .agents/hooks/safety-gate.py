#!/usr/bin/env python3
import json
import re
import shlex
import sys
from pathlib import Path


ENV_RE = re.compile(r"(?:^|[\s/=<>'\"])\.env(?:\.[\w.-]+)?(?=$|[\s'\";|&<>)])")
SEGMENT_RE = re.compile(r"&&|\|\||[;|&\n]|\$\(|`|\(|\)")
GIT_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PROTECTED = {"main", "master"}


def split_segments(cmd):
    """Split on shell separators, ignoring those inside quotes.

    Inside double quotes only command substitution ($( and backtick) still
    starts a new command; inside single quotes nothing does.
    """
    segs, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and quote != "'" and i + 1 < len(cmd):
            buf.append(cmd[i:i + 2])
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
            elif quote == '"' and (c == "`" or cmd.startswith("$(", i)):
                segs.append("".join(buf))
                buf = []
                i += 2 if c == "$" else 1
                continue
            buf.append(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        m = SEGMENT_RE.match(cmd, i)
        if m:
            segs.append("".join(buf))
            buf = []
            i = m.end()
            continue
        buf.append(c)
        i += 1
    segs.append("".join(buf))
    return segs


def _git_sub(tokens):
    """Return (subcommand, args) after skipping git's global options."""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in GIT_OPTS_WITH_ARG:
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t, tokens[i + 1:]
    return "", []


def _short_flags(args):
    return "".join(a[1:] for a in args if re.fullmatch(r"-[A-Za-z]+", a))


def check_segment(tokens):
    # skip leading VAR=value assignments and wrappers
    while tokens and (re.fullmatch(r"\w+=.*", tokens[0]) or tokens[0] in ("sudo", "command", "env", "nohup", "time")):
        tokens = tokens[1:]
    if not tokens:
        return None
    exe = Path(tokens[0]).name
    args = tokens[1:]

    if exe == "git":
        sub, rest = _git_sub(tokens)
        if sub == "push":
            if any(a in ("--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete") or a.startswith(("--force-with-lease=", "--force-if-includes=")) for a in rest) \
                    or "f" in _short_flags(rest) or any(a.startswith("+") for a in rest):
                return "git push --force is prohibited by AGENTS.md rules."
            for a in rest:
                if a.startswith("-"):
                    continue
                dst = a.split(":")[-1]
                if re.sub(r"^refs/heads/", "", dst) in PROTECTED:
                    return "Pushing directly to main is prohibited."
        if sub == "reset" and "--hard" in rest:
            return "git reset --hard is prohibited."
        if sub == "clean":
            return "git clean is prohibited."
        if sub == "commit" and "--amend" in rest:
            return "git commit --amend is prohibited."
    elif exe == "gh":
        if args[:2] == ["pr", "merge"]:
            return "gh pr merge is prohibited (only claude-fix auto-merges per AGENTS.md)."
        if args[:2] == ["pr", "review"] and any(a == "--approve" or a == "-a" for a in args):
            return "Approving PRs via gh CLI is prohibited for agents."
    elif exe == "rm":
        flags = _short_flags(args)
        recursive = "r" in flags or "R" in flags or "--recursive" in args
        force = "f" in flags or "--force" in args
        if recursive and force:
            return "rm -rf is blocked for safety."
    return None


def check_tool_call(tool_call):
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    if name == "run_command":
        cmd = args.get("CommandLine", "")
        # .env: any mention in the command line, whichever command touches it
        if ENV_RE.search(cmd):
            return False, "Accessing .env via shell commands is prohibited."
        for seg in split_segments(cmd):
            try:
                tokens = shlex.split(seg)
            except ValueError:
                tokens = seg.split()
            reason = check_segment(tokens)
            if reason:
                return False, reason

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
