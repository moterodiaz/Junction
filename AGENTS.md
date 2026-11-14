# Team rules for every agent

## START HERE

New here or kickoff day? Read KICKOFF.md, then run tools/onboard.

Every agent reads this file first. The flow, in order:

1. **Own worktree.** `tools/wt <issue#>-<slug>` creates your branch from fresh `origin/main` in a sibling folder; work only there. Never edit in the shared checkout or on `main`. After your PR merges, `tools/wt rm <slug>`.
2. **The PRD is the source of truth** for what we build: `Junction-Prep/metalab_prd.md`. Every task cites a PRD section. If a task issue and the PRD disagree, the PRD wins; change the PRD only by PR.
3. **Get work from the issue board.** `tools/task next` shows the next unclaimed task; `tools/task claim <N>` takes it. Never start work without a claimed task issue.
4. **Ship on your own time.** When a feature is done, open a PR to `main` from your worktree (`Closes #N`).
5. **PRs run themselves.** Greptile reviews, `claude-fix` fixes its comments and pushes, `ci` runs, and GitHub auto-merges. Do not hand-fix bot threads or approve a PR; never use `--admin`. One exception: a PR that changes `.github/workflows/**` or `.claude/settings.json` needs one human merge.
6. **Never idle.** After opening a PR, run `tools/task next` and claim the next task. If the queue is below 3, run `tools/task fill` and file more tasks from the PRD.
7. **Conflicts go on the board**, not to a human: see section 6.

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

1. Name branches `<issue#>-<slug>` (`tools/wt` does this).
2. Small commits. Stage only your own files (no `git add -A`).
3. Open a PR with `Closes #N`, ready for review, not draft (Greptile skips drafts). Post its link on the board and move on.
4. Bots push to PR branches, so before pushing run `git pull --no-rebase`. Resolve conflicts by merging `origin/main` into your branch. Never rebase or force-push a pushed branch.
5. Agents may merge a team PR with `gh pr merge --squash --auto` once it is ready: GitHub holds the merge until every required check (`ci`) passes and all review threads are resolved, and `claude-fix` also enables it. Never use `--admin`, never merge a PR with failing or pending checks, and never approve a PR (`gh pr review --approve`). The board pings you on conflicts, `needs human`, and merge.
6. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what

TEMPLATE split, not final. The team will agree owners together; until then ask the lead before editing outside your own area.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| iOS app: thin client, Meta Wearables DAT capture and display, WebSocket client | TBD | `ios/` |
| Backend: FastAPI orchestrator on Modal, speech to text, page reading and reasoning, image generation | TBD | `backend/` |
| Shared contracts (WebSocket message schema, PRD section 7) | @moterodiaz (lead) | `contracts/` |

## 5. Supervisor + sub-agents

For an agent that fans work out to sub-agents (Claude → Codex, etc.):
- Split by file, never by feature. Two sub-agents never edit the same file.
- One worktree per implementer (`isolation: "worktree"` or `git worktree add`). Never share a working tree.
- Give each sub-agent an explicit list of files it may touch, plus the contract excerpt it needs.
- Sub-agents commit on their own branch and stop. They never push, open PRs, merge, or touch `main`.
- The supervisor reviews each diff, pushes, and opens the PR. Use a fresh reviewer, not the implementer, to check the final diff.
- Stop and ask the lead on the board for a contract change, a cross-owner edit, or a failing test you did not cause. Never delete or skip a test to pass.

## 6. Conflicts between agents

The board (issue #1) is where agents settle disagreements. No human input is needed. Every board post starts with your `[<human>'s <agent>]` tag (`tools/board` rejects posts without it); `[CONFLICT]` and `[RESOLVED]` are markers after the tag.

1. Post `[<human>'s <agent>] [CONFLICT] <files or area>: <@a's agent> vs <@b's agent>. Recommended: <one concrete path>. Why: <one line>.` Mention both owners.
2. Choose the recommended path in this order: (a) what the PRD says; (b) `contracts/` is authoritative and consumers adapt; (c) work already merged beats work not yet merged; (d) the smaller change yields.
3. If nobody objects within 10 minutes, the recommendation stands. Post `[<human>'s <agent>] [RESOLVED] <decision>. <who> merges origin/main and adapts.` The yielding side runs `git pull --no-rebase`, then `git fetch origin` and `git merge origin/main`, adapts, and pushes. If the PR is DIRTY (merge conflict), the author's agent runs `git pull --no-rebase`, then `git fetch origin` and `git merge origin/main`, resolves, and pushes without waiting for a human.
4. If someone objects, they post one counter-recommendation. Apply the order above once more and decide; do not loop.
5. Escalate to a human only for spend, credentials or access, or a PRD contradiction the order above cannot settle.
