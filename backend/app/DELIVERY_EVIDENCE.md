# Backend core: delivery evidence (EVID-A1, #130)

Owner: Ahmed (@Ahm3d-KA), area `backend/app/` and `backend/stt/`. Requirements: REQ-PROC-01, REQ-BUILD-01, REQ-DEV-01, REQ-HOST-01.

This file records only commands that were actually run, with their revision, platform and outcome. **Mock** means stubbed model clients (no keys, no network); **live** means the deployed Modal backend. Anything not run is listed under "Not checked". No secrets, transcripts or user content appear here.

## 1. Revision and platform

| Item | Value |
|---|---|
| Revision checked | `03c24bd` (main, 2026-11-14T16:17:44Z) |
| Local platform | Linux 7.2.15 x86_64 (EndeavourOS), Python 3.14.10; Python 3.12.16 in a separate venv |
| CI platform | GitHub Actions `ubuntu-latest` (`.github/workflows/ci.yml`) |

## 2. Core build (REQ-BUILD-01)

**Dependencies** (`backend/requirements.txt`, installed in `backend/.venv` by `backend/test.sh`): fastapi 0.162.7, pydantic 2.14.3, uvicorn 0.54.0, httpx 0.28.1, google-genai 3.3.0, jsonschema 4.23.0.

**Speech engine** (`backend/stt/requirements.txt`, production image only, never installed in CI): `faster-whisper==1.2.1`, `av<16`. av 16 removed `open(metadata_errors=...)`, which faster-whisper 1.2.1 still passes; found by running it, not from docs. The av and ctranslate2 wheels bundle ffmpeg and OpenMP, so the slim image needs no system packages (checked by the stt/deploy audit).

**CI entry points** (`ci.yml`, one job): shell syntax for `tools/*` and hooks; guard-hook tests; "areas have tests" (an area with code must ship an executable `test.sh`); then each area's `test.sh` (`backend/`, `contracts/`, `ios/`).

**Commands run on 2026-11-14 at revision `03c24bd` (mock):**

| Command | Outcome |
|---|---|
| `backend/test.sh` (Python 3.14), run twice | 231 tests OK, both runs (6.2 s) |
| `python -m unittest discover` under Python 3.12.16 | 231 tests OK |
| `contracts/test.sh` (local; the remote test skips without `WS_URL`) | 17 tests OK, 1 skipped |

## 3. Hosting (REQ-HOST-01, REQ-DEPLOY-01)

Deployed by @Marcus228 with `modal deploy backend/app/modal_app.py`.

| Setting (`modal_app.py`) | Value | Why |
|---|---|---|
| Public endpoint | `wss://junction26-vision--metalab-web.us-east.modal.run/ws` (health: `/health`) | posted on the board 13:57 |
| Secret | Modal secret `metalab` (names in `backend/.env.example`); `create_app(require_keys=True)` stops the container at start, naming any missing key (#92) | keys never in the repo or image |
| Containers | `max_containers=1`, `@modal.concurrent(max_inputs=20)` | generated images and speech clips live in process memory |
| Size | `cpu=2.0`, `memory=2048`; `scaledown_window=300`; `timeout=600` | Whisper small.en ≈ 4 s per clip on one core |
| Whisper role | `small.en` weights baked into the image at build time (#107); `stt.warm()` loads them at container start; a failed load is logged and does not stop the server | the 0.5 GB download took 73 s on every cold start |

**Live checks:**

| When | Command | Outcome |
|---|---|---|
| 14:05 | one typed `explain` request with a real photo of a Hamlet page | card in 25.0 s: reading 0.3 s, thinking 10.1 s, drawing 13.5 s; `models` = read `nemotron-3.5-super-vl`, reason `gemini-4-hydrogen`, image `gemini-nano-banana-2.1`; `image_url` set; `audio_url` null |
| ~15:25 | `WS_URL=…/ws contracts/test.sh` | 17 tests; every live reply passed the schema; drift only from placeholder media in the recordings (a 28-byte fake JPEG gives `internal` after reading; an empty WAV gives `stt_failed`, which does not show whether Whisper ran: an import or model-load failure gives the same code. Successful live transcription is unverified until real speech succeeds) |
| 16:27 | `GET /health` | HTTP 200 `{"ok":true}` in 6.4 s (container cold start) |

The live build predates #107, #171–#174 (merged after the deploy). A redeploy is needed for the baked Whisper weights, cancel on disconnect and contract-valid cards.

## 4. Development: who wrote and reviewed what (REQ-DEV-01)

| Role | Tool | In backend core |
|---|---|---|
| Author | Claude Code (Anthropic Opus) in Ahmed's terminal, one worktree per task | every backend-core PR |
| Reviewer | Greptile, on every PR | 21 threads on the 17 PRs below |
| Fixer | `claude-fix` (Claude Sonnet, `.github/workflows/claude-fix.yml`) | 8 fix commits on these PRs |
| Independent spot-check | two read-only reviewer subagents, on merged `main` (~13:20) | the 10 misses in section 5.3 |
| Codex | not used in this area | none |

## 5. Trust evidence (REQ-PROC-01)

### 5.1 Track record of the area

17 merged PRs where Ahmed is the author and every file is in backend core: #78, #84–#86, #88, #92–#94, #96, #98, #104, #106, #107, #171–#174. Counted from the GitHub API with `tools/metrics`'s disposition rules:

| Measure | Value |
|---|---|
| AI review threads | 21 |
| Fixed in a named commit | 20 |
| Rejected with a written reason | 1 |
| Resolved in silence | 0 (15 replies added retroactively on 2026-11-14, each checked against its fix commit) |
| Escalated to a human | 0 as a thread disposition; claude-fix posted "needs human" on 8 of the 17 PRs (#86, #88, #94, #98, #171–#174), and the owner fixed or answered each (checked from the PR comments) |
| claude-fix commits | 8 |
| Time to merge | median 4.8 min, mean 5.9 min, max 17.8 min |
| Reverts (repo-wide) | 0 |

### 5.2 What the AI found, what was refused, and why

| PR | AI finding or proposal | Decision | Why |
|---|---|---|---|
| #174 (REQ-WS-01) | A source URL ending in `\n` passed the filter, then failed `Source` validation | **Fixed** in a named commit, with a test that failed first | real bug, reproduced |
| #174 | A blank caption fails before the fallback | **Not changing** in this PR; filed #175 for the owner of `backend/ai/` | the code is in another owner's area; the owner fixed it in #178 |
| #104 (REQ-PRIV-02) | claude-fix edited `backend/ai/image.py` to stop logging messages | **Reverted** by the owner; filed #108 | cross-owner edit without a handoff, and it broke that owner's test |
| #106 (REQ-STT-01) | The audit suggested steering Whisper with `initial_prompt` | **Rejected after measuring** | with the prompt, Whisper small.en heard "What is this?" in pink noise |
| #82 | Overlap transcription with page reading | **Closed, not planned** | live numbers: it would save ~0.3 s of a ~29 s request |
| #112 / #174 | Sanitise `image_url` as well | **Dropped** | it broke the contracts owner's drift test (`test_non_https_image_url_is_reported`); the contract owner decides |
| #172 (REQ-WS-01) | 5 Greptile findings on cancel-on-disconnect (queued disconnect, history, orphan task, queue memory, cross-session removal) | **Fixed** (bot) plus 2 owner-written tests, each shown to fail without the fix | real concurrency bugs |

### 5.3 What the AI reviewer missed: spot-check on merged code

Two read-only reviewer subagents audited about 800 lines of backend core on `main` (~13:20), after Greptile had passed every PR. The owner reproduced the findings before accepting them. **10 real defects** (filed as 7 issues) were missed by the per-PR review:

| Defect (reproduced) | Fixed in |
|---|---|
| A slow image turned the whole request into `model_timeout` instead of a card without a picture | #104 |
| Logs could contain page text (exception messages from upstream errors) | #104 |
| An unknown page-reader error code crashed the error handler, so the phone got no error at all | #104 |
| Every cold start downloaded 0.5 GB of Whisper weights (73 s), past the phone's 30 s limit | #107 |
| No CPU size on Modal for Whisper | #107 |
| "Drawing", "Explanation" and similar wordings got `stt_failed` | #106 |
| A third simultaneous spoken request failed at once instead of waiting | #173 |
| A phone disconnect did not stop the model calls, and the abandoned question was saved | #172 |
| Spoken-answer clips were not tied to their session | #171 |
| Empty model fields produced schema-invalid cards | #174 |

Of the audit's suggestions, 1 was rejected after measurement (#106 above) and no finding turned out to be false. One report cited line numbers that did not exist (`pipeline.py:338` in a 227-line file); the findings behind them held up when reproduced, which is why each finding is reproduced before it is accepted. This is the only recall measurement we have for the per-PR reviewer: one sample, one area, one day.

## 6. Not checked, and why

- **Spoken request with real speech on the live server:** no recording available yet. Only an empty WAV was sent live.
- **Spoken answer audio on the live server:** `audio_url` was null on the 14:05 card; the cause (model name, billing or base URL) has not been read from the Modal logs, which only the deployer can see.
- **Grounded act/scene/line citations:** #129 (blocked) wires the source loader into answers; until then cards do not cite lines.
- **Glasses hardware:** no rehearsal on the loaned Ray-Ban Display has been recorded in this area.
- **Load:** no load test; one container is the deliberate limit.
- **The current `main` on Modal:** not redeployed since #107 and #171–#174.
