#!/usr/bin/env bash
# PreToolUse (Edit|Write): block edits to files whose worktree is on main.
# Checks the branch of the worktree holding the target file, not the session's start dir,
# so a session started on main can still edit inside a worktree created with tools/wt.
f="$(jq -r '.tool_input.file_path // empty' 2>/dev/null)"
d="${f:+$(dirname "$f")}"
while [ -n "$d" ] && [ ! -d "$d" ]; do d="$(dirname "$d")"; done  # new file in a new dir: climb to one that exists
b="$(git -C "${d:-${CLAUDE_PROJECT_DIR:-.}}" branch --show-current 2>/dev/null)"
[ "$b" != main ] || { echo 'On main: start a worktree first (tools/wt <issue#>-<slug>), then edit files inside it.' >&2; exit 2; }
