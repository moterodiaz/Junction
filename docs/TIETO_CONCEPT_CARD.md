# Tieto concept card: bounded autonomy, tiered by risk

How a four-person team let AI agents write, review, fix and merge most of the code for MetaLab in one weekend, what a named human still signs off on, and how we measure whether that trust was earned. Every number below comes from this repository's GitHub data (measured 2026-11-14 14:15 UTC); `tools/metrics` regenerates them.

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
- **Escape rate:** reverts or hotfix PRs within 24 h ÷ merged PRs.
- **Fixer effort:** `claude-fix` commits ÷ PRs.

| Metric (product PRs, #67 onwards) | Value at 2026-11-14 14:15 UTC |
|---|---|
| PRs opened / merged / open | 29 / 27 / 2 |
| Time to merge | median 5.7 min, mean 15.9 min, max 89 min |
| Greptile review threads | 74 on 19 PRs, all resolved |
| Threads with a written reply | 30 (28 "Fixed in <sha>", 0 rejected) |
| Threads resolved with no reply | 44 (59%) |
| AI finding acceptance rate (threads with a disposition) | 28 of 28 |
| `claude-fix` commits | 24 on 15 PRs (measured 12:40 UTC); cap of 5 never hit |
| `ci` runs succeeded | 196 of the last 200 |
| Reverts | 0 |
| Human approvals on merged PRs (all PRs) | 0 of 60 |

The two numbers we commit to watching: disposition coverage must reach 100% for new PRs (rule 8), and the escape rate must not rise while time to merge stays low.

## 6. Limits

- Greptile's recall is unknown: we can count what it found, not what it missed.
- 0 reverts in one day of building proves little.
- The acceptance rate (28 of 28) looks perfect only because no finding was ever rejected in writing; with 44 silent threads it is not yet a real measure.
- The safety net was broken for most of the day: the sweeper's retry step failed 170 of its last 200 runs and nobody was alerted (lessons log entry 2).
- The protected-path rule needs the workflow to enforce it. Until the `claude-fix` path guard (#120) merges, it is a team rule that a bot can break, as PR #100 showed (lessons log entry 7).
- The iOS tests are proxies, and the app target is never compiled in CI.
- The pipeline has run on one repository, for one weekend, with four people.

## 7. Walkthrough

The live walkthrough uses one agent-written PR with its self-explaining header (Verified by AI / Refused or escalated to a named human / Human sign-off, plus metrics). Until the header workflow is live, the candidate is PR #86 (REQ-ERR-01, REQ-PRIV-01): every stage failure maps to a contract error code and a request writes nothing to disk. It had 3 Greptile threads, 1 fixer commit, and contract and privacy tests.
