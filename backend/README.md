# Backend

FastAPI orchestrator for MetaLab (PRD section 4). Tests: `backend/test.sh`.

## Run locally

```sh
cd backend && .venv/bin/pip install -r stt/requirements.txt   # once: Whisper, for spoken commands
.venv/bin/uvicorn app.main:app --reload                       # after backend/test.sh has built .venv
```

Without keys the stages run as offline stubs; typed `text` commands work without Whisper.

## Deploy on Modal

One-time setup:

1. `uv tool install modal`, then `modal setup` (browser login).
2. Create the secret the app reads (names in `backend/.env.example`):
   ```sh
   modal secret create metalab NVIDIA_API_KEY=... NVIDIA_BASE_URL=... MODEL_READ=... GEMINI_API_KEY=...
   ```

Deploy from the repo root:

```sh
modal deploy backend/app/modal_app.py
```

It prints a URL like `https://<workspace>--metalab-web.modal.run`. Then:

- Phone app: `wss://<workspace>--metalab-web.modal.run/ws`
- Health check: `curl https://<workspace>--metalab-web.modal.run/health` returns `{"ok":true}`
- Add `IMAGE_BASE_URL=https://<workspace>--metalab-web.modal.run` to the `metalab` secret, then deploy again. Generated images and spoken answers are both served from it; without it `image_url` and `audio_url` stay null.

`backend/.env` is never uploaded; keys come only from the Modal secret. A missing required key stops the container when it starts (check `modal app logs metalab`), not `modal deploy` itself. The Whisper weights are baked into the image at build time, so the first deploy takes a few minutes longer. For the demo, set `min_containers=1` in `modal_app.py` so the first request does not wait for a cold start (this keeps one container running and billed).

---

## AI Architecture & Gemini Stack (Paid Tier 3)

The backend features a fully integrated Gemini multimodal stack with local grounding and single-pass decision routing:

### 1. Dynamic Decision Routing (`backend/ai/decision.py`)
- Single-pass evaluation using Gemini Decisions API (`gemini-decision-1` on `v1beta` via `client.aio.decisions.create`).
- Classifies user intent into structured dimensions with a target latency of ~150–250 ms and 0 output tokens (live measurement pending):
  - `action`: `explain`, `draw`, `who_is_this`, `question`, `clarify`.
  - `task_tier`: `fast` (`gemini-3.5-flash-lite`), `balanced` (`gemini-4-argon`), or `deep` (`gemini-4-carbon`).
  - `needs_image`: boolean flag indicating whether visual illustration should accompany the answer.
  - `speak_only`: boolean flag that skips illustration generation; the client still shows the card's title and caption.
- Graceful heuristic fallback: If the Decisions API is unavailable, times out (`DECISION_TIMEOUT_S=2.0`), or returns low confidence (<0.50), the system falls back to regex/keyword command matching (`stt.match_command`) without failing the turn.

### 2. Model Tier Routing & Configuration
- `MODEL_REASON` (default `gemini-4-argon`): Maintains strict backward compatibility with WebSocket contract `modelInfo.reason` (non-empty string).
- `MODEL_REASON_FAST` (default `gemini-3.5-flash-lite`): Fast factual definitions, line translations, and quick lookups.
- `MODEL_REASON_DEEP` (default `gemini-4-carbon`): Deep thematic analysis, soliloquy dissection, and literary synthesis.
- `DYNAMIC_MODEL_ROUTING` (default `false`): Additive flag enabling dynamic model selection per query based on `task_tier`. The resolved model identifier is populated directly into `card.models["reason"]`.
- `MODEL_DECISION` (default `gemini-decision-1`): Model identifier for intent routing.

### 3. Local Hamlet Grounding (`backend/ai/source_loader.py` + `backend/ai/reasoning.py`)
- Full text of *Hamlet* (Project Gutenberg #1524, 1,012 KB) indexed in memory by `source_loader.py` (`find_passage`, `locate_passage`).
- Auto-grounding via `reasoning.ground_passage(page_text)` runs locally in sub-milliseconds before Gemini API calls, injecting exact canonical Act/Scene/Line coordinates into the prompt.
- Eliminates model hallucination and guesswork on play coordinates, intended to reduce the earlier ~10.1s reasoning latency (target only; live measurement pending).
- Ungrounded passages (e.g. non-Hamlet books or unmatched text) proceed through an explicit no-source fallback path (`sources: []`), guaranteeing no invented citations.
- Mid-book classification: `BookSession.candidate_books` and Decision API track book identity across turns; rare clarification gate (`action == "clarify"`) triggers only when both local score < 0.65 and book match confidence < 0.70.

### 4. Soft Visual Style Conditioning (`backend/ai/image.py`)
- Selected style presets (e.g., oil painting, sketch, dramatic lighting) are formatted into display prompts as soft stylistic suggestions.
- Preserves optical see-through display constraints: pure `#000000` black background and luminous high-contrast foreground required for Ray-Ban Meta waveguide lenses.
- Maintains `gemini-nano-banana-2.1` as fast local/optional image fallback alongside cloud generators.

### 5. Modular Checks & Anti-Spoiler Guard (planned under #197–#199; not yet used by the pipeline)
- Modular question registry (`DecisionQuestionSpec`) allows toggleable evaluation passes.
- `DECISION_ENABLE_SPOILER_CHECK` (default `false`, planned: spoiler results are not yet used): Evaluates `requires_future_plot` / `answerable_from_seen` against reading position (`session.max_position`) to prevent narrative spoilers for students reading sequentially.

### 6. Speech-to-Text Engines (`backend/stt/engine.py`)
- Controlled via `STT_ENGINE`:
  - `whisper` (default): Local `faster-whisper` (`small.en`) running inside Modal container or local host.
  - `gemini` (planned under #197–#199; not yet implemented, transcription currently always loads Whisper): Cloud-based Gemini transcription (`gemini-3.5-transcribe`), with domain-specific Shakespeare vocabulary biasing.

### 7. Gemini TTS & Audio URL Resolution (`backend/stt/speak.py`)
- `MODEL_TTS` (default `gemini-3.8-flash-tts`, voice `Kore`): Generates 24 kHz 16-bit mono PCM audio for spoken answers.
- Fix for live Modal `audio_url: null`: Audio clip URLs require `IMAGE_BASE_URL` configured in the `metalab` Modal secret (e.g., `IMAGE_BASE_URL=https://<workspace>--metalab-web.modal.run`). `_resolve_base_url()` enforces `https://` schema. Without `IMAGE_BASE_URL`, `audio_url` is returned as `null` and the client uses system on-device TTS fallback.

### 8. Privacy-Preserving Telemetry (`REQ-PRIV-02`)
- Structured telemetry (`metalab.latency` / `metalab.telemetry`) currently records stage durations only (`StageTimer`). Model distribution counts, tier usage (`fast`, `balanced`, `deep`), and fallback occurrences are planned under #197–#199.
- Strictly content-free: logs contain only model identifiers and integer metrics. User speech transcripts, page text, and audio clips are never logged.

