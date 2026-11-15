# Trust evidence: one real PR, measured (TRUST-GATE, #135)

Requirement: REQ-PROC-01. PRD §12.9. Owner: Mateo (@moterodiaz, lead).

This file ties the Tieto "Earned Trust in AI Code" material together for the gate: one real requirement-linked PR walked through end to end, the repo's measured track record, which backend, Swift and model checks actually ran, and who is accountable for what. The enforcement mechanism (the `trust` status, the escape rule and its drill) is in `docs/evidence/TRUST-PIPELINE.md` and is not repeated here. The rubric story is `docs/TIETO_CONCEPT_CARD.md`; incidents are `docs/TIETO_LESSONS_LOG.md`.

**No time savings are claimed.** We never ran the same work without the pipeline, so there is no baseline to compare against.

Measured 2026-11-14 at 22:54 UTC on `main` at `418a1eb`, covering PRs #67 onwards (#67 is the first product PR).

## 1. Implemented, validated, not validated

| Claim | Status | Evidence |
|---|---|---|
| AI review (Greptile) and AI fixer (`claude-fix`, capped at 5 commits) on every PR | Implemented and running | 180 review threads and 54 `claude-fix` commits over 78 PRs (section 3) |
| Written disposition for every thread (AGENTS.md §3 rule 8) | Implemented, **not fully met** | 44 of 180 threads (24.4%) were resolved in silence, most before the rule |
| Every PR names a requirement id | Implemented, **not fully met** | 65 of 78 PRs (83.3%); ids started at PR #122 |
| Trust earned per area, withdrawn by an open escape, enforced by GitHub | Implemented and validated by a live drill | `TRUST-PIPELINE.md` §2: #191 went CLEAN → BLOCKED → CLEAN at 18:20 UTC |
| Protected paths need their owner's merge | Implemented | `claude-fix` path guard (#120); rule 9 |
| Named human approval on product PRs | **Not used** | 0 of 77 merged PRs carry an approving review; owners merge instead (rule 9) |
| End-to-end product on the live deployment | **Not validated** | Spoken output (`audio_url`) still fails live; no hardware round trip (section 4) |

## 2. Walkthrough: PR #218 (REQ-SRC-01, REQ-BASE-01)

REQ-SRC-01: *Hamlet explanations cite act, scene and line from the loaded public-domain text; other books are marked "no source text".*

1. **The defect, found live.** The first live run (`docs/evidence/base-live.md`) cited Hamlet Act 1, Scene 1 for a page from Scene 2, with generic sources. After #209 wired the passage matcher into the pipeline, a card for a page with no verified passage still kept the model's guessed act, scene and line. Tracked as #129.
2. **The agent's change.** PR [#218](https://github.com/moterodiaz/Junction/pull/218), opened 21:01:49, merged 21:13:58 (12.2 min) by @moterodiaz. Files: `backend/app/pipeline.py`, `backend/tests/test_pipeline.py`. With no verified passage, the card's location becomes `No source text` and its title becomes the book title. `backend/app/` is @Ahm3d-KA's area; he agreed to the edit on the board first.
3. **How the change was tested, independently of the code.** The new `PipelineCitationReferenceTest` runs the real matcher and parser against a fake model that guesses Hamlet coordinates and an invented URL for every page. Seven Hamlet passages are checked against the standard act and scene division, not against our own corpus. Three pages from other books (Moby-Dick, Pride and Prejudice, Macbeth) must get `sources == []` and `No source text`. A mutation check: without the `pipeline.py` change, those three cards came out as `Hamlet, Act 4, Scene 7, line 1` and the test failed.
4. **What the AI found.** Greptile raised two P2 findings at 21:03:57:
   - *"Direct runs skip new tests"*: the new class sat below `unittest.main()`, so running the file directly would skip it.
   - *"Citation tests call Gemini"*: `draw()` and `speak()` stayed live under a dummy key, so a developer with `IMAGE_BASE_URL` set could call real image and speech APIs from a unit test.

   `claude-fix` fixed both in `274a8f0` at 21:04:37 (one of its 5-commit cap).
5. **What the AI did not decide.** `claude-fix` could not mark the threads resolved and escalated at 21:05:39: *"@moterodiaz needs human: claude-fix could not resolve 2 thread(s)"*. The lead's agent checked the bot's diff and replied `Fixed in 274a8f0.` on both threads at 21:06:42, so both have a written disposition. The PR body also routed three follow-ups to @Marcus228 instead of editing his folder (`backend/ai/`): the session still stores the guessed location, extra model sources pass unverified on grounded cards, and lines under 5 words never ground.
6. **The header the owner reads.** `tools/metrics --pr 218` renders: `REQ-BASE-01` and `REQ-SRC-01` with their text; risk tier "auto-merge allowed" (no protected path, no open escape); named owners @Ahm3d-KA @moterodiaz; `ci` success and `Greptile Review` success, both linked; review threads 2 (fixed 2, rejected 0, escalated 0, silent 0, open 0); `claude-fix` commits 1 of 5; the escalation above.
7. **Validated after merge, on the live deployment.** After the v5 redeploy (`5d1a6ee`), the strict live check got `Hamlet` / `William Shakespeare` / `Act 1, Scene 2, lines 135-138` with the Gutenberg #1524 source, for typed and spoken requests. The expected location was found by reading `backend/ai/data/plays/hamlet.json` directly, not through the matcher. A Moby-Dick page got `sources: []` and `No source text`.
8. **What the merge did not cover.** The same Moby-Dick card still says `Hamlet` as its book title, because a new session starts with Hamlet. That is a residual defect in @Marcus228's area, filed as #231. It was found by the live probe, not by the review.

### Lead sign-off for #218 (@moterodiaz; recorded by the lead's agent under his authorization)

- **Checked:** the requirement text; both Greptile findings and the bot's fix diff; the independent reference test and its mutation check; the live citation on v5 and v6.
- **Not checked, and why:** display on the glasses and audible playback (needs hardware, #140); the three `backend/ai/` follow-ups (Marcus's area).
- **Residual risk accepted:** an unknown book's card is titled Hamlet until #231 lands; it carries no invented citation.

## 3. Measured track record

`tools/metrics`, PRs #67 onwards, measured 2026-11-14T22:54:06Z. Each rate's denominator is in the same table.

| Metric | Value |
|---|---|
| PRs opened / merged | 78 / 77 |
| Time to merge, median / mean (min) | 8.7 / 16.0 |
| AI review threads | 180 |
| Fixed / rejected with a reason / escalated | 135 / 1 / 0 |
| Resolved in silence / still open | 44 / 0 |
| Disposition coverage (%) | 75.6 (136 of 180) |
| AI finding acceptance (%) | 99.3 (135 of 136 with a disposition) |
| `claude-fix` commits | 54 |
| PRs routed to a human (any `needs human`) | 32 of 78 (41.0%) |
| Reverts | 0 |
| Escapes recorded / still open | 9 / 0 |
| Escape rate: merged PRs that let a defect reach `main` (%) | 9.1 (7 of 77) |
| REQ id coverage (%) | 83.3 (65 of 78) |
| `ci` runs succeeded, last 100 (%) | 99.0 |

Merges, from `gh pr list --state merged` for the same 77 PRs: 25 by `github-actions` (auto-merge), 33 by @moterodiaz, 14 by @Ahm3d-KA, 4 by @Marcus228, 1 by @maksymmatviievskyi. 0 carry an approving review.

`tools/metrics --areas` (a PR counts for every area whose files it changes):

| Area (owner) | PRs merged | Median TTM (min) | AI threads | Fixed | Rejected | Silent | Escapes | Escape rate (%) | Trust |
|---|---|---|---|---|---|---|---|---|---|
| @Ahm3d-KA (backend core) | 35 | 10.2 | 96 | 73 | 1 | 22 | 9 | 20.0 | earned |
| @Marcus228 (backend AI) | 15 | 13.7 | 65 | 43 | 0 | 22 | 1 | 6.7 | earned |
| @maksymmatviievskyi (iOS) | 4 | 10.2 | 16 | 2 | 0 | 14 | 0 | 0.0 | earned |
| @moterodiaz (contracts, docs, pipeline) | 35 | 10.5 | 76 | 61 | 0 | 15 | 1 | 2.9 | earned |

How to read it:
- **Since the 17:30 snapshot in `TRUST-PIPELINE.md`** (48 PRs), 30 more PRs added 62 threads with 54 more fixed and 11 more silent. Disposition coverage rose from 69.5% to 75.6%, and no new escape was recorded.
- **Escapes measure what audits found.** All 9 are in backend core, the area that had a two-reviewer audit and the live runs. iOS shows 0 escapes and 14 of 16 threads silent: that is a lack of evidence, not proof of quality.
- **The acceptance rate is not a precision measure.** With 1 rejection in 136 dispositions and 44 silent threads, it mostly shows that agents fix what Greptile reports.

## 4. Backend, Swift and model checks

Run for this file on 2026-11-14, macOS (darwin 25.5.0), `main` at `418a1eb` unless stated.

| Check | Command | Outcome |
|---|---|---|
| Backend, stubbed models | `python -m unittest discover -s . -t . -p 'test_*.py'` in `backend/` (existing venv) | 408 tests OK |
| Contracts, local | `contracts/test.sh` | 40 tests OK, 2 skipped (the live tests skip without `WS_URL`) |
| Swift package, local | `swift test --package-path ios/MetaLabCore` | **Did not run**: this machine has only Command Line Tools, whose Swift fails to link the package manifest. Not a test failure |
| Swift package and backend in CI | `ci` run 43649231648 on `53b35ff` (`ios/` and `backend/` unchanged since) | success: `MetaLabCore` 27 tests, 0 failures; iOS proxy 7 tests; backend 408 tests |
| iOS app target | `xcodebuild … CODE_SIGNING_ALLOWED=NO`, by @maksymmatviievskyi | BUILD SUCCEEDED at `6b3d353` only (reported by the iOS owner). Not built in CI, not installed on a phone |
| Live models, v5 `5d1a6ee` | strict `WS_URL` + `WS_SUCCESS_CASES` run of `contracts/test.sh` | 40 tests, 2 failures, both only `audio_url` null. Reported models: read `nemotron-3.5-super-vl`, reason `gemini-4-hydrogen`, image `gemini-nano-banana-2.1` (`docs/evidence/base-live.md`) |
| Live models, v6 `53b35ff` | the same strict run | Still 2 failures, only `audio_url` (typed 21.1 s, spoken 25.0 s). The new logging (#230) showed the cause: `400 INVALID_ARGUMENT`, the Gemini TTS model needs a different API shape. Fix pending under #226 |

Model attribution limit: `models.reason` is the requested model name, not one the provider confirmed.

## 5. Named accountability

| Who | Accountable for | Evidence file |
|---|---|---|
| @moterodiaz (lead) | `contracts/`, `.github/`, `.claude/`, `.agents/`, the trust pipeline, evidence docs, deploys, gate acceptance | this file, `TRUST-PIPELINE.md`, `base-live.md` |
| @Ahm3d-KA | `backend/app/`, `backend/stt/`: orchestration, speech, errors, privacy | `backend/README.md`, `backend/tests/` |
| @Marcus228 | `backend/ai/`: page reading, source text, reasoning, images | `docs/evidence/HOST.md`, `backend/tests/` |
| @maksymmatviievskyi | `ios/`: the app, DAT capture, the hardware round trip | `ios/README.md`, `ios/HARDWARE.md` |

These were the area owners during the build; all areas moved to @moterodiaz on 2026-11-15 (`AGENTS.md` §4).

Bots are never accountable: Greptile and `claude-fix` never approve, and each escalation names one of the four people above.

## 6. Limits

- **No baseline, no time-savings claim.** Time to merge is measured; what the same work would have taken without agents is not.
- **Greptile's recall is unknown.** 9 escapes passed review; defects nobody has found are not counted.
- **One weekend, one repo, four people.** Nothing here shows the pipeline works at another scale.
- **Human approval is a team rule.** Agents push from their human's account; nothing technical stops an agent approving another owner's PR (`TRUST-PIPELINE.md` §6).
- **Spoken output and hardware are unvalidated** (section 4). G0 (#141) stays open.

## Reproduce

```
tools/metrics                 # section 3, repo-wide
tools/metrics --areas         # section 3, per area
tools/metrics --pr 218        # section 2, the header
gh pr list --state merged --limit 200 --json number,mergedBy,reviews
gh api repos/moterodiaz/Junction/pulls/218/comments
```
