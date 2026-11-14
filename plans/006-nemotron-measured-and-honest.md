# Plan 006: The Nemotron claim is backed by committed measurements, a truthful model note, and a demo-safe budget

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- backend/ai/measure_accuracy.py backend/ai/page_reader.py backend/ai/sample_frames/ backend/.env.example README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition. **PR #99 (Gemini fallback for page
> reading) changes `page_reader.py` and `pipeline.py`; wait for it to merge, then
> re-read those files before Step 3.**

## Status

- **Priority**: P1 for the Nemotron track; P2 for the product
- **Effort**: M (2–4 hours plus endpoint time; one real-endpoint run takes minutes per frame)
- **Risk**: LOW for code (benchmark script + docs); the decision in Step 3 is a product call for the lead
- **Depends on**: PR #99 merged (for Step 3); a working `NVIDIA_API_KEY`/`NVIDIA_BASE_URL`/`MODEL_READ` for Steps 1–2
- **Category**: direction / docs / tests
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

"Best use of Nemotron" will be judged on whether Nemotron does real work in the
demo and whether the team can show it. Today:

- The only Nemotron endpoint the team can reach answers in **260–275 s per
  request** (board post 10:16 UTC: "EVERY request takes ~260-275 s, even a
  3-token reply"). The backend's stage timeout is **25 s**
  (`backend/app/pipeline.py:43`). In production every page read times out.
- PR #99 (open at planning time) adds `read_page_with_fallback`: Nemotron gets
  `READ_FALLBACK_AFTER_S` = **8 s**, then Gemini reads the frame. With the
  current endpoint Nemotron never finishes, so every live card will say
  `models.read: gemini-4-hydrogen`. A judge who asks "show me Nemotron reading
  the page" will see Gemini.
- The accuracy script `backend/ai/measure_accuracy.py` exists, but the only
  numbers anyone has seen are the **stub** run that `backend/test.sh` prints at
  the end of every CI log: `Overall Accuracy: 100.00%` (the stub echoes the
  expected text). No real measurement is committed; the one real result
  ("transcribed a Hamlet page word-perfect and named Act III Sc I") lives in a
  board comment.
- The mandatory submission note template (strategy doc §5) names
  `https://integrate.api.nvidia.com/v1`; the deployed base URL is a Verda
  container. A note that does not match the code is worse than no note.

This plan does not make the endpoint faster. It makes the Nemotron story
*true and measured*: committed per-frame accuracy and latency from the real
endpoint, a README note that matches the deployed config, a `models.read` value
the judges can see, and an explicit, lead-approved budget decision.

## Current state

- `backend/ai/page_reader.py` — `NemotronClient.complete()` (lines 175–214) posts
  an OpenAI-style `chat/completions` with the frame as a `data:` URL and
  `"chat_template_kwargs": {"enable_thinking": False}`; `timeout=30.0` default
  (line 161); `_resolve_config()` (132–150) reads `NVIDIA_API_KEY`,
  `NVIDIA_BASE_URL`, `MODEL_READ` from env, then `app.config`.
- `backend/ai/measure_accuracy.py` — `evaluate_sample` (139–186) computes
  character/word accuracy via Levenshtein against `sample_frames/<id>.txt`;
  `run_benchmark` (188–234); `main()` (261–289) has `--samples-dir`, `--use-stub`,
  `--json`; prints `*** SIMULATED ... ***` when the stub is used. **It records no
  latency** (`grep -n "perf_counter\|latency" backend/ai/measure_accuracy.py` → nothing).
- `backend/ai/sample_frames/manifest.json` — 4 frames: `hamlet_act3_scene1`,
  `hamlet_act1_scene2` (text), `blank_page`, `blurry_empty` (no text). No
  committed results file.
- `backend/app/pipeline.py:171-175` — `models.read` is `page_reader._resolve_config()[2]`
  when a key is set, else `"stub"`. After #99 it should come from the `PageText.model`
  attribute (re-read after merge).
- `backend/.env.example` lines 13–14 document `NVIDIA_BASE_URL` and `MODEL_READ`.
- `ios/MetaLab/RootView.swift:123,259-260` — the phone shows `models.reason` and
  `models.image` but **not** `models.read`. (iOS is out of scope here; see Maintenance.)
- Team process: `backend/ai/` is owned by `@Marcus228`; `backend/app/` by `@Ahm3d-KA`.

## Commands you will need

| Purpose | Command (from `backend/`) | Expected |
|---|---|---|
| Tests | `./test.sh` | `OK` |
| Stub benchmark (no key) | `.venv/bin/python -m ai.measure_accuracy --use-stub` | table + `*** SIMULATED` banner |
| Real benchmark (key + base URL + model exported) | `.venv/bin/python -m ai.measure_accuracy --json > /tmp/nemotron-results.json` | JSON with 4 samples, no SIMULATED banner |
| Check the deployed values (names only, never print the key) | `env \| grep -E '^(NVIDIA_BASE_URL|MODEL_READ)='` | the Verda URL and model id |

## Scope

**In scope**:
- `backend/ai/measure_accuracy.py` (add latency per sample and endpoint metadata to the report)
- `backend/tests/test_measure_accuracy.py` (adjust for the new fields)
- `backend/ai/sample_frames/RESULTS.md` (create: committed real-endpoint results)
- `backend/ai/sample_frames/` (add 2–6 more real glasses frames + expected `.txt` if the iOS "keep a sample frame" toggle has produced any; otherwise skip)
- `README.md` "Models used" section (coordinate with plan 001; one of the two PRs owns the wording)
- `backend/.env.example` (document `READ_FALLBACK_AFTER_S` once #99 lands, with the chosen demo value)

**Out of scope**:
- Making the Nemotron endpoint faster (vendor/booth conversation, not code).
- `backend/ai/page_reader.py` logic beyond what #99 lands — do not add a second fallback.
- `ios/**` — showing `models.read` on the phone belongs to the iOS owner (file a task).
- Keeping frames after the card to run Nemotron in the background: this would
  break REQ-PRIV-01 (`test_no_frame_or_audio_is_kept_after_the_card`). Not without
  a lead decision recorded in the PRD.

## Git workflow

Follow `AGENTS.md`: task issue (REQ-READ-01; PRD §4, §9 risk C1) → claim →
`tools/wt N-nemotron-measured` → PR `Closes #N` → auto-merge → board post.
Commit style: `test(ai): measure Nemotron accuracy and latency on real frames; commit results`,
`docs: Nemotron model note matches the deployed endpoint`.

## Steps

### Step 1: Record latency and endpoint metadata in the benchmark

In `backend/ai/measure_accuracy.py`:
1. Add `latency_s: float` to `SampleResult` (dataclass at ~line 76) and
   `endpoint_host: str`, `model: str`, `thinking: str`, `measured_at: str` to
   `BenchmarkReport` (~line 87).
2. In `evaluate_sample`, wrap the `client.complete(...)` call with
   `t = time.perf_counter()` … `latency_s = round(time.perf_counter() - t, 2)`;
   include it on success *and* on `NoTextFoundError`/errors.
3. In `run_benchmark`, fill the metadata: host = `urllib.parse.urlparse(base_url).netloc`
   (never the key), `model` from `_resolve_config()`, `thinking="disabled"`,
   `measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds")`.
4. In `format_report_table`, add a `Latency` column and a header line
   `Endpoint: <host>  Model: <model>  Thinking: disabled  Measured: <ts>`.
   Keep the `*** SIMULATED ***` banner for `--use-stub`.
5. Update `backend/tests/test_measure_accuracy.py` (`test_run_benchmark_with_stub_client`,
   `test_main_cli`) for the new fields; add one assertion that `latency_s >= 0`
   on every result.

**Verify**: `cd backend && ./test.sh` → `OK`; `.venv/bin/python -m ai.measure_accuracy --use-stub | head -3` shows the `Endpoint:` header and the SIMULATED banner.

### Step 2: Run the real benchmark and commit the results

With `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `MODEL_READ` exported (from the Modal
secret owner; never commit or paste them):

```sh
cd backend && .venv/bin/python -m ai.measure_accuracy --json > /tmp/nemotron-results.json \
  && .venv/bin/python -m ai.measure_accuracy > /tmp/nemotron-results.txt
```
Expect 4 samples × up to ~5 min each; run it in the background and keep working.
Then write `backend/ai/sample_frames/RESULTS.md`:

```markdown
# Nemotron 3.5 Super VL reading accuracy on saved frames

Measured: <measured_at>  · Endpoint host: <host>  · Model: <model>  · Thinking: disabled
Script: `backend/.venv/bin/python -m ai.measure_accuracy` (real client; the stub run in CI prints a SIMULATED banner and is not a measurement).

| Frame | Has text | Char acc | Word acc | Blank detected | Latency |
|---|---|---|---|---|---|
| hamlet_act3_scene1 | yes | 98.1% | 96.0% | – | 262 s |
| … | | | | | |

Notes: <what was wrong in the OCR, if anything; whether blank/blurry frames were rejected; the latency vs the 25 s stage budget and the READ_FALLBACK_AFTER_S budget>.
```
Fill with the real numbers from `/tmp/nemotron-results.txt`. If more real glasses
frames exist (PRD §9 B1 "saves real frames"; iOS "Keep a sample frame"), add them
to `sample_frames/` with their expected `.txt` and `manifest.json` entries first,
then benchmark all of them.

**Verify**: `test -f backend/ai/sample_frames/RESULTS.md && grep -c "^| hamlet" backend/ai/sample_frames/RESULTS.md` → ≥ 2; the file contains no `nvapi-` or key fragments (`grep -ci "nvapi\|api_key" backend/ai/sample_frames/RESULTS.md` → `0`).

### Step 3: Decide the demo budget with the lead, then encode it

After #99 merges, re-read `page_reader.read_page_with_fallback` and the
`READ_FALLBACK_AFTER_S` default. Post on the board (tag `@moterodiaz`,
`@Marcus228`) with the measured latency and ask for one of:

- **A. Nemotron-first (if the booth provides a faster endpoint, e.g. < 15 s):**
  set `READ_FALLBACK_AFTER_S` to 20 in the Modal secret, keep `STAGE_TIMEOUT_S`
  25. Nemotron reads live; Gemini only on failure.
- **B. Gemini-first live, Nemotron measured offline (current endpoint):** keep
  8 s; the card truthfully reports `models.read`; the pitch and README say
  "Nemotron reads the page when the endpoint answers within budget; on the
  shared hackathon endpoint (≈4.5 min/request) the demo falls back to Gemini
  and reports it on the card; accuracy measured offline, see RESULTS.md".

Encode the decision: add `# READ_FALLBACK_AFTER_S=<value>` with a comment to
`backend/.env.example`, and make sure `models.read` in the card reflects the
model that *actually* produced the text (after #99 this is `PageText.model`;
`backend/tests/test_ws.py::test_models_read_is_model_name_on_real_reader_path`
covers the Nemotron case — add a sibling test for the fallback case if #99 did not).

**Verify**: `grep -n "READ_FALLBACK_AFTER_S" backend/.env.example` → 1 line with the chosen value; `cd backend && ./test.sh` → `OK`.

### Step 4: Make the public note truthful

In `README.md` "Models used" (plan 001 creates it; if plan 001 has not merged,
put the same text in `backend/README.md` under a new `## Models used` heading and
tell plan 001's executor on the board):

> **Models used.** MetaLab uses NVIDIA Nemotron 3.5 Super VL (`<MODEL_READ as deployed>`, served at `<host as deployed>`, OpenAI-compatible API, thinking disabled) to read the page photo captured by the glasses. On the endpoint available during the hackathon a read takes ≈<N> s (see `backend/ai/sample_frames/RESULTS.md`); when it exceeds the per-request budget the backend falls back to Gemini `<MODEL_READ_FALLBACK>` and the card's `models.read` field reports which model read the page. Gemini `<MODEL_REASON>` handles reasoning, `<MODEL_IMAGE>` the illustration, `<MODEL_TTS>` speech. Nemotron output is text only and is passed to the reasoning step. Frames are processed in memory and not stored.

Copy the same paragraph into the Junction submission form (human action; note it in the PR body).

**Verify**: `grep -c "RESULTS.md" README.md backend/README.md` → ≥ 1; no `<...>` placeholders remain (`grep -cE "<[A-Za-z_ ]+>" README.md` → `0`).

### Step 5: File the iOS follow-up and open the PR

File a task issue for `ios/` (owner `@maksymmatviievskyi`): "show `models.read`
next to reason/image on the card (RootView.swift:259-260)", REQ-READ-01. Open
this plan's PR per "Git workflow"; attach `/tmp/nemotron-results.txt` content in
the PR body (numbers only).

## Test plan

- `backend/tests/test_measure_accuracy.py`: existing tests adjusted for the new
  fields; new assertion `latency_s >= 0` for every result; `test_main_cli` still
  prints the SIMULATED banner with `--use-stub`.
- No network in tests: the stub client path stays the only CI path.
- `cd backend && ./test.sh` → `OK`.

## Done criteria

- [ ] `grep -n "latency_s" backend/ai/measure_accuracy.py` → ≥ 2 matches
- [ ] `backend/ai/sample_frames/RESULTS.md` exists, dated today, with real latency and accuracy per frame and no secrets
- [ ] `README.md` (or `backend/README.md`) "Models used" names the deployed host and model and links RESULTS.md
- [ ] `backend/.env.example` documents `READ_FALLBACK_AFTER_S` with the lead's chosen value
- [ ] `cd backend && ./test.sh` exits 0
- [ ] An iOS task issue for `models.read` exists
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- No working Nemotron credentials are available to you within 30 minutes of
  asking on the board: do Step 1 and Step 4 with the latency figure from the
  10:16 board post, label it "reported, not re-measured", and leave Step 2 open.
- The real benchmark returns `no_text_found` for the two text frames: the
  endpoint or prompt is broken — report the raw response shape, do not tune the
  prompt in this plan.
- PR #99 is not merged by the time you reach Step 3: do Steps 1, 2, 4, 5 and
  leave Step 3 for after the merge (say so in the PR body).
- Someone proposes keeping the frame after the card to run Nemotron later: that
  changes the privacy promise (PRD §6, REQ-PRIV-01); it needs the lead and a PRD edit first.

## Maintenance notes

- Re-run the benchmark whenever `NVIDIA_BASE_URL`/`MODEL_READ` change, and
  update RESULTS.md with the new date; the submission note quotes it.
- Reviewer: check that nothing in RESULTS.md or the README overstates the live
  path (if option B was chosen, the words "falls back to Gemini" must be there).
- Direction (not in this plan): Nemotron can do more than OCR — ask it for a
  JSON with `text`, `is_book_page`, `speakers`, `page_number`; that would make
  the "why Nemotron, not Gemini, for reading" answer stronger than "it's the
  sponsor's model".
