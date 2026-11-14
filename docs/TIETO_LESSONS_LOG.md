# Tieto lessons log

Real incidents from building MetaLab with AI agents on 2026-11-14 (times UTC), each with what we changed. Entries marked "already fixed" were fixed before or during the build; the others link the change that addresses them.

## 1. A P1 finding sat for 30 minutes because the fix landed on another branch  (09:11 to 09:42, PR #68)
**What happened.** Greptile flagged a P1 on #68: a non-string `request_id` closed the socket. `claude-fix` ran twice and posted "needs human: could not resolve 1 thread(s), no fix pushed". The owner's agent wrote the fix, but in the worktree of its next task, so #68 stayed blocked for 30 minutes.
**Why.** An agent working on several tasks lost track of which branch it was on. Nothing tied the escalation to the branch that needed the fix.
**What we changed.** One worktree per task (`tools/wt <issue>-<slug>`, AGENTS.md START HERE rule 1), and escalations name the PR and its branch.
**Rubric lesson.** Practicality: an escalation must reach a named human with enough context to act on the right branch.

## 2. The safety net failed on almost every run and nobody noticed  (all day, `pr-sweeper.yml`)
**What happened.** The sweeper's "Retry stuck claude-fix" step failed with "GraphQL: … requesting up to 1,000,000 possible nodes which exceeds the maximum limit of 500,000". 170 of its last 200 runs failed, so the retries and the "sweeper gave up, needs human" escalation never ran.
**Why.** `gh pr list --json …,commits --limit 100` asks GitHub for every commit of every PR. The sweeper alerts on other workflows' failures but not on its own.
**What we changed.** The sweeper reads commits through the REST endpoint for one PR at a time (#119).
**Rubric lesson.** Measurement: a control that is not monitored is not a control.

## 3. Branches stacked on unmerged work produced add/add conflicts  (09:08 to 10:40, PRs #68, #79, #32)
**What happened.** Agents branched new work from a dependency's unmerged branch. `claude-fix` then rewrote the dependency's branch, and the squash merge produced add/add conflicts downstream in `config.py`, `.env.example`, `main.py` and `test_ws.py`.
**Why.** A squash merge creates a new commit, so branches built on the old commits no longer share history with `main`.
**What we changed.** `tools/wt` always branches from fresh `origin/main`; `tools/task claim` refuses a task whose dependencies are still open.
**Rubric lesson.** Practicality: the workflow has to match how the merge strategy really behaves.

## 4. Most AI findings were resolved without a word  (all day, 19 PRs)
**What happened.** 44 of 74 Greptile threads (59%) were resolved with no reply. For those we cannot say whether the finding was real, a hallucination, or ignored.
**Why.** Resolving a thread was enough to satisfy the ruleset, and nothing asked for a reason.
**What we changed.** AGENTS.md §3 rule 8: never resolve a thread without `Fixed in <sha>` or `Not changing: <reason>`. `tools/metrics` reports disposition coverage, and the PR header shows the silent threads.
**Rubric lesson.** Evidence: what the AI found and what was done about it has to be written down to count.

## 5. The iOS app target is never compiled in CI, and a contract drift slipped through  (PR #70 onwards)
**What happened.** `ios/test.sh` runs Python proxy tests and CI builds the `MetaLabCore` package, but the app target (`ios/MetaLab/*.swift`, about 1.3k lines with every DAT, audio and WebSocket path) is never compiled. The Swift error decoder rejects `request_id: null`, which the schema allows and the backend sends.
**Why.** Compiling the app needs Xcode on macOS, which our CI runner does not have.
**What we changed.** @maksymmatviievskyi is testing the Swift decoder against the contract fixtures. The gap is stated in the concept card's "not checked" list.
**Rubric lesson.** Clarity: state what was not checked, and why, instead of implying full coverage.

## 6. The same escalation was posted twice within a minute  (08:47 #64, 09:12 #68, 09:57 #73)
**What happened.** "needs human" lines appeared twice within one minute on three PRs.
**Why.** Two workflows (`claude-fix` and the sweeper) escalated the same state independently.
**What we changed.** `claude-fix` checks the PR and the board for the same line before posting (`grep -qF … <<<"$board_seen"`).
**Rubric lesson.** Practicality: a noisy escalation channel trains people to ignore it.

## 7. A PR its author marked "no auto-merge" merged itself  (13:45, PR #100)
**What happened.** A teammate's agent opened #100 (review plans, docs only) and wrote "no auto-merge" in the description. `claude-fix` enabled auto-merge as soon as it had no unresolved threads, and `github-actions` merged it. The lead had decided not to publish that text, so it had to be removed by a new PR (#115).
**Why.** The author's intent was written in prose, which no workflow reads. `claude-fix` enables auto-merge on every PR whose threads are resolved.
**What we changed.** One merge rule (AGENTS.md §3 rule 9), and `claude-fix` skips auto-merge on protected-path PRs (#120). This guard does not cover the incident itself: a docs-only PR is not on a protected path, so an author's "no auto-merge" in prose is still not honored. Holding such a PR remains unsupported (keep it as a draft, which Greptile and auto-merge skip, until it is ready).
**Rubric lesson.** Clarity: a rule that lives only in prose is not enforced.

## 8. A hosted reviewer reported "pass" while reviewing nothing  (before the event; partly mitigated, not fixed)
**What happened.** During preparation, a hosted reviewer's credits ran out and it kept reporting success without reviewing anything.
**Why.** A missing or exhausted credential was treated as "nothing to report".
**What we changed.** `claude-fix.yml` fails loudly when `CLAUDE_CODE_OAUTH_TOKEN` or `BOT_PUSH_TOKEN` is missing, so the fixer's check turns red instead of green. This does not cover the hosted reviewer: nothing yet detects exhausted reviewer credits or a review that never ran. That part is still open.
**Rubric lesson.** Measurement: a green check must mean the check ran.

## 9. The fixer loop has a hard cap  (already fixed; PRs #70 and #75)
**What happened.** #70 (iOS, 7 threads) and #75 (image generation, 11 threads) needed 2 to 4 bot fix commits each. #75 came within one commit of the cap.
**Why.** An AI fixer answering an AI reviewer can loop.
**What we changed.** `claude-fix` counts its own `fix: address greptile review` commits and stops at 5 with `needs human: fix loop cap hit`.
**Rubric lesson.** Practicality: bounded autonomy needs a bound that a human sees when it is hit.

## 10. The fixer never rebases  (already fixed)
**What happened.** Early on, history rewrites on pushed branches broke teammates' local branches.
**Why.** Rebasing a branch that a bot and a human both push to discards the other side's commits.
**What we changed.** The fixer prompt and AGENTS.md §3 rule 4: plain `git pull --no-rebase`, merge `origin/main`, never rebase or force-push a pushed branch.
**Rubric lesson.** Practicality: the rule the bot follows and the rule the humans follow must be the same rule.

## 11. The merge rule was written five different ways  (found 13:35)
**What happened.** AGENTS.md allowed agents to run `gh pr merge --auto`, the Codex safety gate said `gh pr merge` was prohibited, a `claude-fix.yml` comment said `.claude/settings.json` denies it (it does not), the strategy doc pitched a "hard rule", and AGENTS.md said `.github` changes need a human merge while 30 PRs were merged by `github-actions`.
**Why.** Each file was written at a different time, and none pointed to the others.
**What we changed.** The rule is stated once, as AGENTS.md §3 rule 9, and the other places point to it. The safety gate and the workflow comment are aligned in #120.
**Rubric lesson.** Clarity: one rule, in one place, matching what the code enforces.

## 12. The fixer edited another owner's file and broke its test  (about 14:00, PR #104)
**What happened.** On #104 (backend core), `claude-fix` answered a review thread by editing `backend/ai/image.py`, which belongs to another owner, and broke that owner's test. The PR author reverted the edit and filed a task for the owner (#108) with the diff as a starting point.
**Why.** The fixer may edit any file the review mentions; nothing checks the owner table.
**What we changed.** The PR author's revert and handoff are the pattern we follow. The `claude-fix` path guard (#120) refuses changes to protected paths before it pushes.
**Rubric lesson.** Practicality: a named human owns each folder, and the AI should hand off rather than cross that line.
