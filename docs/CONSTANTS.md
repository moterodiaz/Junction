# Constants, defaults and environment overrides

This file lists the runtime, configuration, model, timeout and limit constants in MetaLab, with
their default value, the environment variable that overrides them (if any), where they live, and
what they do. It is a reference, not a source of truth: **the code wins**. If a value here
disagrees with the file in the Location column, trust the code and fix this table.

Keeping it current:

- When you add, rename or change a constant or an environment variable, update its row in the same PR.
- Locations are paths only (no line numbers), so moving code within a file needs no edit here.
- Secrets are listed by name only. Never put a key, token or voice ID value in this file.
- The full list of variables the backend reads is also in `backend/.env.example`, and validation of
  deployed values is in `config_problems()` in `backend/app/config.py`.

"Env override: none" means the value is fixed in code. On Modal, env overrides come from the
`metalab` Modal secret; locally, export them in your shell (the backend does not read `.env` files).

## Backend config and secrets

| Constant | Default | Env override | Location | Description |
|---|---|---|---|---|
| `MODAL_SECRET_NAME` | `"metalab"` | none | `backend/app/config.py`, `backend/app/modal_app.py` | Modal secret that holds the backend's environment variables. |
| `ELEVENLABS_SECRET_NAMES` | `("ELEVEN_LABS_KEY", "ELEVVOICE_ID")` | none | `backend/app/config.py`, `backend/app/modal_app.py` | Extra Modal secrets (names only) that set the ElevenLabs key and voice ID; deploy fails if either is missing. |
| `REQUIRED` | `("NVIDIA_API_KEY", "GEMINI_API_KEY")` | the listed variables (secrets) | `backend/app/config.py` | Variables the container needs to start on Modal; locally, offline stubs run without them. |
| `OPTIONAL_SECRETS` | `("ELEVEN_LABS_API_KEY", "ELEVEN_LABS_VOICE_ID")` | the listed variables (secrets) | `backend/app/config.py` | ElevenLabs speaks the answer only when both are set (read in `backend/stt/speak.py`); otherwise Gemini TTS is used. |
| `DEFAULTS` | dict of the model and STT defaults below | per key | `backend/app/config.py` | Optional overrides and their defaults (PRD section 4, Models). |
| `NVIDIA_BASE_URL` | `"https://integrate.api.nvidia.com/v1"` | `NVIDIA_BASE_URL` | `backend/app/config.py`, `backend/ai/page_reader.py` | Nemotron API base URL (module default `DEFAULT_NVIDIA_BASE_URL`). |
| `PHONE_IDLE_LIMIT_S` | `30.0` | none | `backend/app/config.py` | Phone's idle limit; `STAGE_TIMEOUT_S` must stay below it. |
| `PHONE_TOTAL_LIMIT_S` | `90.0` | none | `backend/app/config.py` | Phone's total request limit; `REQUEST_TIMEOUT_S` must stay below it. |
| `DEFAULT_MAX_CONNECTIONS` | `20` | `WS_MAX_CONNECTIONS` (whole number >= 1) | `backend/app/config.py` | Maximum concurrent `/ws` connections; matches `@modal.concurrent(max_inputs=20)`. |
| `WS_AUTH` | off | `WS_AUTH` (`on`/`off`) | `backend/app/config.py`, `backend/app/main.py` | Optional bearer auth on the `/ws` handshake; on without a token refuses every handshake. |
| `WS_AUTH_TOKEN` | empty (secret) | `WS_AUTH_TOKEN` | `backend/app/config.py` | Bearer token checked when `WS_AUTH` is on. Secret: name only. |
| `WS_TRUST_FORWARDED_PROTO` | off | `WS_TRUST_FORWARDED_PROTO` (`on`/`off`) | `backend/app/config.py` | Whether `X-Forwarded-Proto: https` counts as WSS (turn on behind Modal's proxy). |
| `MODAL_MIN_CONTAINERS` | `0` | `MODAL_MIN_CONTAINERS` (read by `modal deploy` from your shell, not the secret) | `backend/app/modal_app.py` | Warm containers kept running; `1` avoids a cold start on demo day (and is billed). |
| `max_containers` | `1` | none | `backend/app/modal_app.py` | One container only, because generated images and audio clips live in process memory. |
| `max_inputs` | `20` | none | `backend/app/modal_app.py` | Concurrent requests per container (`@modal.concurrent`). |
| `cpu` | `2.0` | none | `backend/app/modal_app.py` | Modal CPU cores for the web function (Whisper `small.en` needs about one full core). |
| `memory` | `2048` (MiB) | none | `backend/app/modal_app.py` | Modal memory for the web function. |
| `scaledown_window` | `300` (s) | none | `backend/app/modal_app.py` | How long an idle container stays warm after a request. |
| `timeout` | `600` (s) | none | `backend/app/modal_app.py` | Modal function timeout. |
| `REMOTE_BACKEND` | `"/root/backend"` | none | `backend/app/modal_app.py` | Path of the backend code inside the container. |
| `STT_LOG_DIR` | `"/stt-logs"` | none | `backend/app/modal_app.py` | Mount path of the `metalab-stt-logs` Modal Volume (STT debug log). |

Not read by the app: `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` (secrets) are used by the Modal CLI
to deploy; see `backend/.env.example`.

## Pipeline, WebSocket and telemetry

| Constant | Default | Env override | Location | Description |
|---|---|---|---|---|
| `STAGE_TIMEOUT_S` | `25.0` | `STAGE_TIMEOUT_S` (must be < 30 and <= `REQUEST_TIMEOUT_S`) | `backend/app/pipeline.py`, `backend/app/config.py` | Per-stage deadline; running out becomes `model_timeout`. Parsed at import time. |
| `REQUEST_TIMEOUT_S` | `85.0` | `REQUEST_TIMEOUT_S` (must be < 90) | `backend/app/pipeline.py`, `backend/app/config.py` | Whole-request deadline; running out becomes `model_timeout`. Parsed at import time. |
| `SESSION_IDLE_TTL_S` | `3600.0` | `SESSION_IDLE_TTL_S` | `backend/app/pipeline.py` | Idle book sessions older than this are forgotten. |
| `_STT_WORKERS` | `2` | none | `backend/app/pipeline.py` | Threads (and slots) available for speech-to-text at once. |
| `STT_SLOT_POLL_S` | `0.05` | none | `backend/app/pipeline.py` | How often a waiting request checks for a free STT slot. |
| `_MAX_PENDING_DRAWS` | `2` | none | `backend/app/pipeline.py` | Background picture draws per session; beyond this a card waits for its picture. |
| `DYNAMIC_MODEL_ROUTING` | `"false"` | `DYNAMIC_MODEL_ROUTING` | `backend/app/pipeline.py`, `backend/app/config.py` | Enables Gemini Decisions API routing of each request. |
| `MAX_QUEUED_FRAMES` | `4` | none | `backend/app/main.py` | Maximum queued outbound WebSocket frames per connection. |
| `MAX_QUEUED_BYTES` | `32 * 1024 * 1024` (32 MiB) | none | `backend/app/main.py` | Maximum queued outbound WebSocket bytes per connection. |
| `DEFAULT_STAGES` | `("decision", "read", "reason", "image", "tts")` | none | `backend/app/latency.py` | Stages tracked by latency and model-choice telemetry. |

## AI modules

| Constant | Default | Env override | Location | Description |
|---|---|---|---|---|
| `MODEL_READ` | `"nvidia/nemotron-3.5-super-vl-120b-a12b"` | `MODEL_READ` | `backend/app/config.py`, `backend/ai/page_reader.py` | Primary page-reading VLM (module default `DEFAULT_MODEL_READ`). |
| `NemotronClient` timeout | `30.0` s | none | `backend/ai/page_reader.py` | HTTP timeout of the Nemotron page-reading call (the stage deadline still applies). |
| `DEFAULT_MODEL_READ_FALLBACK` | `"gemini-4-hydrogen"` | `MODEL_READ_FALLBACK` | `backend/ai/page_reader.py` | Gemini VLM that reads the page when Nemotron fails or is too slow. |
| `DEFAULT_READ_FALLBACK_AFTER_S` | `3.0` | `READ_FALLBACK_AFTER_S` | `backend/ai/page_reader.py` | How long Nemotron gets before the Gemini fallback starts on the same frame. |
| `GeminiPageReader` timeout | `15.0` s | none | `backend/ai/page_reader.py` | HTTP timeout of the Gemini fallback page-reading call. |
| `GEMINI_BASE_URL` | `"https://generativelanguage.googleapis.com/v1beta"` | none | `backend/ai/page_reader.py`, `backend/ai/reasoning.py` | Gemini REST base URL used by the page-reading fallback and reasoning. |
| `MODEL_REASON` | `"gemini-4-argon"` | `MODEL_REASON` | `backend/app/config.py`, `backend/ai/reasoning.py`, `backend/ai/decision.py` | Book reasoning model and balanced routing tier (module defaults `DEFAULT_MODEL_REASON`, `DEFAULT_MODEL_BALANCED`). |
| `HttpGeminiClient` timeout | `15.0` s | none | `backend/ai/reasoning.py` | HTTP timeout of the Gemini reasoning call. |
| `MODEL_REASON_FAST` | `"gemini-3.5-flash-lite"` | `MODEL_REASON_FAST` | `backend/app/config.py`, `backend/ai/decision.py` | Fast reasoning tier when routing is on (module default `DEFAULT_MODEL_FAST`). |
| `MODEL_REASON_DEEP` | `"gemini-4-carbon"` | `MODEL_REASON_DEEP` | `backend/app/config.py`, `backend/ai/decision.py` | Deep reasoning tier when routing is on (module default `DEFAULT_MODEL_DEEP`). |
| `MODEL_DECISION` | `"gemini-decision-1"` | `MODEL_DECISION` | `backend/app/config.py`, `backend/ai/decision.py`, `backend/app/pipeline.py` | Gemini Decisions API routing model (module default `DEFAULT_MODEL_DECISION`). |
| `DEFAULT_DECISION_TIMEOUT_S` | `2.0` | `DECISION_TIMEOUT_S` (can only lower it; clamped to 0.01-2.0 s) | `backend/ai/decision.py` | Deadline of the routing call; on timeout the heuristic fallback decides. |
| `MIN_CONFIDENCE_THRESHOLD` | `0.5` | none | `backend/ai/decision.py` | Routing answers below this confidence fall back to the heuristic. |
| `DECISION_ENABLE_SPOILER_CHECK` | `"false"` | `DECISION_ENABLE_SPOILER_CHECK` | `backend/ai/decision.py`, `backend/ai/reasoning.py` | Turns on the anti-spoiler guard. |
| `MODEL_IMAGE` | `"gemini-nano-banana-2.1"` | `MODEL_IMAGE` | `backend/app/config.py`, `backend/ai/image.py`, `backend/app/pipeline.py` | Image generation model (module default `DEFAULT_MODEL_IMAGE`). |
| `MAX_STORED_IMAGES` | `200` | none | `backend/ai/image.py` | In-memory generated images kept before the oldest are evicted. |
| `_DEFAULT_IMAGE_WAIT_S` | `25.0` | `IMAGE_WAIT_S` | `backend/ai/image.py` | How long `GET /img/<id>.png` waits for a picture still being drawn. |
| `_DEFAULT_SESSION_TTL` | `3600.0` | `IMAGE_SESSION_TTL_SECONDS` | `backend/ai/image.py` | Images of sessions idle longer than this are swept. |
| `_UNOWNED_RESERVATION_TTL_S` | `600.0` | none | `backend/ai/image.py` | Abandoned image reservations without a session expire after this. |
| `IMAGE_BASE_URL` | unset | `IMAGE_BASE_URL` | `backend/ai/image.py`, `backend/stt/speak.py` | Public HTTPS base for `image_url` and `audio_url`; unset leaves both null. |

## Speech

| Constant | Default | Env override | Location | Description |
|---|---|---|---|---|
| `DEFAULT_ENGINE` | `"whisper"` | `STT_ENGINE` (`whisper` or `gemini`) | `backend/stt/engine.py` | Speech-to-text engine (value validated in `backend/app/config.py`). |
| `WHISPER_MODEL` | `"small.en"` | none | `backend/stt/engine.py` | faster-whisper model, baked into the Modal image. |
| `GEMINI_MODEL` | `"gemini-3.5-transcribe"` | `MODEL_TRANSCRIBE` | `backend/stt/engine.py` | Gemini speech-to-text model when `STT_ENGINE=gemini`. |
| `GEMINI_TIMEOUT_MS` | `15_000` | `GEMINI_TIMEOUT_MS` (positive integer) | `backend/stt/engine.py`, `backend/app/config.py` | Gemini STT timeout, below the stage deadline so the Whisper fallback still fits. |
| `DEFAULT_PATH` | `"/stt-logs/transcripts.jsonl"` | `STT_DEBUG_LOG_PATH` | `backend/stt/debug_log.py` | JSONL file of the opt-in transcript debug log, on the `metalab-stt-logs` Modal Volume. |
| `STT_DEBUG_LOG` | `"off"` | `STT_DEBUG_LOG` (`on`/`off`) | `backend/stt/debug_log.py`, `backend/app/config.py` | Opt-in transcript log (stores user speech, so off by default). |
| `COMMIT_INTERVAL_S` | `10.0` | none | `backend/stt/debug_log.py` | Minimum time between commits of the debug log to the Modal Volume. |
| `MODEL_TTS` | `"gemini-3.8-flash-tts"` | `MODEL_TTS` | `backend/app/config.py`, `backend/stt/speak.py` | Gemini TTS model, used when ElevenLabs is not configured or fails (module default `DEFAULT_MODEL_TTS`). |
| `VOICE` | `"Kore"` | none | `backend/stt/speak.py` | Gemini TTS voice. |
| `SAMPLE_RATE` | `24000` | none | `backend/stt/speak.py`, `backend/stt/elevenlabs.py` | 16-bit mono PCM rate of synthesized speech. |
| `TTS_TIMEOUT_S` | `20` | none | `backend/stt/speak.py` | One budget shared by the ElevenLabs attempt and its Gemini fallback. |
| `MAX_CLIPS` | `50` | none | `backend/stt/speak.py` | In-memory WAV clips kept before the oldest are dropped. |
| `CLIP_TTL_S` | `3600.0` | none | `backend/stt/speak.py` | Lifetime of an in-memory WAV clip. |
| `SWEEP_EVERY_S` | `60.0` | none | `backend/stt/speak.py` | Interval of the background clip expiry sweep. |
| `_MAX_EPOCH_ENTRIES` | `1000` | none | `backend/stt/speak.py` | LRU cap on per-session clip epoch entries. |
| `MODEL_TTS_ELEVENLABS` | `"eleven_flash_v2_5"` | `MODEL_TTS_ELEVENLABS` | `backend/app/config.py`, `backend/stt/elevenlabs.py`, `backend/stt/speak.py` | Primary ElevenLabs TTS model (module default `DEFAULT_MODEL_TTS_ELEVENLABS`). |
| `REQUEST_TIMEOUT_S` (ElevenLabs) | `20.0` | none | `backend/stt/elevenlabs.py` | HTTP timeout of the ElevenLabs call; `TTS_TIMEOUT_S` still bounds the whole attempt. Not the pipeline's `REQUEST_TIMEOUT_S`. |
| `API_URL` | `"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"` | none | `backend/stt/elevenlabs.py` | ElevenLabs text-to-speech endpoint. |

## iOS

| Constant | Default | Env override | Location | Description |
|---|---|---|---|---|
| `Deadline.demo` overallSeconds | `90` s | none | `ios/MetaLabCore/Sources/MetaLabCore/Deadline.swift` | Client gives up on a request after this long in total. |
| `Deadline.demo` idleSeconds | `30` s | none | `ios/MetaLabCore/Sources/MetaLabCore/Deadline.swift` | Client gives up after this long without a server message (any message resets it). |
| `armDeadline` poll | `500` ms | none | `ios/MetaLab/AppModel.swift` | How often the request watchdog checks `Deadline.demo`. |
| `CaptureSettings.maxRecordSeconds` | `4` s | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Longest microphone recording per request. |
| `CaptureSettings.trailingSilenceSeconds` | `0.7` s | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Silence kept after speech when trimming the recording. |
| `CaptureSettings.sampleRate` | `16_000` Hz | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Microphone capture rate (16-bit mono PCM WAV). |
| `CaptureSettings.frameRate` | `2` fps | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Glasses camera stream rate (valid DAT rates: 2, 7, 15, 24, 30). |
| `CaptureSettings.resolution` | `.high` | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Camera stream resolution for page frames. |
| `CaptureSettings.displayEnabled` | `true` | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Whether answers are shown on the glasses display. |
| `CaptureSettings.useStandalonePhoto` | `false` | none | `ios/MetaLabCore/Sources/MetaLabCore/CapturePlan.swift` | Use the beta standalone `capturePhoto()` instead of a stream frame. |
| `captureFirstFrame` timeout | `8` s | none | `ios/MetaLab/GlassesBridge.swift` | Wait for the first camera stream frame before failing with a timeout. |
| `captureStandalone` timeout | `20` s | none | `ios/MetaLab/GlassesBridge.swift` | Wait for a standalone photo before failing with a timeout. |
| `waitUntilStarted` timeout | `5` s | none | `ios/MetaLab/GlassesBridge.swift` | Wait for the glasses display to start before continuing anyway. |
| `settleHFP` delay | `300` ms | none | `ios/MetaLab/GlassesBridge.swift` | Pause after switching audio to Bluetooth HFP before recording. |
| `jpegData(compressionQuality:)` | `0.85` | none | `ios/MetaLab/GlassesBridge.swift` | JPEG quality of the captured page frame. |
| `Keys` | `metalab.backendURL`, `metalab.bookSessionId`, `metalab.configureError`, `metalab.earconsEnabled` | none | `ios/MetaLab/AppModel.swift` | `UserDefaults` keys for persisted settings. |
| `placeholder` | `"wss://your-modal-app.modal.run/ws"` | none | `ios/MetaLabCore/Sources/MetaLabCore/Privacy.swift` | Placeholder backend URL shown until the user sets one. |
| `makeChime` | `24000` Hz, `0.08` s, `maxAmp` `4000.0` | none | `ios/MetaLab/AnswerSpeaker.swift` | Synthesis parameters of the per-stage earcon chimes. |
