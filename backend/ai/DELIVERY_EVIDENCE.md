# Backend AI: delivery evidence (EVID-C1, #132)

Area owner: Marcus (@Marcus228), `backend/ai/`. Drafted by the lead's agent with Marcus's agreement (board, 2026-11-14); Marcus reviews it and appends his lane updates after #196. Requirements: REQ-PROC-01, REQ-BUILD-01, REQ-DEV-01, REQ-HOST-01.

This file records only what was actually run or read, with its revision and outcome. **Configured** means the model name in code or config. **Reported** means the name a live card put in `models`. Nothing here claims a model ran unless a live card reported it. No keys, prompts, page text, transcripts or user content appear here.

## 1. Revision and platform

| Item | Value |
|---|---|
| Revision checked | `5dbb607` (main, 2026-11-14T20:00Z) |
| CI platform | GitHub Actions `ubuntu-latest`, `ci` run 43635174446 on `5dbb607`: success |
| Local platform (lead) | macOS (darwin 25.5.0). The backend suite was **not** run locally: no backend virtualenv exists here, and creating one needs a package install, which was not authorized for this task |

## 2. Model chain: configured vs reported

Defaults come from `backend/app/config.py` and the `DEFAULT_MODEL_*` constants in `backend/ai/`. The deployed Modal secret can override any of them; its values are not visible in the repo.

| Role | Configured default | Where | Reported by a live card (2026-11-14, `docs/evidence/base-live.md`) |
|---|---|---|---|
| Page reading | `nvidia/nemotron-3.5-super-vl-120b-a12b` at `https://integrate.api.nvidia.com/v1` (`NVIDIA_BASE_URL`) | `ai/page_reader.py`, `app/config.py` | `nemotron-3.5-super-vl` |
| Reading fallback (Nemotron slow or failing, #99) | `gemini-4-hydrogen` (`MODEL_READ_FALLBACK`) | `ai/page_reader.py` | not seen live |
| Reasoning | `gemini-4-argon` (`MODEL_REASON`) | `ai/reasoning.py`, `app/config.py` | `gemini-4-hydrogen`. This differs from the default. Either the deployed secret overrides `MODEL_REASON` or the deployed build is older; not checked |
| Decision routing (#206, off by default: `DYNAMIC_MODEL_ROUTING=false`) | `gemini-decision-1`; tiers `gemini-3.5-flash-lite` / `gemini-4-argon` / `gemini-4-carbon` | `ai/decision.py` | not deployed (merged after the live run) |
| Image | `gemini-nano-banana-2.1` (`MODEL_IMAGE`) | `ai/image.py` | `gemini-nano-banana-2.1`; the image was fetched over HTTPS (HTTP 200, `image/png`, 581,589 bytes) |
| Speech output (backend core, `stt/speak.py`) | `gemini-3.8-flash-tts` (`MODEL_TTS`) | `app/config.py` | `audio_url` null on every live card so far. The base-URL fix is in #206, not yet deployed |

**Attribution limit.** `backend/app/pipeline.py` fills `models.reason` from the configured or routed model name (`resolve_reason_model()` or the decision's `recommended_model`), not from the provider's response. `models.read` comes from the reader that returned the text, so it shows when the fallback was used. `models.image` is `stub` when no image was produced. A reported reasoning name therefore shows what was requested, not a provider-confirmed model ID.

**Nemotron and Verda.** The configured endpoint is NVIDIA's hosted API (`integrate.api.nvidia.com`). Nothing in the repo points at a Verda-hosted endpoint, and no Verda inference has been recorded. Before any Verda claim, D (the lead) needs:
1. The actual base URL the deployed secret uses for `NVIDIA_BASE_URL`, from the deployer (@Marcus228). Give the host only, never the key.
2. Verda's written confirmation that this endpoint counts as Verda inference for their challenge.
3. A dated live request whose card reports the Nemotron reader, not the Gemini fallback.

## 3. Source grounding (REQ-SRC-01)

| Item | Evidence |
|---|---|
| Source text | `ai/data/plays/hamlet.json`: *Hamlet*, William Shakespeare, 5 acts, `https://www.gutenberg.org/ebooks/1524`, "Public Domain (Project Gutenberg License)" |
| Loader | `ai/source_loader.py` (#80, sped up in #179); 22 tests in `tests/test_source_loader.py`, including unknown books |
| Sample frames | `ai/sample_frames/`: `hamlet_act1_scene2.jpg`, `blank_page.jpg`, `blurry_empty.jpg`, each with its expected text in a `.txt` file |
| Accuracy script | `ai/measure_accuracy.py` (#74, REQ-READ-01); 7 tests. It runs offline with the stub reader, and live accuracy needs a key. **No live accuracy figure is recorded** |
| Live result | **Grounding miss.** The live card for the Act 1 Scene 2 sample said Act 1 **Scene 1** and cited Folger/MIT pages (the reasoning defaults), not the Gutenberg text. The loader exists but `pipeline.py` does not pass its matches to the card yet: that is #129, after Marcus's lane #194 |

## 4. Tests and build (REQ-BUILD-01)

CI runs `backend/test.sh` (unittest discovery over `backend/tests/`, dependencies from `backend/requirements.txt` in `backend/.venv`). On `5dbb607`: **262 tests, OK**. The same run had `ios/` with 6 tests OK, and `contracts/` with 40 tests OK and 2 live tests skipped.

AI test files (test functions counted with `grep "def test_"` at `5dbb607`):

| File | Tests | Covers |
|---|---|---|
| `test_page_reader.py` | 19 | Nemotron reader, `no_text_found` |
| `test_page_reader_fallback.py` | 26 | Gemini fallback when Nemotron is slow or fails |
| `test_reasoning.py` | 18 | book session and reasoning |
| `test_image.py` | 25 | image generation, billing check, no secret in errors |
| `test_source_loader.py` | 22 | passage lookup, unknown books |
| `test_measure_accuracy.py` | 7 | accuracy script |
| `test_decision.py` | 19 | decision routing (#206) |

All of these use stub or mocked clients; none calls a provider. Live model behavior is covered only by the live runs in section 2.

## 5. Development and review (REQ-DEV-01, REQ-PROC-01)

**Who wrote what.** 10 merged PRs touch `backend/ai/`: #74, #75, #77, #80, #105, #176, #178, #179 and #206 by @Marcus228, and #99 by @moterodiaz. Commit trailers name Claude Sonnet 5.5 (the `claude-fix` bot) on 9 of them, and factory-droid on #99. Marcus posts as "Marcus's Antigravity". **Codex: no Codex contribution is recorded in this area**, so this file supports no Codex claim.

**Area track record** (`tools/metrics --areas`, PRs #67 onwards, measured 2026-11-14T20:04Z):

| Measure | Value |
|---|---|
| PRs merged in the area | 10 |
| Median time to merge | 15.7 min |
| AI review threads | 47 |
| Fixed in a named commit | 27 |
| Rejected with a reason | 0 |
| Resolved in silence | 20, mostly on the early PRs #74–#80 (before the written-reply rule) |
| Escapes | 1 (none open); trust: earned |

Per PR (threads / `claude-fix` commits / minutes to merge): #74 7/2/30, #75 11/4/43, #77 12/3/79, #80 9/3/89, #99 2/0/14, #105 0/0/3, #176 1/1/4, #178 1/1/4, #179 2/1/18, #206 2/1/7.

**Misses found after review:**
- Raw upstream error messages could reach the logs from the image, page-reader and reasoning clients (#108), fixed in #176.
- A blank caption failed before the fallback (#175, found on #174), fixed in #178.
- The live grounding miss in section 3 is still open (#129).

## 6. Not checked, and why

- **Live reading accuracy**: no keyed run of `measure_accuracy.py` is recorded.
- **Gemini reading fallback live**: never triggered on a recorded live request.
- **Decision routing live (#206)**: merged after the live run, off by default, and not deployed.
- **Spoken answer audio live**: `audio_url` null; the #206 fix needs a redeploy.
- **Deployed secret values** (`MODEL_*`, `NVIDIA_BASE_URL`): only the deployer can see them; asked above for the host and model names only.
- **Verda eligibility**: no confirmation and no Verda endpoint (section 2).
- **Local test run on the lead's machine**: skipped (no install authorized); CI is the record.

## 7. Handoff to D (the lead)

Lane updates from Marcus (#194–#199) will be appended here after #196. Gate tasks #135–#138 can cite this file for the AI area. It is evidence for review, not a gate acceptance.
