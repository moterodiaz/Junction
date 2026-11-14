# Trust pipeline: where trust comes from, measured

Evidence for the Tieto "Earned Trust in AI Code" entry (REQ-PROC-02, task #186). Every number below is output from a command in this repo, with its time window and denominator. No time savings are claimed: we did not measure a baseline without the pipeline.

Measured on 2026-11-14 at 17:30 UTC against `main` at `85238b9`, covering PRs #67 onwards (#67 is the first product PR).

## 1. The rule in one paragraph

Every agent-written PR names a requirement id and a human owner (the CODEOWNERS owner of the files it changes). Greptile reviews it; `claude-fix` fixes or rejects each finding with a written reason; `ci` runs. **Trust is earned per area:** while an area has no open escape, its PRs may auto-merge. **Trust is withdrawn after an escape:** when a defect that reached `main` past review is recorded (an issue labelled `escape`, naming the PR that introduced it with an `Introduced-by: #N` line), every PR touching that area is held until the area's owner, or the lead, approves its head commit. Trust is earned back when the escape closes with its fix.

## 2. How the hold is enforced

| Piece | What it does |
|---|---|
| `tools/metrics --gate <PR>` | Works out the PR's areas from its files, the open escapes per area, and who approved the **head commit**. Exit 0 passes; exit 3 holds, naming the escape and who must approve. |
| `.github/workflows/trust.yml` (handed to the lead on #186; agent tokens cannot push workflows) | Posts the commit status `trust` on the PR's head when the PR changes, a review is submitted or dismissed, an escape issue changes, and every 30 minutes as a backstop. A `gh` failure posts `error`, so the PR stays held. |
| main-protect ruleset | Lists `trust` as a required check, so GitHub itself refuses the merge, auto-merge from `claude-fix` included. **Pending:** the lead adds it; agents cannot change rulesets. |

Choices, with the reason for each:
- **Approval of the head commit only.** An approval does not cover code pushed after it.
- **The lead may approve for an owner.** Agents push from their human's account, and GitHub refuses self-approval, so an owner cannot approve their own agent's PR.
- **A later "changes requested" withdraws an approval.** A comment-only review changes nothing.
- **The fix for an escape is held too.** It is the change most worth a human look.

The offline tests (`tools/tests/trust_gate.test.sh`; the `ci` step that runs them is in the same handoff) drive the gate through a fake `gh`:

```
earned: no open escape
ok   #50 exit 0: trust earned in @Ahm3d-KA
withdrawn: open escape #140 was introduced by #40 in @Ahm3d-KA's area
ok   #50 exit 3: held: @Ahm3d-KA trust withdrawn (#140); needs @Ahm3d-KA or @moterodiaz to approve the head commit
ok   #51 exit 0: trust earned in @Marcus228
ok   #50 exit 3: held: ... (approval of an older commit)
ok   #50 exit 3: held: ... (approval by a different area's owner)
ok   #50 exit 0: owner-approved head commit for withdrawn area(s) @Ahm3d-KA
ok   #50 exit 0: owner-approved head commit for withdrawn area(s) @Ahm3d-KA   (the lead)
ok   #50 exit 3: held: ... (the lead's later change request)
re-earned: escape #140 closed with its fix
ok   #50 exit 0: trust earned in @Ahm3d-KA
gh failure fails closed (exit other than 0 or 3)
ok   exit 1
trust gate tests: OK
```

The test is not vacuous: letting any approver release the hold makes it fail (`FAIL #50: want exit 3 with 'held:', got exit 0`). Against the live repo, `tools/metrics --gate 188` printed `trust earned in @moterodiaz` (exit 0), because all 9 escapes are closed.

## 3. One change, end to end: PR #174 (REQ-WS-01)

REQ-WS-01: *`invoke`, `status`, `card` and `error` messages validate against `contracts/ws-messages.schema.json`.*

1. **Escape.** A two-reviewer audit of merged backend code (2026-11-14, ~13:20) found that a model answer with a blank title or a malformed source URL produced a card that failed the schema, and a blank title crashed the request. Recorded as escape #112, `Introduced-by: #68`.
2. **Agent change.** PR #174, opened 15:19, merged 15:26 (auto-merge, enabled from the owner's account): `contract_card()` fills blank text with plain defaults and drops sources without a valid https URL; `Card`, `Book` and `Source` mirror the schema. Owner: @Ahm3d-KA.
3. **What the AI found.** Greptile raised two P1 findings:
   - *"One source blocks the card"*: `_https()` accepted `"https://example.com\n"`, because Python's `$` matches before a final newline. **Fixed in ad2a0b1**, with a test that failed with `ValidationError` before the fix.
   - *"Blank captions still fail"*: `parse_reasoning_json()` raises before the fallback runs.
4. **What the AI refused to decide, and why.**
   - *"Not changing in this PR: the blank-caption check is in `backend/ai/reasoning.py` (Marcus's area, no handoff)."* The agent filed #175 with the exact fix and an acceptance test. @Marcus228's PR #178 fixed it at 16:05.
   - The PR body records a second refusal: sanitizing `image_url` broke `contracts/test_conformance.py::DriftTests::test_non_https_image_url_is_reported`, a merged test in the lead's contracts area. *"That test is merged and in the contracts area, so this PR yields."*
5. **How a named human accepts without a full read.** The trust header workflow landed at 15:48, after this PR merged, so #174 never had a header comment. `tools/metrics --pr 174` renders it now:
   - `REQ-WS-01` with its text, named owners @Ahm3d-KA @moterodiaz;
   - `ci` success and `Greptile Review` success, both linked;
   - review threads: 2 (fixed 1, rejected 1, escalated 0, silent 0, open 0);
   - two "needs human" escalations: `claude-fix` "could not resolve 2 thread(s)", so the owner's agent answered both threads itself;
   - an empty sign-off block for the owner: checked, not checked and why, residual risk accepted.

   The owner reads the two findings, the refusal and the test names, not the whole diff. With this PR's gate, #174 would also have waited for an approval, because escape #112 was open until #174's own merge closed it (section 5).

## 4. Measured track record

`tools/metrics` (repo-wide, PRs #67 onwards):

| Metric | Value |
|---|---|
| PRs opened / merged | 48 / 46 |
| Time to merge, median / mean (min) | 5.5 / 15.3 |
| AI review threads | 118 |
| Fixed / rejected with a reason / escalated | 81 / 1 / 0 |
| Resolved in silence / still open | 33 / 3 |
| Disposition coverage (%) | 69.5 |
| AI finding acceptance (%) | 98.8 |
| PRs routed to a human (%) | 45.8 |
| Reverts | 0 |
| Escapes recorded / still open | 9 / 0 |
| Escape rate: merged PRs that let a defect reach `main` (%) | 15.2 (7 of 46) |
| REQ id coverage (%) | 72.9 |
| `ci` runs succeeded, last 100 (%) | 100.0 |

`tools/metrics --areas` (a PR counts for every area whose files it changes):

| Area (owner) | PRs merged | Median TTM (min) | AI threads | Fixed | Rejected | Silent | Escapes | Escape rate (%) | Trust |
|---|---|---|---|---|---|---|---|---|---|
| @Ahm3d-KA | 25 | 5.7 | 60 | 46 | 1 | 13 | 9 | 28.0 | earned |
| @Marcus228 | 9 | 17.7 | 45 | 25 | 0 | 20 | 1 | 11.1 | earned |
| @maksymmatviievskyi | 1 | 12.0 | 7 | 0 | 0 | 7 | 0 | 0.0 | earned |
| @moterodiaz | 17 | 7.3 | 50 | 37 | 0 | 13 | 1 | 5.9 | earned |

How to read the tables:
- **The highest escape rate belongs to the most-audited area, not the worst code.** All 9 escapes are in backend core (2 of them also in another area), the area whose owner ran a two-reviewer audit and live deploy checks. An area nobody audits shows 0 escapes. The rate measures what was found, not what exists.
- **33 threads were resolved in silence.** Disposition coverage is 69.5%, not 100%. Those are changes the pipeline cannot vouch for; the per-area table shows where they are.

## 5. Replay: what the gate would have held

A retroactive replay over the same PRs found:
- the escape issues, with the times they were opened and closed;
- the areas of the PRs each escape names;
- every merged PR that touched one of those areas while the escape was open.

| Result | Value |
|---|---|
| Merged PRs that would have needed owner or lead approval | **10 of 46** (21.7%) |
| Of those, in backend core | 9 (#78, #98, #104, #106, #107, #171, #172, #173, #174) |
| Of those, in backend AI | 1 (#105: escape #102's introducing PR touched both areas) |
| Of those, the fix that closed one of the open escapes | 9 (all but #105) |

**What this shows:** escapes here lived 4 to 82 minutes, from filing to fix, so the gate would mostly have held the fixes themselves. That is where we want a human: a fix for a defect that already got past review. The one unrelated PR it would have held, #105, changed backend AI while escape #102, introduced by a PR that touched both areas, was open.

**Caveat:** the `escape` label and the `Introduced-by` lines were added at ~16:30, after the fact. The replay treats each issue as an escape from the moment it was filed.

## 6. Limits: what this does not prove

- **The hold is not enforced until the lead commits `trust.yml` and adds `trust` to main-protect's required checks.** Until then it is a red status that a merge can ignore. *Owner: @moterodiaz.*
- **"Human approval" rests on a team rule, not on cryptography.** Agents push from their human's account, and an agent could in principle approve another owner's PR. AGENTS.md §3 rule 9 forbids agents from approving; nothing technical stops them.
- **Escapes are only as complete as the audits.** An escape is a defect someone found. There is no estimate of defects nobody has found.
- **The cost of a hold was not measured.** That cost is the owner's approval latency. The replay counts the holds, not the minutes they would have taken.
- **No baseline.** We have no comparable run without the pipeline, so we claim no time saved.

## Reproduce

```
tools/metrics                      # section 4, repo-wide
tools/metrics --areas              # section 4, per area
tools/metrics --gate <PR>          # the trust status for one PR
tools/metrics --selftest           # offline unit checks
tools/tests/trust_gate.test.sh     # section 2, offline gate tests
gh issue list --label escape --state all
```
