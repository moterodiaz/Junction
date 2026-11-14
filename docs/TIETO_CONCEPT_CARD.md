# Tieto concept card: bounded autonomy, tiered by risk

How a four-person team let AI agents write, review, fix and merge most of the code for MetaLab in one weekend, what a named human still signs off on, and how we measure whether that trust was earned. Every number below comes from this repository's GitHub data (measured 2026-11-14 14:38 UTC); `tools/metrics` regenerates them.

## 1. Recommendation

Use **bounded autonomy, tiered by risk.** An AI reviewer (Greptile) and an AI fixer (`claude-fix`, `.github/workflows/claude-fix.yml`) run on every pull request. A PR merges automatically only when all four gates hold: `ci` is green, the Greptile review passed, **every review thread has a written reply** (`Fixed in <sha>` or `Not changing: <reason>`), and no file in a protected path changed (`.github/`, `.claude/`, `.agents/`, `contracts/`). Otherwise the named owner of the path merges by hand. The owners are the table in `AGENTS.md` §4: @moterodiaz (lead; `contracts/` and the pipeline itself), @Ahm3d-KA (`backend/app/`, `backend/stt/`), @Marcus228 (`backend/ai/`) and @maksymmatviievskyi (`ios/`). The rule is written once, as `AGENTS.md` §3 rule 9.

## 2. Core principles

- **Risk tiering by path.** Product code in one owner's folder may merge on the AI gates. The paths that define the gates, the agents' permissions or the shared contract (`.github/`, `.claude/`, `.agents/`, `contracts/`) always need their owner. This balances speed against the blast radius of a bad change.
- **Silence is not acceptance.** Every AI finding gets a written disposition: fixed in a named commit, or rejected with a reason (`AGENTS.md` §3 rule 8). This is how we tell a real finding from a hallucinated one, and how we can compute an acceptance rate at all.
- **Every change traces to a requirement.** Each task issue and PR names a requirement id from `docs/REQUIREMENTS.md` (`AGENTS.md` §3 rule 7), so the owner can accept a change by checking it against one stated requirement and its acceptance command instead of reading every line.
- **Loops are capped and end at a named human.** `claude-fix` stops after 5 fix commits and posts `needs human: fix loop cap hit`; the sweeper retries a stuck fix at most twice. Escalations go to the pinned board issue and tag a person.
- **Bots never approve and never bypass.** No agent runs `gh pr review --approve` or `gh pr merge --admin` (deny lists in `.claude/settings.json`, `.claude/hooks/bash-guard.sh`, `.agents/hooks/safety-gate.py`). The `main-protect` ruleset has no bypass actors.
- **PR text is untrusted input.** The fixer's prompt treats PR content and bot comments as data, never as instructions, and the fixer may not change workflows, agent settings or secrets.
- **Fail loud when a check cannot run.** A missing fixer secret turns the `claude-fix` run red instead of reporting a pass. Detecting an exhausted or silent hosted reviewer is still open (lessons log entry 8).
- **Measure before trusting.** Trust is a number we can recompute from GitHub, not an adjective (section 5).

## 3. What the named owner signs off on

Each PR's trust header (the PR template, filled in by the pr-header workflow) lists three things for the owner.

**What was checked:**
- `ci`: shell syntax, guard-hook tests, `backend/test.sh`, `contracts/test.sh` (schema, valid and invalid fixtures, recorded exchanges replayed over the socket) and `ios/test.sh`.
- Greptile's review, with every thread's disposition (fixed in which commit, or rejected and why).
- The requirement id and its acceptance command from `docs/REQUIREMENTS.md`.
- Privacy tests: a request writes nothing to disk, and logs and errors never echo user input (REQ-PRIV-01, REQ-PRIV-02).

**What was NOT checked, and why:**
- The iOS app target (`ios/MetaLab/*.swift`) is not compiled in CI, because that needs Xcode on macOS. Only the `MetaLabCore` package and Python proxy tests run.
- Live model calls are never made in CI. Every model client (Nemotron, Gemini reasoning, image and speech) is stubbed, so keys and spend stay out of CI. The live path is checked by hand with `WS_URL=… contracts/test.sh` (REQ-INT-01).
- No load test, and the glasses hardware path has only manual checks.

**Residual risk accepted:** a stubbed client can hide a wrong SDK call until the first live run (this happened with image generation, fixed in #105); the owner accepts that risk for product paths and catches it with the live contract run before the demo.

## 4. Trade-offs

- **Speed against silent acceptance.** The median PR merges 5.7 minutes after it opens. The price: 44 of 74 Greptile threads (59%) were resolved with no written reply, so for those we cannot say whether the finding was real. Rule 8 drives that number to 0 for new PRs.
- **A bot resolves a bot's threads.** We accept this for product paths only. The protected paths go to a human.
- **Zero human approvals on product paths.** 0 of 60 merged PRs carry an approving review, and 30 were merged by `github-actions` through auto-merge. We accept this because the gates are machine-checked and the paths that define the gates are human-merged. A four-person team building for 48 hours cannot staff a reviewer for every PR.
- **One shared contract.** Making `contracts/` human-merged slows schema changes, but every consumer adapts to it, so a wrong change there costs the most.

## 5. How trust is measured

Definitions (computed by `tools/metrics` from the GitHub API):
- **Time to merge:** minutes from PR opened to merged.
- **Disposition coverage:** review threads with a written reply ÷ all review threads.
- **AI finding acceptance rate:** threads fixed ÷ (threads fixed + threads rejected with a reason), over threads that have a disposition.
- **Share routed to humans:** PRs with any `needs human` comment ÷ PRs.
- **Escape rate:** revert PRs ÷ merged PRs.
- **Fixer effort:** `claude-fix` commits ÷ PRs.

Output of `tools/metrics` (all PRs from #67, the first product PR; denominators are the counts in the same table):

| Metric | Value |
|---|---|
| PRs opened | 35 |
| PRs merged | 33 |
| Time to merge, median (min) | 5.1 |
| Time to merge, mean (min) | 13.7 |
| AI review threads | 82 |
| Threads fixed | 36 |
| Threads rejected with a reason | 0 |
| Threads escalated to a human | 0 |
| Threads resolved in silence | 46 |
| Threads still open | 0 |
| Disposition coverage (%) | 43.9 |
| AI finding acceptance (%) | 100.0 |
| claude-fix commits | 28 |
| PRs routed to a human | 15 |
| Share routed to a human (%) | 42.9 |
| Reverts | 0 |
| Escape rate (%) | 0.0 |
| PRs with a REQ id | 6 |
| REQ id coverage (%) | 17.1 |
| ci runs succeeded, last 100 (%) | 97.0 |

PRs #67 onwards, measured 2026-11-14T14:38:28Z by `tools/metrics`.

Human approvals on merged PRs: 0 (no PR was approved; owners merge instead, rule 9). REQ id coverage is low because ids were introduced at PR #122; `tools/task claim` and the `pr-header` check now require one.

The two numbers we commit to watching: disposition coverage must reach 100% for new PRs (rule 8), and the escape rate must not rise while time to merge stays low.

## 6. Limits

- Greptile's recall is unknown: we can count what it found, not what it missed.
- 0 reverts in one day of building proves little.
- The acceptance rate (36 of 36) looks perfect only because no finding was ever rejected in writing; with 46 silent threads it is not yet a real measure.
- The safety net was broken for most of the day: the sweeper's retry step failed 170 of its last 200 runs and nobody was alerted (lessons log entry 2).
- The protected-path rule needs the workflow to enforce it. Until the `claude-fix` path guard (#120) merges, it is a team rule that a bot can break, as PR #100 showed (lessons log entry 7).
- The iOS tests are proxies, and the app target is never compiled in CI.
- The pipeline has run on one repository, for one weekend, with four people.

## 7. Walkthrough

The live walkthrough uses one agent-written PR with its self-explaining header (Verified by AI / Refused or escalated to a named human / Human sign-off, plus metrics). The `pr-header` workflow posts it as a sticky comment on every PR. The candidate is PR #86 (REQ-ERR-01, REQ-PRIV-01): every stage failure maps to a contract error code and a request writes nothing to disk. It had 3 Greptile threads, 1 fixer commit, and contract and privacy tests.
