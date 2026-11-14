# Junction 2026: MetaLab challenge strategy

**Project:** one reading assistant, not one product per sponsor. **Team:** Ahmed @Ahm3d-KA, Maksym @maksymmatviievskyi, Marcus @Marcus228, Mateo @moterodiaz (lead).

Execute the [four-stream implementation plan](IMPLEMENTATION_PLAN.md), using the [PRD](metalab_prd.md) and the existing [requirement registry](../docs/REQUIREMENTS.md). This document specifies candidates and evidence, not promised qualification. This pass changes documentation/issues only: no installs, integrations, provisioning, spend, sponsor forms or submissions.

## 1. Shared product and truthful evidence

BASE proves glasses capture → backend reading/grounding/illustration → lens/audio. INTENT preserves natural questions and session follow-ups. VOICE and RESEARCH extend this same reading story. GEMMA and MEDIA are conditional improvements; BLUEPRINT is a contract-first, real-drawing mode after the voice/follow-up milestone. TRUST, BUILD, DEV and HOST package actual development/hosting contributions independently of runtime delivery.

Keep credentials/model calls server-side, existing deadlines, optional flags off until accepted, one terminal result and cancellation. User text/cache/generated media are session-only; raw frames/audio are never persisted/logged. Provider policies are separate from application cleanup; an incompatible integration stays blocked. No automatic location, booking, purchase or outbound message. Development evidence must be cleared of user content and secrets; no wholesale Entire transcript upload.

Preserve the existing Nemotron/Gemini reader chain and truthful `card.models.read` (#99). The lead dropped benchmark plan 006; do not revive it. A configured endpoint/model is not proof that it contributed to a successful request.

## 2. Readiness states and challenge matrix

**candidate → implementation present → validated → submission-ready → submitted**

- **candidate:** coherent scope and owner exist; prerequisites may be missing.
- **implementation present:** meaningful code/tooling exists. This is not live validation or eligibility.
- **validated:** real behavior and required tooling/usage demonstrated with reproducible evidence.
- **submission-ready:** Mateo accepts validated evidence, applicable forms/permissions/confirmation and completed materials.
- **submitted:** actual separately authorized submission receipt/link/time is recorded.

Baseline below reflects inspected repository/issues on 2026-11-14, not a new sponsor confirmation. No track is marked submission-ready or submitted by this pass. Record credential status, required form status, sponsor confirmation and live evidence independently; “unknown” is not “done”.

| Challenge | Module / requirement | Baseline | Required evidence and explicit blockers | Execution entry |
|---|---|---|---|---|
| [Meta, main 342](https://hackjunction.app/participate/45/challenges/342) | BASE/HOST; REQ-BASE-01, REQ-HOST-01 | implementation present | Real DAT capture/display/audio-only/recovery, five hardware rehearsals; four rubric items at 25% each. Hardware behavior remains to prove. | BASE-B1/B2, BASE-G0, HOST-D1 |
| [Gemini, tech 48](https://hackjunction.app/participate/45/tech-challenges/48) | BASE/HOST; REQ-IMG-01, REQ-HOST-01 | implementation present | Successful grounded reasoning and genuine generated illustration; actual model IDs/usage. Billing/access is a separate unresolved verification, not authorization to top up. | BASE-D0 (#81), EVID-C1, HOST-D1 |
| [Modal, tech 40](https://hackjunction.app/participate/45/tech-challenges/40) | BASE/HOST; REQ-DEPLOY-01, REQ-HOST-01 | implementation present | Deployed configuration/public endpoint and useful orchestration/Whisper compute role, not just an API proxy. Live endpoint is reported on board; successful full reading still unproven. | EVID-A1, BASE-D0, HOST-D1 |
| [Nemotron, tech 46](https://hackjunction.app/participate/45/tech-challenges/46) | BASE/HOST; REQ-READ-02, REQ-HOST-01 | implementation present | Visible contribution to core functionality on actual successful requests; required model-use note. Gemini fallback must not be attributed to Nemotron. | EVID-C1, HOST-D1 |
| [Verda, tech 56](https://hackjunction.app/participate/45/tech-challenges/56) | HOST; REQ-HOST-01 | candidate | Planning reports Verda-hosted Nemotron inference; confirm actual endpoint ownership and sponsor eligibility. Inference API use may qualify, but not by assumption. Need actual useful usage and required short summary + submission link in Verda's Junction Discord channel, separately authorized. No migration off Modal. | EVID-C1, HOST-D1 |
| [Tieto, main 351](https://hackjunction.app/participate/45/challenges/351) | TRUST; REQ-PROC-01 | implementation present | Reuse #117–121/#122 concept card, lessons, requirement-linked real PR header/walkthrough, measured metrics, named owner/refusals/residual-risk sign-off. Rubric: clarity 30%, practicality 25%, measurement 25%, evidence 20%. Docs alone do not validate the walkthrough. | TRUST-D0–D3, EVID-A1/B1/C1, TRUST-GATE |
| [Codex, tech 49](https://hackjunction.app/participate/45/tech-challenges/49) | DEV; REQ-DEV-01 | candidate | Actual Codex contribution-to-commit/file/test map and useful development evidence, not merely AGENTS.md or work from another model. | EVID-A1/B1/C1, DEV-D1 |
| [Entire, tech 51](https://hackjunction.app/participate/45/tech-challenges/51) | DEV; REQ-DEV-01 | candidate | Real checkpoint/handoff and codebase-graph workflow, measured observations/limits. Confirm approved handling; purpose-built cleared session only. Installing CLI alone is insufficient. | DEV-D1 |
| [CRACI, tech 42](https://hackjunction.app/participate/45/tech-challenges/42) | BUILD; REQ-BUILD-01 | candidate | Dedicated successful CRACI build with image/dependency/test evidence, runner and Swift/Xcode compatibility gaps. Preserve required ci until equivalence and lead approval; no migration in this pass. | EVID-A1/B1/C1, BUILD-D1 |
| [ElevenLabs, tech 50](https://hackjunction.app/participate/45/tech-challenges/50) | VOICE; REQ-VOICE-01 | candidate | Real playback, useful voice/audio-only experience, bounded failure/system-voice fallback and session deletion; reuse existing answer text. Provider/key/policy status unconfirmed. | VOICE-A1/B1, VOICE-G2 |
| [Exa, main 298](https://hackjunction.app/participate/45/challenges/298) | RESEARCH; REQ-RESEARCH-01/02 | candidate | Discover relevant live performances/sources for the reading question, with useful sourced comparison. Confirm required endpoint/tool use and credentials. | RESEARCH-D1/C1, RESEARCH-G2 |
| [Context.dev, main 332](https://hackjunction.app/participate/45/challenges/332) and [tech 44](https://hackjunction.app/participate/45/tech-challenges/44) | RESEARCH; REQ-RESEARCH-01/02 | candidate (each track) | Current main title: “The Web Is Your Real-Time Database”, not the old main 334 title. Extract live structured schedules/dates/venues/prices; no persistent database needed. Confirm each track's exact endpoint/tool requirements and separately record validation/readiness for main and tech. | RESEARCH-D1/C1, RESEARCH-G2 |
| [Oxylabs, tech 32](https://hackjunction.app/participate/45/tech-challenges/32) | RESEARCH; REQ-RESEARCH-01/02 | candidate | Useful live retrieval/verification of ticket-page evidence, not token calls or duplicate Exa discovery. Confirm sponsor-required Web API endpoint/mode and actual use; retain provenance. | RESEARCH-D1/C1, RESEARCH-G2 |
| [Gemma, tech 47](https://hackjunction.app/participate/45/tech-challenges/47) | GEMMA; REQ-GEMMA-01 | candidate | Real hosted text-based intent classification, measured held-out quality/confidence and cold/warm latency against existing resolver; fallback works. No extra mandatory vision pass. | GEMMA-C1/A1, GEMMA-G3 |
| [Cloudinary, tech 41](https://hackjunction.app/participate/45/tech-challenges/41) | MEDIA; REQ-MEDIA-01 | candidate | Confirm eligible starter kit, Skills Pack or AI Power Start, meaningful generated-illustration transform benefit and session-compatible asset/derivative/CDN deletion. Required [survey](https://cld.media/hackathon-survey) remains a separate form. No captured page uploads; incompatible cache/provider policy blocks module. | MEDIA-D1 first, MEDIA-C1/A1/B1, MEDIA-G3 |
| [Stoa, main 335](https://hackjunction.app/participate/45/challenges/335) | BLUEPRINT; REQ-BLUEPRINT-01 | candidate | Sponsor-cleared real construction drawings, versioned drawing/region contract first, independent accuracy/region/cost evaluation and live region UX. Not a blueprint-themed prompt. L3 remains after G1 and voice/follow-ups. | BLUEPRINT-D1 first, C1/A1/B1, BLUEPRINT-G3 |

### Required endpoint and confirmation ledger

These are prerequisites to resolve, not permission to create accounts, install tooling or issue qualification-only calls.

| Service | What is known / what must be recorded | Owner |
|---|---|---|
| Nemotron / Verda | Existing configured NVIDIA-compatible URL and actual deployed endpoint may differ. Record each actual base URL/model, successful reader contribution, endpoint provenance and Verda's dated eligibility confirmation; no keys. | C evidence → D confirmation |
| Exa | Discovery role approved. Record exact challenge-required discovery API/SDK/tool, source of requirement and successful useful request. Endpoint confirmation pending. | D prerequisite → C adapter |
| Context.dev | Structured extraction role approved. Record main 332 and tech 44 required endpoint/mode, extraction schema and useful schedule output separately. Do not infer that any Context call qualifies. | D → C |
| Oxylabs | Ticket-page retrieval/verification role approved. Record required Web API endpoint/mode and live page evidence distinct from discovery/extraction. Confirmation pending. | D → C |
| Cloudinary | Eligible tooling, survey and deletion/CDN/provider handling need dated confirmation before activation. | D → C transform / A lifecycle |
| ElevenLabs / Gemma | Record chosen hosted endpoint/model/voice, optional-key status, timeout envelope, provider policy and real contribution; do not store secrets. | A/C → D |
| CRACI / Entire | Record required build/checkpoint/graph workflow, runner/tool versions and approved evidence handling. Do not confuse install with validated use. | D with A/B/C inputs |

Source for the planning baseline: the user-approved planning session inspected the official challenge catalog on 2026-11-14. The linked official pages are rechecked by the named prerequisite tasks before any submission-ready decision; this document does not assert a new live re-verification.

## 3. Useful extension scenario and gates

While reading Hamlet: **“Find upcoming performances of this play in Helsinki and compare dates and ticket prices.”**

Exa discovers; Context.dev extracts structured dates/venues/prices; Oxylabs verifies ticket pages. Show readable sources and fetch-time/provenance, mark missing/conflicting facts and bound every call/result/byte/time budget. Locality is supplied explicitly. Session-only caches and cancellation apply even on partial/all-provider failure. No automatic location, booking, purchases or messages.

- G0 first: actual successful BASE cards, generated illustration, audio, Hamlet grounding/no-source path, recovery and five hardware rehearsals. #81's recorded schema-valid errors are insufficient.
- G1 next: full utterance, session-aware follow-ups, L0 regressions, reset/cancel/ambiguity evidence.
- G2: independently accept VOICE and RESEARCH. A serializes pipeline edits; C/B can build adapters/UI within agreed contracts.
- G3: Gemma/Cloudinary after G0 plus evaluation/privacy/tooling prerequisites. Stoa after G1 and the voice/follow-up milestone, with drawing contract first.
- TRUST/BUILD/DEV/HOST evidence can proceed without delaying G0. No unfinished extension is enabled or promoted by documentation alone.

## 4. Official schedule and submission preparation

The existing baseline comes from the [participant guide](https://hackjunction.app/participate/45/guide); confirm applicable fields/rules before finalizing. Multiple challenge entries are allowed.

| Time, Europe/Helsinki | Action / status |
|---|---|
| Friday November 13, 23:59 | Pre-submission draft deadline. Historical checklist item, not a claim it was completed. |
| Saturday November 14, 12:00 | Final form opens; challenges may be edited until the deadline. |
| Sunday November 15, **08:00** (06:00 UTC) | **Proposed runtime freeze**, awaiting lead confirmation. Validate/rehearse enabled features; unfinished modules stay off. |
| Sunday **09:30** (07:30 UTC) | Team target: authorized operator switches DRAFT → FINAL, saves and verifies receipt. |
| Sunday **10:00 sharp** (08:00 UTC) | Official final deadline; do not rely on last-minute changes. |
| Sunday 10:30–14:00 | Required physical table presence and assigned peer/partner reviews. Missing either can disqualify the main-prize entry. |
| Sunday 14:15–15:10 | Top-five finalist pitching window; existing guide baseline: 3-minute pitch + 3-minute Q&A. |

Preparation checklist, owned by D, with actual execution requiring separate authorization:

- [ ] Project name, punchline, description, technologies and only evidenced challenge selections.
- [ ] Public repository/root MIT licence (already delivered by #114/#116); verify public access.
- [ ] Publicly accessible video **≤2:00**; target 1:50–1:58, check actual duration/access.
- [ ] Live demo endpoint and actual successful feature proof; fallback cleared recording.
- [ ] Required pitch PDF and team contact details, entered privately, never committed here.
- [ ] Truthful model/hosting notes and each applicable sponsor's form/confirmation/tooling evidence.
- [ ] Cloudinary survey, if entering, and Verda short summary + submission link, if confirmed eligible. This pass submits neither.
- [ ] Named lead readiness sign-off, then separately authorized actual FINAL save and receipt.
- [ ] Review assignments, numbered table coverage and team presence plan.

### Truthful Nemotron model-use note

Fill from successful request evidence, not configured defaults:

> **Models used.** MetaLab used NVIDIA `[actual model ID]` via `[actual endpoint]` for `[demonstrated page-reading contribution]`, with thinking `[actual setting]`. Gemini `[actual IDs]` contributed `[reasoning / illustration evidence]`. The existing reader fallback remains enabled; per-request attribution identifies the reader that actually succeeded. Frames/audio are processed in memory and not stored by the application. Provider handling is recorded separately.

For Verda, draft the actual eligible inference/compute contribution and link only after confirmation. Retain Modal's actual role; do not claim a migration or sponsor use that did not occur.

## 5. Explicit exclusions

Defer databases/persistent sessions (Aiven, MongoDB Atlas, Tiger Data/MariaDB tracks), new hardware (Arduino/robotics/alternative displays), separate banking/healthcare/recruitment/dispatch products and the AfterQuery RL environment. No bookings, purchases, automatic location or outbound messages in the product. No dropped benchmark plan 006 or removed public audit documents.

These exclusions protect the working BASE and do not remove any approved coherent module from the execution backlog. Candidate scope is a place to evaluate useful work, not a promise to finish or qualify.
