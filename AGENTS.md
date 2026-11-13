# Team rules for every agent

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. Fill in your team: `@moterodiaz` (Mateo, team lead), `@Ahm3d-KA`, `@maksymmatviievskyi`, `@Marcus228`, `@all` (everyone).
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.
- Sub-agents spawned by a supervisor agent (e.g. Codex workers): do not run `tools/board wait`; the supervisor relays. Run them with `BOARD_WAIT=off`.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Humans over agents. Only the team lead reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board.

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Every agent session works in its own worktree: `tools/wt <issue#>-<slug>` creates the branch from fresh `origin/main` in a sibling folder; `cd` into it. Never edit in the main checkout or on `main`. Remove it after merge with `tools/wt rm <slug>`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`, ready for review, not draft (Greptile skips drafts). Greptile reviews it; `claude-fix` addresses its comments and enables auto-merge. Don't hand-fix bot threads unless the board says `needs human`.
5. Bots push to PR branches, so before pushing run `git pull --no-rebase`. Resolve conflicts by merging `origin/main` into your branch. Never rebase or force-push a pushed branch.
6. Agents may merge a team PR with `gh pr merge --squash --auto` once it is ready: GitHub holds the merge until every required check (`ci`) passes and all review threads are resolved, and `claude-fix` also enables it. Never use `--admin`, never merge a PR with failing or pending checks, and never approve a PR (`gh pr review --approve`). After opening a PR, post its link on the board and move on. The board pings you on conflicts, `needs human`, and merge.
7. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what

TEMPLATE split, not final. The team will agree owners together; until then ask the lead before editing outside your own area.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| Pi edge capture (motion gate, I2S mic, WS server) | TBD | `pi/` |
| iPhone orchestrator (STT, prompt router, Claude calls) | TBD | `ios/` |
| HUD renderer | TBD | `hud/` |
| Shared contracts (WS message schema) | @moterodiaz (lead) | `contracts/` |

## 5. Supervisor + sub-agents

For an agent that fans work out to sub-agents (Claude → Codex, etc.):
- Split by file, never by feature. Two sub-agents never edit the same file.
- One worktree per implementer (`isolation: "worktree"` or `git worktree add`). Never share a working tree.
- Give each sub-agent an explicit list of files it may touch, plus the contract excerpt it needs.
- Sub-agents commit on their own branch and stop. They never push, open PRs, merge, or touch `main`.
- The supervisor reviews each diff, pushes, and opens the PR. Use a fresh reviewer, not the implementer, to check the final diff.
- Stop and ask the lead on the board for a contract change, a cross-owner edit, or a failing test you did not cause. Never delete or skip a test to pass.
