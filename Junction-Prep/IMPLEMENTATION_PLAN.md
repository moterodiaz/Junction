# MetaLab execution plan

**Documentation baseline:** task [#123](https://github.com/moterodiaz/Junction/issues/123). This plan specifies work; it does not implement features, install integrations, provision services, spend credits or authorize sponsor submissions.

Read [PRD §§1–14](metalab_prd.md), [the single requirement registry](../docs/REQUIREMENTS.md), and [challenge readiness](HACK_JUNCTION_CHALLENGES_AND_STRATEGY.md). No audit `plans/` folder or dropped plan 006 is recreated.

## Execution rules

- Exactly four canonical areas: A `backend-app` Ahmed @Ahm3d-KA; B `ios` Maksym @maksymmatviievskyi; C `backend-ai` Marcus @Marcus228; D `contracts` Mateo @moterodiaz. Lead-owned docs/CI/evidence tasks belong to D. One responsible owner and bounded file list per task; shared test/evidence files require sequential owner coordination.
- Existing issue assignees/claims stay unchanged. A named responsible owner below does not reassign an existing issue. Preserve #29 (Marcus loader), #81 (live integration) and #108–112. The lead-approved grounding/hardening pipeline handoff belongs to Ahmed.
- Reuse merged #24–28, #30–38, #69, #72, #76, #83, #89–91, #95, #97, #101–103 and image fix PR #105. Implementation present is not live verification. #29 stays open as found even though loader PR #80 exists; its owner resolves remaining evidence. #82 is conditional latency optimization, not a new gate or revived benchmark. Preserve #113 removal and #114 README/LICENSE work; no duplicate tasks.
- Retain task headings `Goal`, `PRD section`, `Requirement`, `Scope`, `Acceptance check`, `Depends on`, `Area`. Publish dependency issue numbers under `## Depends on`, not only prose or gate names. New tasks initially carry `task, blocked` and depend on #123 so they cannot run against unapproved docs. Existing tasks do not gain this dependency.
- New task responsible owners are named in bodies, not pre-assigned, so `tools/task claim` can work after readiness. Remove `blocked` only when documentation is accepted, all issue dependencies are closed, and explicit prerequisites are met. Gates remain open pending evidence and lead acceptance; implementation PRs must not use `Closes` on gate issues.
- Implementation can be reviewed behind off-by-default flags; activation requires its separate accepted gate. G0 → G1 → independent G2 VOICE/RESEARCH; optional Gemma/Cloudinary require G0 and their prerequisites; Stoa is after G1 and the voice/follow-up milestone. TRUST/BUILD/DEV/HOST evidence proceeds independently and never delays G0.
- A serializes `pipeline.py`: existing media/capacity/card fixes → grounding → hardening/lifecycle → intent → voice adapter → research. Optional Gemma/media/document edits require an explicit file-slot handoff, not completion of unrelated optional modules. File-lock dependencies are not claims that unrelated sponsor acceptance is required. If a predecessor is abandoned, the lead may explicitly release that file lock and update issue dependencies without waiving the successor's own activation prerequisites.
- Every task inherits PRD §§6–7 and §12.1: server-side credentials/calls, unchanged deadlines, bounded optional work, one terminal result, cancellation, no raw-media persistence/logging, session-only user text/cache/generated media, explicit-end cleanup and bounded abandonment expiry, isolation/error/disconnect tests. Provider handling is reviewed separately; conflicts block activation. No user content or secrets in durable evidence.
- `backend/test.sh`, `ios/test.sh`, `contracts/test.sh` are existing entry points, not proof of live behavior. All “new/planned/future” cases, evaluators and success scenarios below are **work to implement**, not checks already available or already run. Run real Swift/Xcode/hardware checks as specified; proxy/stub checks are insufficient.
- Handoffs: D contracts first; C adapter signatures and evaluation evidence to A; A provider budgets/lifecycle/auth readiness to B/D; B hardware/manual outcomes to D. Gate owner D records actual revision, commands, failures, metrics, cleared evidence and explicit @moterodiaz acceptance.

## Four-stream entry points

| Stream | Start / preserve | Then |
|---|---|---|
| A / Ahmed | BASE-A4/A5/A6/A7 (#109–112), approved BASE-A1 grounding [#129](https://github.com/moterodiaz/Junction/issues/129) | BASE-A2/A3 → INTENT-A1 → VOICE-A1 → RESEARCH-A1; EVID-A1 independent |
| B / Maksym | BASE-B1 contract decode [#134](https://github.com/moterodiaz/Junction/issues/134), BASE-B2 hardware [#140](https://github.com/moterodiaz/Junction/issues/140) | INTENT-B1 → VOICE-B1 / RESEARCH-B1; optional MEDIA/BLUEPRINT; EVID-B1 independent |
| C / Marcus | BASE-C0 [#29](https://github.com/moterodiaz/Junction/issues/29), BASE-C1 [#108](https://github.com/moterodiaz/Junction/issues/108); reuse image fix #105 | INTENT-C1 → RESEARCH-C1; gated GEMMA/MEDIA/BLUEPRINT adapters; EVID-C1 independent |
| D / Mateo | BASE-D1 lifecycle contract [#128](https://github.com/moterodiaz/Junction/issues/128); preserve BASE-D0 [#81](https://github.com/moterodiaz/Junction/issues/81) and TRUST-D0–D3 #117–121 | G0/G1 and module acceptance; prerequisites, TRUST/BUILD/DEV/HOST and release preparation |

## Module coverage

| Module | A | B | C | D |
|---|---|---|---|---|
| BASE | BASE-A1–A7 | BASE-B1/B2 | BASE-C0/C1; merged reasoning/image | BASE-D0/D1, BASE-G0 |
| INTENT | INTENT-A1 | INTENT-B1 | INTENT-C1 | INTENT-D1, INTENT-G1 |
| VOICE | VOICE-A1 | VOICE-B1 | Reuse speech_text, EVID-C1 | VOICE-G2 |
| RESEARCH | RESEARCH-A1 | RESEARCH-B1 | RESEARCH-C1 | RESEARCH-D1, RESEARCH-G2 |
| GEMMA | GEMMA-A1 | Reuse UI, EVID-B1 | GEMMA-C1 | GEMMA-G3 |
| MEDIA | MEDIA-A1 | MEDIA-B1 | MEDIA-C1 | MEDIA-D1, MEDIA-G3 |
| BLUEPRINT | BLUEPRINT-A1 | BLUEPRINT-B1 | BLUEPRINT-C1 | BLUEPRINT-D1, BLUEPRINT-G3 |
| TRUST | EVID-A1 | EVID-B1 | EVID-C1 | TRUST-D0–D3, TRUST-GATE; existing #119 preserved |
| BUILD | EVID-A1 | EVID-B1 | EVID-C1 | BUILD-D1 |
| DEV | EVID-A1 | EVID-B1 | EVID-C1 | DEV-D1 |
| HOST | EVID-A1 | EVID-B1 | EVID-C1 | HOST-D1, RELEASE-D1 |

## Task specifications

Published dependencies below use actual issue numbers; stable task IDs remain the coordination keys. All 41 new issues were created blocked; 11 existing issues were enriched without changing assignees or open/closed state. The documentation PR is [#127](https://github.com/moterodiaz/Junction/pull/127), pending review/acceptance. Each task is bounded to its named files; proposed new files are not present implementations. Existing issue text/acceptance remains authoritative for already claimed work, augmented by the coordinated metadata rather than silently reassigned.

<!-- task:BASE-C0 -->
## BASE-C0: Verify the existing Hamlet source loader

### Goal
Reuse the existing loader and merged #80. Preserve Marcus's assignee and in-progress state. Supply public-domain source/licence and real act/scene/line lookup evidence to Ahmed; do not reopen merged work.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-SRC-01

### Scope
backend/ai/source_loader.py; backend/ai/data/; backend/tests/test_source_loader.py

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Existing backend/test.sh plus independent Hamlet passage/location checks. Unknown books have no source rather than invented coordinates; provide loader handoff to BASE-A1.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
none

### Area
backend-ai

### GitHub issue
[#29](https://github.com/moterodiaz/Junction/issues/29)

<!-- task:BASE-C1 -->
## BASE-C1: Remove user content from AI errors and logs

### Goal
Keep existing #108: log safe exception types/codes, not provider messages, prompt fragments or model output. Preserve the image-client fix in #105.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-PRIV-02

### Scope
backend/ai/image.py; backend/ai/page_reader.py; backend/ai/reasoning.py; backend/tests/test_image.py and AI error tests

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new SECRET-bearing provider/model errors asserts no text reaches logs or public errors; image failure still yields the established optional-image fallback.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
none

### Area
backend-ai

### GitHub issue
[#108](https://github.com/moterodiaz/Junction/issues/108)

<!-- task:BASE-A4 -->
## BASE-A4: Make spoken clips session-owned and expiring

### Goal
Reuse #109: session-key clips, delete on explicit end and bounded abandonment expiry. Preserve sample-rate parsing, first usable inline part and shared client corrections.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-PRIV-03, REQ-TTS-01

### Scope
backend/stt/speak.py; backend/app/pipeline.py; backend/tests/test_speak.py and media tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with tests to add for session A/B isolation, end, expiry, error/disconnect cleanup and old URL non-retrievability. Hand cleanup hooks to BASE-A3; no new provider required.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
none

### Area
backend-app

### GitHub issue
[#109](https://github.com/moterodiaz/Junction/issues/109)

<!-- task:BASE-A5 -->
## BASE-A5: Handle speech capacity within the existing budget

### Goal
Reuse #110: wait for an STT slot within the stage budget or return an honest safe busy error. Serialize pipeline edits after clip ownership, without raising global deadlines.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-LAT-02, REQ-ERR-01

### Scope
backend/app/pipeline.py; backend/tests/test_stt.py and pipeline capacity tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with a third request succeeding when a slot frees, bounded exhausted-capacity failure, cancellation while waiting, and the existing concurrent-worker cap.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#109

### Area
backend-app

### GitHub issue
[#110](https://github.com/moterodiaz/Junction/issues/110)

<!-- task:BASE-A6 -->
## BASE-A6: Cancel abandoned WebSocket work

### Goal
Reuse #111: cancel active request tasks on disconnect, including downstream calls, and never append abandoned history. No second terminal response; a closed socket cannot receive one.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-PRIV-03, REQ-WS-01

### Scope
backend/app/main.py; backend/tests/test_ws.py and cancellation tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with disconnect during thinking, provider cancellation observation, no history commit, repeated/reconnected requests and isolation from another session.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
none

### Area
backend-app

### GitHub issue
[#111](https://github.com/moterodiaz/Junction/issues/111)

<!-- task:BASE-A7 -->
## BASE-A7: Validate every model-produced card

### Goal
Reuse #112: safe non-empty defaults and drop invalid source URLs before card construction. Serialize pipeline changes; do not loosen contracts.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-WS-01

### Scope
backend/app/messages.py; backend/app/pipeline.py; backend/tests/test_pipeline.py and card tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh and contracts/test.sh with odd/empty fields and malformed HTTPS sources; every successful card meets the authoritative schema and preserves truthful model IDs.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#110

### Area
backend-app

### GitHub issue
[#112](https://github.com/moterodiaz/Junction/issues/112)

<!-- task:BASE-D0 -->
## BASE-D0: Prove successful live typed and audio cards

### Goal
Preserve #81 and its unassigned state. Existing remote mode validates errors too; extend opt-in success scenarios with real cleared Hamlet media, typed and spoken invokes, generated image and audible playback evidence. #79 in the old body is a merged PR for #27, not a new task dependency.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-INT-01, REQ-BASE-01

### Scope
contracts/test_remote.py; contracts/exchanges/; contracts/README.md; docs/evidence/base-live.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 evidence, not the whole gate. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Existing contracts/test.sh stays local by default. Future opt-in successful-card checks must fail on error terminals, absent illustration or missing expected grounding. Record real deployment revision, latency, card/image/playback outcomes, and manual iOS round trip without user content. Prior 17-test schema-only run is not success.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#69, #27

### Area
contracts

### GitHub issue
[#81](https://github.com/moterodiaz/Junction/issues/81)

<!-- task:TRUST-D0 -->
## TRUST-D0: Reuse the lead's concept card and registry work

### Goal
Preserve #117 and #122 ownership and delivered registry IDs. Do not recreate their documents. The new module rows extend the same registry.

### PRD section
§12.9; module TRUST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01

### Scope
docs/REQUIREMENTS.md; docs/TIETO_CONCEPT_CARD.md; docs/TIETO_LESSONS_LOG.md; AGENTS.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; Independent evidence. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Keep the original #117 checks and lead-approved merge rules. Concept card and lessons log describe actual evidence and limitations, not automatic challenge readiness.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
none

### Area
contracts

### GitHub issue
[#117](https://github.com/moterodiaz/Junction/issues/117)

<!-- task:TRUST-D1 -->
## TRUST-D1: Reuse requirement-linked task and PR templates

### Goal
Reuse #118 unchanged in purpose. Coordinate requirement IDs and trust-header headings with the lead; no parallel template rewrite in this pass.

### PRD section
§12.9; module TRUST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01

### Scope
.github/ISSUE_TEMPLATE/task.md; .github/PULL_REQUEST_TEMPLATE.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; protected-path owner merge. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Original #118 checks plus a real PR with Requirement, Verified by AI, Refused/escalated to named human and Human sign-off fields. D owns this coordination, not a fifth docs area.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#117

### Area
contracts

### GitHub issue
[#118](https://github.com/moterodiaz/Junction/issues/118)

<!-- task:TRUST-D2 -->
## TRUST-D2: Reuse protected-path workflow enforcement

### Goal
Reuse #120 and preserve the current assignee/claim. Enforce the lead's existing merge-authority rule, not a new policy.

### PRD section
§12.9; module TRUST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01

### Scope
.github/workflows/claude-fix.yml; .github/CODEOWNERS; .agents/hooks/safety-gate.py; AGENTS.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; protected-path owner merge. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Original #120 checks and actual protected-path refusal/owner-merge evidence. Do not weaken required CI or silently resolve review threads.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#117

### Area
contracts

### GitHub issue
[#120](https://github.com/moterodiaz/Junction/issues/120)

<!-- task:TRUST-D3 -->
## TRUST-D3: Reuse measured trust tooling and claim requirement gate

### Goal
Reuse #121. Preserve machine-readable dependency and canonical area parsing, and require registered IDs rather than introducing a competing registry.

### PRD section
§12.9; module TRUST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01

### Scope
tools/metrics; tools/task; .github/workflows/pr-header.yml

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; protected-path owner merge. Reuse existing issue; do not reopen merged work.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Original #121 metrics check plus a real requirement-linked PR header and refused missing-ID claim. Record denominators, time window and unavailable metrics honestly.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#117

### Area
contracts

### GitHub issue
[#121](https://github.com/moterodiaz/Junction/issues/121)

<!-- task:BASE-D1 -->
## BASE-D1: Specify compatible session lifecycle and auth handoff

### Goal
Agree explicit session-end, abandonment expiry, cancellation semantics and server/client auth rollout with A/B. Reuse headers or existing fields only if their meanings fit; version/negotiate any new wire messages. Document transport-close versus explicit session-end behavior.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-WS-04, REQ-PRIV-03

### Scope
contracts/ws-messages.schema.json; contracts/fixtures/; contracts/README.md; contracts lifecycle conformance tests

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
contracts/test.sh with new valid/invalid lifecycle fixtures, old-client compatibility/rejection and auth-off/on transition scenarios. Specify bounded expiry value and expiry clock before A/B adoption; no user payload persistence.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123

### Area
contracts

### GitHub issue
[#128](https://github.com/moterodiaz/Junction/issues/128)

<!-- task:BASE-A1 -->
## BASE-A1: Wire grounded Hamlet and unknown-book answers

### Goal
Execute the lead's approved source-grounding assignment to Ahmed, not a transfer of Marcus's #29. Pass loader context to existing reasoning and emit real act/scene/line citations. Other books take the explicit no-source-text path.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-SRC-01, REQ-BASE-01

### Scope
backend/app/pipeline.py; backend/tests/test_pipeline.py

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite; approved Ahmed handoff. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with independent Hamlet reference passages and unknown-book cases. Real successful citation evidence goes to #81; do not invent source coordinates or relabel unavailable sources.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #29, #112, #102

### Area
backend-app

### GitHub issue
[#129](https://github.com/moterodiaz/Junction/issues/129)

<!-- task:BASE-A2 -->
## BASE-A2: Harden transport and coordinate optional auth

### Goal
Preserve the lead's post-grounding /ws hardening handoff. Bound input/work, validate deployed config, add coordinated auth with backward-compatible disabled default, and retain safe errors and exactly one terminal result.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-WS-04, REQ-DEPLOY-01

### Scope
backend/app/main.py; backend/app/config.py; backend/app/pipeline.py; backend/tests/test_ws.py; backend/.env.example

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite; token off until B ships support. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh covers malformed/oversized requests, auth absent/bad/valid and disabled mode, bounded concurrency, repeated requests and deadlines. Record deployment/auth handoff to B; enable enforcement only after B's compatible client is verified.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #129, #128

### Area
backend-app

### GitHub issue
[#133](https://github.com/moterodiaz/Junction/issues/133)

<!-- task:BASE-A3 -->
## BASE-A3: Complete application session cleanup and isolation

### Goal
Connect explicit-end and bounded-expiry lifecycle to existing text/image/audio cleanup hooks without duplicating #109/#111. Set finite cache/media budgets. Coordinate C's in-memory session/image hooks rather than editing AI files.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-PRIV-03

### Scope
backend/app/main.py; backend/app/pipeline.py; backend/tests/test_errors_privacy.py and session lifecycle tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with two sessions, explicit end, abandoned expiry, exception, disconnect, cancellation and late completion. Assert no raw persistence, no abandoned history and expired media URLs cannot be retrieved. Hand actual expiry and provider-policy limits to D.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #128, #133, #109, #111, #108

### Area
backend-app

### GitHub issue
[#139](https://github.com/moterodiaz/Junction/issues/139)

<!-- task:BASE-B1 -->
## BASE-B1: Decode contract errors and adopt lifecycle/auth handoff

### Goal
Implement the lead's iOS error-decoding/fixture task. Decode valid error/card fixtures and nullable/unknown request IDs correctly; adopt agreed auth/session lifecycle without assuming enforcement is live. Clear session-owned UI data on end/expiry.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-IOS-02, REQ-WS-04

### Scope
ios/MetaLabCore/Sources/MetaLabCore/Contract.swift; ios/MetaLab/BackendSocket.swift; ios/MetaLab/AppModel.swift; ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 prerequisite. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh plus real Swift/Xcode build with contract fixtures and malformed responses. Test repeated invocation, stale response rejection, session reset, reconnect and fallback speech. Hand client auth readiness to A before enforcement.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #128

### Area
ios

### GitHub issue
[#134](https://github.com/moterodiaz/Junction/issues/134)

<!-- task:BASE-B2 -->
## BASE-B2: Verify capture display audio and recovery on hardware

### Goal
Reuse merged #34–38 rather than reopening them. Verify one real frame/clip, permissions, HFP, capture-before-display, actual image and audio, display-off flow, repeated invocation, PAUSED/STOPPED/hinges/link loss and reconnect on the loaner.

### PRD section
§12.2; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-BASE-01, REQ-IOS-01, REQ-IOS-02

### Scope
ios/MetaLab/GlassesBridge.swift; ios/MetaLab/AnswerSpeaker.swift; ios/MetaLab/LensLayout.swift; ios/DELIVERY_EVIDENCE.md

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; G0 hardware evidence. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh is only proxy evidence. Record device/DAT/Xcode versions and five real rehearsals with outcomes, cleared evidence and recovery steps. No raw user frames/audio saved; coordinate successful requests with #81.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #134

### Area
ios

### GitHub issue
[#140](https://github.com/moterodiaz/Junction/issues/140)

<!-- task:BASE-G0 -->
## BASE-G0: G0 accept the proven reading assistant

### Goal
Collate actual successful typed/audio cards, genuine illustration, audible playback, independent Hamlet grounding, unknown-book no-source, display-off experience, repeated/reconnected invocation, all cleanup/cancel/card fixes and five hardware rehearsals.

### PRD section
§14.1; module BASE; [PRD](metalab_prd.md).

### Requirement
REQ-BASE-01, REQ-INT-01, REQ-PRIV-03

### Scope
docs/evidence/G0.md; contracts live success scenarios

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; Lead acceptance only; BASE activation gate. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead @moterodiaz posts an explicit acceptance comment linked to revision, test outputs and hardware outcomes before closure. Schema-valid errors, mocks, docs or a Closes PR cannot satisfy/close this gate. Record missing billing/access separately; do not spend or provision here.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #81, #139, #110, #112, #140, #108

### Area
contracts

### GitHub issue
[#141](https://github.com/moterodiaz/Junction/issues/141)

<!-- task:INTENT-D1 -->
## INTENT-D1: Contract natural intent follow-ups and controls

### Goal
Specify full-utterance preservation, bounded intents, ambiguity clarification, session reset/cancel and whether frame-free follow-ups need a negotiated version. Preserve L0 and strict old clients; no new wire stage by default.

### PRD section
§12.3; module INTENT; [PRD](metalab_prd.md).

### Requirement
REQ-INTENT-01, REQ-INTENT-02, REQ-WS-04

### Scope
contracts/README.md; contracts/ws-messages.schema.json; contracts/fixtures/; contracts/exchanges/

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G1 contract prerequisite; activation after G0. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
contracts/test.sh with planned natural/follow-up/reset/cancel/ambiguity fixtures, old-client behavior and overlapping request IDs. Fixtures preserve source/audio/image semantics and current deadlines.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #141, #128

### Area
contracts

### GitHub issue
[#142](https://github.com/moterodiaz/Junction/issues/142)

<!-- task:INTENT-C1 -->
## INTENT-C1: Resolve natural intent and reason over follow-ups

### Goal
Resolve extracted text plus entire utterance/session into bounded reading/research/document intents or clarification. Keep established L0 resolver fallback and session-aware reasoning, including tenth-turn context and clean reset.

### PRD section
§12.3; module INTENT; [PRD](metalab_prd.md).

### Requirement
REQ-INTENT-01, REQ-INTENT-02

### Scope
backend/ai/intent.py (new); backend/ai/reasoning.py; backend/ai/session.py; backend/tests/test_intent.py (new); backend/tests/test_reasoning.py

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G1 implementation; remains disabled until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new intent tests for L0 positives/whole-word negatives, natural requests, ambiguity, unsupported intent, reset and isolated sessions. No user-content logs or abandoned-history commits; deliver adapter signature to A.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #142

### Area
backend-ai

### GitHub issue
[#146](https://github.com/moterodiaz/Junction/issues/146)

<!-- task:INTENT-A1 -->
## INTENT-A1: Preserve utterances and dispatch bounded intent

### Goal
Keep the full transcribed/typed question instead of reducing it to an L0 token. A alone integrates the resolver and bounded dispatch; preserve merged word-form fixes and fixed-command fallback, cancel and reset behavior.

### PRD section
§12.3; module INTENT; [PRD](metalab_prd.md).

### Requirement
REQ-INTENT-01, REQ-INTENT-02, REQ-LAT-02

### Scope
backend/stt/engine.py; backend/stt/commands.py; backend/app/pipeline.py; backend/app/config.py; backend/tests/test_stt.py and intent pipeline tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G1 implementation; G0 first. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with full utterance reaching C unchanged, L0 regressions, clarification, fallback, cancellation, overlapping requests and unchanged stage/request deadlines. Feature flag off before G1 acceptance.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #146, #139

### Area
backend-app

### GitHub issue
[#150](https://github.com/moterodiaz/Junction/issues/150)

<!-- task:INTENT-B1 -->
## INTENT-B1: Present follow-up session reset and cancel controls

### Goal
Use the agreed contract for natural spoken follow-ups, explicit reset/end and cancellation. Show clarification without losing the utterance; reject late cards after reset and keep phone/lens state consistent.

### PRD section
§12.3; module INTENT; [PRD](metalab_prd.md).

### Requirement
REQ-INTENT-02, REQ-IOS-02

### Scope
ios/MetaLab/AppModel.swift; ios/MetaLab/RootView.swift; ios/MetaLab/BackendSocket.swift; ios/MetaLabCore/Sources/MetaLabCore/SessionMachine.swift; ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G1 implementation; G0 first. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh and real hardware follow-up/reset/cancel/reconnect exchanges; no cross-session answers, retained old media or background capture. Handoff a real spoken follow-up to INTENT-G1.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #142, #140

### Area
ios

### GitHub issue
[#147](https://github.com/moterodiaz/Junction/issues/147)

<!-- task:INTENT-G1 -->
## INTENT-G1: G1 accept natural interaction without L0 regression

### Goal
Replay natural requests, ambiguities and follow-ups against deployed integration, then demonstrate a real spoken follow-up, reset and cancel on hardware while retaining L0 regression coverage.

### PRD section
§14.1; module INTENT; [PRD](metalab_prd.md).

### Requirement
REQ-INTENT-01, REQ-INTENT-02

### Scope
contracts/exchanges/; docs/evidence/G1.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Lead acceptance only; G1. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Existing contracts/test.sh plus new scenarios to implement. Lead acceptance comment names real outcomes, L0 regression evidence and session/deadline/privacy checks before closing. Do not close via an implementation PR.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #141, #150, #147

### Area
contracts

### GitHub issue
[#154](https://github.com/moterodiaz/Junction/issues/154)

<!-- task:VOICE-A1 -->
## VOICE-A1: Add bounded ElevenLabs speech using existing answer text

### Goal
Add optional server-side provider configuration and session-owned ElevenLabs delivery. Reuse speech_text, audio_url and the base/system voice path; do not call another answer model. Document provider handling before enabling.

### PRD section
§12.4; module VOICE; [PRD](metalab_prd.md).

### Requirement
REQ-VOICE-01, REQ-TTS-01, REQ-PRIV-03

### Scope
backend/stt/elevenlabs.py (new); backend/stt/speak.py; backend/app/config.py; backend/app/pipeline.py; backend/tests/test_speak.py and provider tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 VOICE; default off until VOICE-G2. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with planned missing-key, timeout, failure/bad-audio, cancellation, isolation and end/expiry tests. Real playback evidence and measured worst-case latency go to D; preserve global budgets.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #154, #109

### Area
backend-app

### GitHub issue
[#156](https://github.com/moterodiaz/Junction/issues/156)

<!-- task:VOICE-B1 -->
## VOICE-B1: Verify ElevenLabs playback and system voice fallback

### Goal
Reuse current playback UI, play provider audio through the intended route, support display-off flow and system-voice fallback on null/unplayable audio. Cancel playback on abandonment/reset.

### PRD section
§12.4; module VOICE; [PRD](metalab_prd.md).

### Requirement
REQ-VOICE-01, REQ-TTS-01

### Scope
ios/MetaLab/AnswerSpeaker.swift; ios/MetaLab/AppModel.swift; ios/MetaLabCore/Sources/MetaLabCore/SpeechPlan.swift; ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift; ios/DELIVERY_EVIDENCE.md

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 VOICE; default off until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh and real provider playback/display-off tests including interrupted, missing and malformed audio. Confirm no persistent user/audio cache and provide manual outcomes to VOICE-G2.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #154

### Area
ios

### GitHub issue
[#157](https://github.com/moterodiaz/Junction/issues/157)

<!-- task:VOICE-G2 -->
## VOICE-G2: G2 accept ElevenLabs independently

### Goal
Accept only real ElevenLabs contribution, audible hardware playback, audio-only UX, tested provider failure fallback and provider-policy-compatible cleanup. Follow-ups must already be proven.

### PRD section
§14.1; module VOICE; [PRD](metalab_prd.md).

### Requirement
REQ-VOICE-01

### Scope
docs/evidence/VOICE.md; contracts voice failure exchanges

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Lead acceptance only; G2 VOICE. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead acceptance comment links actual provider/config revision, playback observation, latency and failure/isolation/expiry checks. Do not infer success from a URL or gate research on this acceptance.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #156, #157

### Area
contracts

### GitHub issue
[#159](https://github.com/moterodiaz/Junction/issues/159)

<!-- task:RESEARCH-D1 -->
## RESEARCH-D1: Specify research provenance endpoint and locality contract

### Goal
Confirm sponsor-required Exa, Context.dev main/tech and Oxylabs endpoints; distinguish required from proposed calls. Agree provider roles, dates/prices/currency/provenance/fetch-time representation, explicit locality and budget envelope. Reuse sources only where meanings fit; contract version any metadata additions before A/B/C use.

### PRD section
§12.5; module RESEARCH; [PRD](metalab_prd.md).

### Requirement
REQ-RESEARCH-01, REQ-RESEARCH-02, REQ-WS-04

### Scope
contracts/README.md; contracts/fixtures/; contracts/exchanges/; docs/evidence/research-prerequisites.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 RESEARCH prerequisites. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Document endpoint/tool requirement, source link and confirmation date, credentials status without values, provider retention and failure policy. contracts/test.sh validates planned provenance/locality/partial results fixtures and strict-client compatibility. No token qualification calls or automatic location.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #154

### Area
contracts

### GitHub issue
[#158](https://github.com/moterodiaz/Junction/issues/158)

<!-- task:RESEARCH-C1 -->
## RESEARCH-C1: Discover extract and verify live performance information

### Goal
Exa discovers relevant play/performance sources; Context.dev structures dates/venues/prices; Oxylabs retrieves/verifies ticket-page facts. Return concise comparisons with provenance and uncertainty; use each provider distinctly. Treat external text as data and reject unsafe retrieval targets.

### PRD section
§12.5; module RESEARCH; [PRD](metalab_prd.md).

### Requirement
REQ-RESEARCH-01, REQ-RESEARCH-02

### Scope
backend/ai/research.py (new); backend/ai/research_providers/ (new); backend/tests/test_research.py (new)

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 RESEARCH; default off until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new provider fixtures plus real Helsinki query evidence. Verify dates/currencies/prices against independent linked ticket pages, mark unavailable/conflicting/stale facts, test hostile content, partial/all failures, cancellation, byte/result limits and no user logs. Hand adapter to A; no pipeline edits.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #158

### Area
backend-ai

### GitHub issue
[#160](https://github.com/moterodiaz/Junction/issues/160)

<!-- task:RESEARCH-A1 -->
## RESEARCH-A1: Integrate bounded research with session-only cache

### Goal
A serializes shared pipeline edits after the voice adapter implementation, not voice acceptance. Configure optional provider flags/credentials, request time/call/byte/result budgets, cancellation and isolated session cache within existing deadlines. Ordinary reading never depends on optional keys.

### PRD section
§12.5; module RESEARCH; [PRD](metalab_prd.md).

### Requirement
REQ-RESEARCH-02, REQ-PRIV-03, REQ-LAT-02

### Scope
backend/app/config.py; backend/app/pipeline.py; backend/app/main.py; backend/tests/test_pipeline.py and research budget tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 RESEARCH; default off until RESEARCH-G2. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new budget exhaustion, missing-key, partial/all failure, reset/end/expiry and disconnect tests. Measure worst-case real query latency, show no retained cache/query text across sessions and preserve one terminal response.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #160, #156

### Area
backend-app

### GitHub issue
[#162](https://github.com/moterodiaz/Junction/issues/162)

<!-- task:RESEARCH-B1 -->
## RESEARCH-B1: Present concise research comparisons and source links

### Goal
Ask for locality explicitly; display concise dates/prices and readable HTTPS sources on phone with a legible lens summary. Label partial/unverified/stale results. No location permission, booking, purchase or outgoing message flow.

### PRD section
§12.5; module RESEARCH; [PRD](metalab_prd.md).

### Requirement
REQ-RESEARCH-01, REQ-IOS-02

### Scope
ios/MetaLab/RootView.swift; ios/MetaLab/LensLayout.swift; ios/MetaLab/AppModel.swift; ios/MetaLabCore/Sources/MetaLabCore/Contract.swift; ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; G2 RESEARCH; default off until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh and real hardware comparison/source-link check, missing-locality clarification, partial/offline result and cancel/reset flows. No session content survives end/expiry; use negotiated metadata only.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #158

### Area
ios

### GitHub issue
[#161](https://github.com/moterodiaz/Junction/issues/161)

<!-- task:RESEARCH-G2 -->
## RESEARCH-G2: G2 accept useful live research independently

### Goal
Demonstrate the Helsinki performances query on the deployed reading product. Independently check upcoming dates and ticket prices, useful contribution from all three providers, source provenance, endpoint requirements and bounded privacy-compatible operation.

### PRD section
§14.1; module RESEARCH; [PRD](metalab_prd.md).

### Requirement
REQ-RESEARCH-01, REQ-RESEARCH-02

### Scope
docs/evidence/RESEARCH.md; contracts live research scenarios

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Lead acceptance only; G2 RESEARCH. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead acceptance comment links live facts with fetch times, provider contributions, manual source-link UX, worst-case latency and failure/budget/isolation/cleanup tests. Record each sponsor's readiness separately; a research card alone is not eligibility.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #162, #161

### Area
contracts

### GitHub issue
[#164](https://github.com/moterodiaz/Junction/issues/164)

<!-- task:GEMMA-C1 -->
## GEMMA-C1: Evaluate hosted Gemma text intent classification

### Goal
Agree held-out text/utterance intent fixtures and quality/latency/confidence thresholds with D before evaluation. Compare real hosted Gemma against the established resolver, including ambiguity, with no extra vision pass. Keep model/API calls server-side.

### PRD section
§12.6; module GEMMA; [PRD](metalab_prd.md).

### Requirement
REQ-GEMMA-01

### Scope
backend/ai/gemma_intent.py (new); backend/ai/evaluate_intent.py (new); backend/tests/test_gemma_intent.py (new); backend/ai/DELIVERY_EVIDENCE.md

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 GEMMA; G0 plus evaluation prerequisite. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
New backend tests and evaluation entry point are work to implement. Record dataset provenance, independent expected labels, per-intent errors, low-confidence fallback and cold/warm worst-case latency. Provide actual usage/model evidence; no activation on unevaluated accuracy.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #141

### Area
backend-ai

### GitHub issue
[#143](https://github.com/moterodiaz/Junction/issues/143)

<!-- task:GEMMA-A1 -->
## GEMMA-A1: Wire optional Gemma with bounded fallback

### Goal
A integrates optional hosted inference after serialized pipeline work. Feed extracted text and full utterance; low confidence, failure, unsupported class or missing key uses established resolver. Evaluation must support enabling; otherwise keep off.

### PRD section
§12.6; module GEMMA; [PRD](metalab_prd.md).

### Requirement
REQ-GEMMA-01, REQ-LAT-02

### Scope
backend/app/config.py; backend/app/pipeline.py; backend/tests/test_pipeline.py and classifier fallback tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 GEMMA; disabled until GEMMA-G3. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh covers default-off, absent credentials, timeout, low confidence, fallback equivalence, cancellation and unchanged deadlines. Actual classifier attribution uses cleared evidence unless D versions a compatible wire field.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #143, #139

### Area
backend-app

### GitHub issue
[#148](https://github.com/moterodiaz/Junction/issues/148)

<!-- task:GEMMA-G3 -->
## GEMMA-G3: G3 decide Gemma activation from measured evidence

### Goal
Review real classification quality and latency against agreed thresholds and established resolver, actual model usage and privacy. Record enable or keep-disabled decision with limitations.

### PRD section
§14.1; module GEMMA; [PRD](metalab_prd.md).

### Requirement
REQ-GEMMA-01

### Scope
docs/evidence/GEMMA.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; Lead acceptance only; G3 GEMMA. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead explicitly accepts passing evidence before enabling/closing as accepted. Failed or inconclusive evaluation stays disabled and blocked, not 'ready' because code exists. Include first-call/worst-case measurements and fallback evidence.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #143, #148

### Area
contracts

### GitHub issue
[#151](https://github.com/moterodiaz/Junction/issues/151)

<!-- task:MEDIA-D1 -->
## MEDIA-D1: Resolve Cloudinary eligible tooling and retention blockers

### Goal
Confirm eligible starter kit, Skills Pack or AI Power Start requirement and required survey. Agree application deletion, derived-asset/CDN invalidation, abandoned expiry and provider policy with A/C before implementation activation. Generated illustrations only.

### PRD section
§12.7; module MEDIA; [PRD](metalab_prd.md).

### Requirement
REQ-MEDIA-01, REQ-PRIV-03

### Scope
docs/evidence/cloudinary-prerequisites.md; contracts/README.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 MEDIA hard prerequisite; G0 first. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Cite current sponsor/tool guidance and dated confirmation; record credentials/forms separately. Demonstrate a feasible session-only deletion/cache policy or keep this issue blocked. Never relax privacy or send page photos to qualify; do not submit the survey in this pass.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #141

### Area
contracts

### GitHub issue
[#144](https://github.com/moterodiaz/Junction/issues/144)

<!-- task:MEDIA-C1 -->
## MEDIA-C1: Transform generated illustrations with Cloudinary tooling

### Goal
Use confirmed eligible tooling to transform generated black-background illustrations for the additive lens. Never upload captured page frames. Return source/generated/derived asset handles for A's lifecycle; preserve original session-owned image fallback.

### PRD section
§12.7; module MEDIA; [PRD](metalab_prd.md).

### Requirement
REQ-MEDIA-01

### Scope
backend/ai/cloudinary_media.py (new); backend/ai/image.py; backend/tests/test_cloudinary_media.py (new)

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 MEDIA; prerequisites first; disabled until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new generated-only input, transform failure, timeout, safe error and cancellation tests; compare original/transformed legibility with B and show meaningful benefit. No independent image-answer generation or hidden retention.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #144

### Area
backend-ai

### GitHub issue
[#149](https://github.com/moterodiaz/Junction/issues/149)

<!-- task:MEDIA-A1 -->
## MEDIA-A1: Own Cloudinary delivery deletion and expiry lifecycle

### Goal
A serializes pipeline integration and owns generated/derived delivery handles, session end, abandonment expiry, invalidation and cancellation. Missing optional keys do not affect base; failed transform uses original or text/audio.

### PRD section
§12.7; module MEDIA; [PRD](metalab_prd.md).

### Requirement
REQ-MEDIA-01, REQ-PRIV-03

### Scope
backend/app/config.py; backend/app/pipeline.py; backend/app/main.py; backend/tests/test_errors_privacy.py and media lifecycle tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 MEDIA; disabled until MEDIA-G3. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new two-session, deletion-after-error/disconnect, late-completion and expiry tests. Live generated assets and derivatives must be non-retrievable after the approved lifecycle; API deletion success alone is insufficient.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #149, #139

### Area
backend-app

### GitHub issue
[#152](https://github.com/moterodiaz/Junction/issues/152)

<!-- task:MEDIA-B1 -->
## MEDIA-B1: Verify transformed illustration legibility on the lens

### Goal
Reuse the current image UI and compare original/transformed illustrations on the real additive display. Confirm bright subject/black background, legibility and fallback behavior without captured-page uploads.

### PRD section
§12.7; module MEDIA; [PRD](metalab_prd.md).

### Requirement
REQ-MEDIA-01

### Scope
ios/MetaLab/LensLayout.swift; ios/MetaLab/GlassesBridge.swift; ios/DELIVERY_EVIDENCE.md

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 MEDIA hardware evidence. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh plus real hardware before/after observation and a concrete usability benefit. Include fetch-after-session-end behavior and no persistent phone image cache; do not label an untransformed image as sponsor use.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #149

### Area
ios

### GitHub issue
[#153](https://github.com/moterodiaz/Junction/issues/153)

<!-- task:MEDIA-G3 -->
## MEDIA-G3: G3 accept Cloudinary only with privacy and benefit evidence

### Goal
Verify eligible tool usage, real transformed generated artwork, additive-lens benefit and compatible provider/deletion/cache handling. Survey status is separate from runtime success.

### PRD section
§14.1; module MEDIA; [PRD](metalab_prd.md).

### Requirement
REQ-MEDIA-01

### Scope
docs/evidence/MEDIA.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; Lead acceptance only; G3 MEDIA. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead acceptance comment links tooling proof, hardware result and live original/derivative non-retrievability at end/expiry. Any retention/tooling blocker keeps module disabled; no submission-ready claim before required form is actually completed under separate authorization.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #152, #153

### Area
contracts

### GitHub issue
[#155](https://github.com/moterodiaz/Junction/issues/155)

<!-- task:BLUEPRINT-D1 -->
## BLUEPRINT-D1: Version the drawing contract and clear the Stoa dataset

### Goal
Obtain sponsor-cleared real construction drawings and permission before use. Specify drawing/page identity, coordinates/rotation, regions/provenance, limits and negotiated version. Agree independent expected answers/regions, accuracy/cost thresholds and abstention policy before scoring.

### PRD section
§12.8; module BLUEPRINT; [PRD](metalab_prd.md).

### Requirement
REQ-BLUEPRINT-01, REQ-WS-04

### Scope
contracts/drawings.schema.json (new); contracts/fixtures/drawings/ (new); contracts/README.md; docs/evidence/stoa-prerequisites.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; L3 after G1 and voice/follow-up milestone. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
contracts/test.sh extended with new drawing/strict-old-client fixtures. Record dataset clearance/provenance without storing user documents. A blueprint-themed prompt or unsolicited metadata to existing clients fails the prerequisite.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #154, #159

### Area
contracts

### GitHub issue
[#163](https://github.com/moterodiaz/Junction/issues/163)

<!-- task:BLUEPRINT-C1 -->
## BLUEPRINT-C1: Answer from real drawings with verifiable source regions

### Goal
Ground construction-drawing questions in sponsor-cleared pages and return verifiable regions in the agreed coordinate system. Abstain on unsupported/unreadable/uncertain inputs; no engineering safety claims.

### PRD section
§12.8; module BLUEPRINT; [PRD](metalab_prd.md).

### Requirement
REQ-BLUEPRINT-01

### Scope
backend/ai/blueprint.py (new); backend/ai/evaluate_blueprint.py (new); backend/tests/test_blueprint.py (new)

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 BLUEPRINT; contract and cleared data first. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
New tests/evaluator are work to implement. Score held-out drawings against independent expected answers/regions and pre-agreed thresholds; record errors, accuracy, region correctness, per-document worst-case latency and cost. Keep document/text/region caches session-only.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #163

### Area
backend-ai

### GitHub issue
[#165](https://github.com/moterodiaz/Junction/issues/165)

<!-- task:BLUEPRINT-A1 -->
## BLUEPRINT-A1: Add a bounded negotiated document-processing path

### Goal
A serializes the optional document path after prior pipeline edits. Enforce negotiated version, input byte/page/time/work budgets and cancellation without raising global deadlines; no drawing-specific fields to old clients.

### PRD section
§12.8; module BLUEPRINT; [PRD](metalab_prd.md).

### Requirement
REQ-BLUEPRINT-01, REQ-PRIV-03, REQ-LAT-02

### Scope
backend/app/main.py; backend/app/pipeline.py; backend/app/config.py; backend/tests/test_pipeline.py and document limit tests

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 BLUEPRINT; disabled until accepted. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
backend/test.sh with new oversize/too-many-pages/unsupported-version/unreadable/cancel/isolation/end/expiry tests. Measure real heaviest supported drawing within agreed time/cost limits; base remains available with optional path disabled.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #165, #139

### Area
backend-app

### GitHub issue
[#167](https://github.com/moterodiaz/Junction/issues/167)

<!-- task:BLUEPRINT-B1 -->
## BLUEPRINT-B1: Present document mode and drawing source regions

### Goal
Add explicit document-mode UX and source-region presentation using versioned metadata. Respect page/rotation/coordinate semantics; show abstention and unsupported-mode fallback without corrupting reading clients.

### PRD section
§12.8; module BLUEPRINT; [PRD](metalab_prd.md).

### Requirement
REQ-BLUEPRINT-01, REQ-IOS-02

### Scope
ios/MetaLab/AppModel.swift; ios/MetaLab/RootView.swift; ios/MetaLab/LensLayout.swift; ios/MetaLabCore/Sources/MetaLabCore/Contract.swift; ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; G3 BLUEPRINT; contract first. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
ios/test.sh with planned decoding/region-transform fixtures plus real sponsor-cleared drawing presentation on phone/lens. Verify independent expected region, cancel/reset and old-client rejection/downgrade; no persistent document/media cache.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #163

### Area
ios

### GitHub issue
[#166](https://github.com/moterodiaz/Junction/issues/166)

<!-- task:BLUEPRINT-G3 -->
## BLUEPRINT-G3: G3 accept Stoa from cleared-dataset accuracy and cost evidence

### Goal
Demonstrate grounded questions over actual sponsor-cleared drawings and verifiable displayed answer regions. Review independent held-out accuracy, per-document cost/latency, abstentions and version compatibility.

### PRD section
§14.1; module BLUEPRINT; [PRD](metalab_prd.md).

### Requirement
REQ-BLUEPRINT-01

### Scope
docs/evidence/BLUEPRINT.md; contracts document integration scenarios

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P2; Lead acceptance only; G3 BLUEPRINT. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead acceptance comment links dataset clearance, pre-agreed numeric thresholds and worst-case measurements, real region UX and privacy/cancel/fallback checks. Not ready for Stoa on prompt-only evidence; no relaxed thresholds after seeing results.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #167, #166

### Area
contracts

### GitHub issue
[#168](https://github.com/moterodiaz/Junction/issues/168)

<!-- task:EVID-A1 -->
## EVID-A1: Supply cleared core build trust development and hosting evidence

### Goal
A documents actual backend checks and limits; runtime/Python/native/Whisper dependencies and CI entry points; actual Codex contribution map and cleared handoff material; deployed Modal config/Whisper role and endpoints without secrets. No code/integration changes required by this evidence task.

### PRD section
§12.9–12.12; module TRUST, BUILD, DEV, HOST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01, REQ-BUILD-01, REQ-DEV-01, REQ-HOST-01

### Scope
backend/app/DELIVERY_EVIDENCE.md (new)

### Owner
Ahmed, @Ahm3d-KA. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; does not block G0. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Record commands actually run, revision, platform and outcomes, not proposed tests as passed. Identify mock versus live evidence, unknowns and failures. Supply D only cleared no-user-content evidence; no transcript upload, spend or provisioning.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123

### Area
backend-app

### GitHub issue
[#130](https://github.com/moterodiaz/Junction/issues/130)

<!-- task:EVID-B1 -->
## EVID-B1: Supply cleared Swift hardware and development evidence

### Goal
B supplies real Swift/Xcode/DAT requirements and checks, proxy-test limitations, actual Codex contribution map and cleared checkpoint/handoff material, plus available Meta hardware evidence. Coordinate this file sequentially with B's runtime evidence tasks.

### PRD section
§12.9–12.12; module TRUST, BUILD, DEV, HOST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01, REQ-BUILD-01, REQ-DEV-01, REQ-HOST-01

### Scope
ios/DELIVERY_EVIDENCE.md

### Owner
Maksym, @maksymmatviievskyi. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; does not block G0. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Commands/revision/Xcode/SDK/device outcomes and missing hardware checks are explicit. No unsupported Linux Swift check represented as iOS/hardware validation; no user media/secrets in retained artifacts. Hand limitations and runner requirements to D.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123

### Area
ios

### GitHub issue
[#131](https://github.com/moterodiaz/Junction/issues/131)

<!-- task:EVID-C1 -->
## EVID-C1: Supply cleared AI grounding model and build evidence

### Goal
C supplies source-grounding evidence and model-test limitations; real AI test entry points/dependencies; actual Codex contribution map and cleared development handoff; actual reader/reason/image model IDs, endpoint/config and demonstrated Nemotron/Gemini/possible Verda contributions. Preserve the current reader chain.

### PRD section
§12.9–12.12; module TRUST, BUILD, DEV, HOST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01, REQ-BUILD-01, REQ-DEV-01, REQ-HOST-01

### Scope
backend/ai/DELIVERY_EVIDENCE.md (new)

### Owner
Marcus, @Marcus228. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; does not block G0. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Separate configured, attempted, succeeded and fallback model usage, identify stubs and live misses, never claim intended model ran. Give D reproducible cleared evidence, endpoint provenance and Verda confirmation questions without keys/prompts/page content.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123

### Area
backend-ai

### GitHub issue
[#132](https://github.com/moterodiaz/Junction/issues/132)

<!-- task:TRUST-GATE -->
## TRUST-GATE: Validate the Tieto requirement-linked PR walkthrough

### Goal
Reuse existing docs and tools for one real requirement-linked PR walkthrough: verified findings, refusals/escalations, named human sign-off/residual risks, measured review/acceptance/escape/routing metrics and lessons.

### PRD section
§12.9; module TRUST; [PRD](metalab_prd.md).

### Requirement
REQ-PROC-01

### Scope
docs/TIETO_CONCEPT_CARD.md; docs/TIETO_LESSONS_LOG.md; docs/evidence/TRUST.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent challenge validation; lead acceptance. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead accepts linked real PR, actual metrics with denominator/time window and limitations, backend/Swift/model checks and named accountability. Distinguish implementation present from validated/submission-ready; no fabricated time-savings estimate.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #117, #118, #120, #121, #130, #131, #132

### Area
contracts

### GitHub issue
[#135](https://github.com/moterodiaz/Junction/issues/135)

<!-- task:BUILD-D1 -->
## BUILD-D1: Prove a dedicated CRACI build before CI migration

### Goal
D coordinates a dedicated CRACI build with documented dependencies/image/test commands first. Confirm sponsor runner requirements and Swift/Xcode availability. Any workflow installation is a future separately reviewed protected-path implementation, not this docs pass.

### PRD section
§12.10; module BUILD; [PRD](metalab_prd.md).

### Requirement
REQ-BUILD-01

### Scope
docs/evidence/BUILD.md; .github/workflows/craci-evaluation.yml (future protected-path change only)

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; required CI unchanged. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Record actual CRACI build/run evidence and compare test/dependency coverage with required ci. Keep ci required and unmodified until compatibility and named lead approval are proven. Missing Swift/Xcode or unsupported runtime is a blocker, not a waived check.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #130, #131, #132

### Area
contracts

### GitHub issue
[#136](https://github.com/moterodiaz/Junction/issues/136)

<!-- task:DEV-D1 -->
## DEV-D1: Validate actual Codex contributions and a cleared Entire workflow

### Goal
Map actual Codex contributions to commits/files/tests. Demonstrate an Entire checkpoint/handoff and codebase-graph workflow using a purpose-built cleared development session; measure useful observations, limitations and human review. Installation alone is not contribution.

### PRD section
§12.11; module DEV; [PRD](metalab_prd.md).

### Requirement
REQ-DEV-01

### Scope
docs/evidence/DEV.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; approved cleared session only. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Lead accepts sanitized contribution map, real workflow/checkpoint/graph evidence and measured observations. Confirm handling before any future integration; never upload existing transcripts wholesale, secrets or user content. Missing real Codex/Entire evidence keeps the relevant track candidate.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #130, #131, #132

### Area
contracts

### GitHub issue
[#137](https://github.com/moterodiaz/Junction/issues/137)

<!-- task:HOST-D1 -->
## HOST-D1: Validate existing-track contributions and Verda eligibility

### Goal
Maintain per-challenge states and prerequisites for Meta/Gemini/Modal/Nemotron/Verda. Require actual hardware/model/compute contributions, truthful per-request attribution and sponsor confirmation of reported Verda inference eligibility; preserve Modal and the reader chain.

### PRD section
§12.12; module HOST; [PRD](metalab_prd.md).

### Requirement
REQ-HOST-01

### Scope
Junction-Prep/HACK_JUNCTION_CHALLENGES_AND_STRATEGY.md; docs/evidence/HOST.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P1; Independent evidence; live validation still required. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Record confirmed endpoints/model IDs, successful contributions and missing credentials/forms/confirmation/live evidence separately. Draft required Nemotron usage note and Verda summary, but send nothing externally. Tracks without evidence remain candidate/implementation present, never submitted.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #130, #131, #132

### Area
contracts

### GitHub issue
[#138](https://github.com/moterodiaz/Junction/issues/138)

<!-- task:RELEASE-D1 -->
## RELEASE-D1: Confirm feature freeze and prepare only validated submissions

### Goal
Ask the lead to confirm proposed 2026-11-15 08:00 Europe/Helsinki runtime freeze. Validate enabled modules, keep unfinished extensions disabled, prepare <=2-minute video/MIT repo/model notes and applicable form checklist. Target saved FINAL at 09:30 ahead of 10:00.

### PRD section
§14.3; module RELEASE; [PRD](metalab_prd.md).

### Requirement
REQ-HOST-01, REQ-BASE-01, REQ-PROC-01

### Scope
Junction-Prep/HACK_JUNCTION_CHALLENGES_AND_STRATEGY.md; docs/evidence/release.md

### Owner
Mateo, @moterodiaz. One responsible stream; preserve current assignees and approved handoffs.

### Priority and activation gate
P0; After G0; preparation only, no sponsor submission authorization. Initially blocked; documentation #123 and listed prerequisites first.

### Behavior, fallback and privacy
Apply PRD §§6–7 and §12.1 plus this module's failure/retention rules. Optional failure must leave BASE usable; cancel abandoned work, isolate sessions and delete session text/cache/generated media at end/bounded expiry. Provider-policy conflicts block activation. Retain only cleared evidence, never user content or secrets.

### Acceptance check
Named lead records freeze decision, enabled/disabled list, live/hardware validation and candidate→implementation present→validated→submission-ready states. Optional gates do not block base preparation. Actual platform/forms/Discord writes and submitted state require separately authorized execution and receipt; this task does not submit.

### Handoffs and evidence
Named owner supplies adapter/contract or manual/hardware/test outcomes to the next stream and D. Record revision, actual commands/outcomes, missing checks and provider-policy limits. Gate tasks require explicit lead acceptance before closure; documentation is not completion evidence.

### Depends on
#123, #141, #138

### Area
contracts

### GitHub issue
[#145](https://github.com/moterodiaz/Junction/issues/145)
