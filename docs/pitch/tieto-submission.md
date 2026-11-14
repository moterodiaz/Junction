# MetaLab: Tieto submission text (draft)

Draft for Tieto's "Earned Trust in AI Code" track (#207, LANE-A5). Submitting stays with the lead (#145). Tags like **[E18]** point to `docs/pitch/SOURCES.md`. Re-run `tools/metrics` before submitting, and update E18 if the numbers move.

## One line

Four people let AI agents write, review, fix and merge most of a real product in a weekend, and GitHub lets the AI merge only where it has earned it.

## Short description (~70 words)

We built MetaLab with AI agents writing most of the code. To trust what they shipped, every change names its requirement and a human owner. Every AI review finding is answered with "fixed" or "not changing, because…". And trust is earned per area: when a defect slips through, GitHub blocks that area's PRs until its owner approves. We measured all of it, live from the repo **[E18, E19]**.

## Long description (~250 words)

Most "AI code review" stories stop at "the bot left comments". We wanted to know when a person can put their name on code they didn't read line by line, and when they can't.

**Where trust comes from.**
- **Every change names its requirement and its owner.** Each PR cites a requirement id (77.2% of PRs do, and a check flags the rest) and has a named owner from CODEOWNERS **[E18]**.
- **Every finding gets an answer.** An AI reviewer (Greptile) reviews each PR, and the fixer bot or the owner's agent answers each finding with "Fixed in <commit>" or "Not changing: <reason>". Of 131 threads, 93 were fixed and 1 was rejected with a reason **[E18]**. 33 were resolved in silence **[E18]**.
- **A trust header on every PR** shows what the AI verified, what it refused to decide, and a sign-off box for the owner **[E19]**.

**Trust is earned per area, and taken back.** When a defect reaches `main` past review, we record it as an "escape" against the PR that introduced it. A required `trust` check then blocks every PR in that area until the owner, or the lead, approves the exact head commit. In a live drill, a test escape turned a ready PR from mergeable to blocked within 15 seconds, and back again when it closed **[E19]**.

**One real change.** PR #174 (REQ-WS-01): the AI found a newline bug and fixed it with a test that failed first. It refused a second fix because that code belonged to a teammate, and filed #175 instead, which the teammate fixed in #178. The owner read two findings and two refusals, not the diff **[E19]**.

**Honest numbers:** 54 PRs merged, a median of 6.7 minutes to merge, 0 reverts, and 13.0% of merged PRs let a defect through **[E18]**. That rate measures what our audits found, not every defect that exists.

## What we recommend

Let AI merge only what it can show evidence for, and only in areas that haven't let a defect through. Everything else goes to a named owner. Bots never approve.

## Evidence for judges

| Claim | Where to check |
|---|---|
| All numbers | `tools/metrics`, `tools/metrics --areas` (regenerated live from GitHub) **[E18]** |
| The gate, its tests, the live drill, lessons | `docs/evidence/TRUST-PIPELINE.md`; `tools/metrics --gate <PR>`; `tools/tests/trust_gate.test.sh` **[E19]** |
| Concept card and lessons log | `docs/TIETO_CONCEPT_CARD.md`, `docs/TIETO_LESSONS_LOG.md` |
| One change end to end | PR #174, issue #175, PR #178 **[E19]** |

## Limits (say them before a judge asks)

- **We see the reviewer's findings, not what it missed.** Our one audit found escaped defects in a single area **[E19]**.
- **"Bots never approve" is a team rule, not cryptography.** Agents push from our own accounts **[E19]**.
- **No baseline:** one repo, one weekend, four people. We claim no time saved **[E19]**.
