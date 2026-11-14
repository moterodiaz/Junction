# WebSocket Message Contract

`ws-messages.schema.json` is the authoritative JSON Schema (Draft 2020-12) for PRD Section 7 WebSocket messages exchanged between `ios/` and `backend/`.

## Proposed lifecycle extension (not runtime implementation)

[LIFECYCLE.md](LIFECYCLE.md) specifies the opt-in `metalab.v2` subprotocol for
REQ-WS-04 / REQ-PRIV-03 ([#128](https://github.com/moterodiaz/Junction/issues/128)).
Its separate `ws-lifecycle.schema.json` does **not** widen the existing schema.
Clients must observe successful v2 negotiation before sending new controls;
legacy clients never receive v2 messages. Cancellation, explicit-end cleanup,
15-minute monotonic expiry with a five-second cleanup bound, and default-off
WSS handshake auth are proposed contracts, not claims about deployed behavior.

`test_lifecycle.py` validates synthetic protocol fixtures/traces and auth rollout
scenarios. `test_legacy_lifecycle.py` checks actual legacy rejection against the
current backend. These run through `./test.sh` alongside the existing legacy
conformance tests. Backend/iOS implementation and compatibility approval remain
with Ahmed/Maksym; runtime flags/auth remain off.

## Message Types

### Phone to Backend
- **`invoke`**: exactly one of `audio` or `text` carries a value; the other is `null` or omitted. An invoke with both set, or with neither, is rejected.
  - `type`: `"invoke"`
  - `request_id`: non-empty string
  - `session_id`: non-empty string
  - `frame`: `{ "mime": "image/jpeg", "b64": "<non-empty base64>" }` (required in both modes)
  - `audio`: `{ "mime": "audio/wav", "b64": "<non-empty base64>" }`. This is the real path: the spoken command captured on the glasses.
  - `text`: non-empty string. This is the test-only path for running without glasses hardware; it skips speech to text.

### Backend to Phone
- **`status`**:
  - `type`: `"status"`
  - `request_id`: non-empty string
  - `stage`: `"transcribing" | "reading" | "thinking" | "drawing"`
- **`card`**:
  - `type`: `"card"`
  - `request_id`: non-empty string
  - `title`, `caption`, `speech_text`: non-empty strings
  - `image_url`: `null` or `https://...` URL (`null` when image generation is unavailable; the card ships text plus audio). The field is still required.
  - `audio_url`: `null` or `https://...` URL
  - `book`: `{ "title": "...", "author": "...", "location": "..." }`
  - `sources`: `[ { "title": "...", "url": "https://..." } ]`
  - `models`: `{ "read": "...", "reason": "...", "image": "..." }`
- **`error`**:
  - `type`: `"error"`
  - `request_id`: non-empty string, or `null` only when the backend could not parse the incoming message and so has no request id to echo
  - `code`: `"no_text_found" | "stt_failed" | "model_timeout" | "internal"`
  - `message`: non-empty string
  - `retryable`: boolean

## Validation

Run `./test.sh` from `contracts/` to validate all fixtures in `fixtures/valid/` and `fixtures/invalid/` against `ws-messages.schema.json`, and to run the conformance harness below.
## Conformance harness

`test_conformance.py` runs the real backend (`../backend`, `app.main:app`) in-process through FastAPI's `TestClient` and replays every recorded exchange in `exchanges/*.json` over `/ws`. For each exchange it:

- sends the `send` frames, then reads back as many frames as `receive` holds (a 10 s alarm turns a missing reply into a failure instead of a hang);
- validates every outbound frame from the backend against `ws-messages.schema.json`;
- compares each frame with its recording on `type`, `stage`, `request_id`, `code` and `retryable` only, so model text can change without touching the recordings;
- checks the flow: status stages in PRD order, then exactly one `card` or `error` per send, each echoing the invoke's `request_id` (`null` when the frame could not be parsed).

It also checks that every recording passes the schema, that every sent invoke passes it (unless the exchange sets `"invalid_send": true`), and that a drifting backend (a card with an `http://` image URL) is reported. Only outbound frames from the backend are checked against the schema; the harness does not test how the backend rejects bad invokes beyond the recorded replies.

### Adding an exchange

1. Create `exchanges/<name>.json` with a `description`, a `send` list and `"receive": []`. A send frame is `{"text": <object or raw string>}` for a text frame, or `{"bytes": <object>}` for a binary frame encoded the way the iOS `Contract.encode` does (sorted keys, explicit nulls, escaped `/`).
2. Record it: `.venv/bin/python record.py <name>` (after `./test.sh` has created `.venv`).
3. Review the recorded replies, then commit.

### When to run `record.py`

Only for an intentional contract change (a new stage, a new error code, a changed flow). A failing harness otherwise means the backend drifted from the contract: fix the backend, not the recording.

## Remote mode

`test_remote.py` replays the same exchanges against a running backend over a real socket. It is opt-in:

```sh
WS_URL=wss://<modal-url>/ws ./test.sh
WS_URL=wss://<modal-url>/ws WS_TIMEOUT_S=600 ./test.sh   # longer per-reply wait
```

- `WS_URL`: the backend's `/ws` endpoint. Without it the remote test is reported as skipped.
- `WS_TIMEOUT_S`: how long to wait for each reply, in seconds (default 300, since Nemotron page reading takes minutes). A missing reply, a refused connection or an unknown host fails the run with a clear message instead of hanging.

A live server runs real models on the recorded media (an empty WAV, a 20-byte JPEG), so its outcomes can differ from the stubbed recordings, for example `stt_failed` instead of a card. Remote mode therefore:

- **enforces** that every reply passes `ws-messages.schema.json` and that the flow is valid: status stages in PRD order, then exactly one `card` or `error` per send, each echoing the invoke's `request_id`;
- **reports only** differences from the recordings (`type`, `stage`, `request_id`, `code`, `retryable`, reply count) as drift on stderr. Drift never fails the run.

CI never sets `WS_URL`, so it stays local and needs no network or keys. It still covers the socket path: `LocalServerRemoteModeTests` starts `uvicorn app.main:app` from `../backend` on a free localhost port with the model keys unset, and runs remote mode against it.

### Successful-card checks (#81), separate from schema-only conformance

Schema-valid errors are **not** evidence that reading works. `test_live_success.py`
adds a separate strict check, enabled only when **both** `WS_URL` and
`WS_SUCCESS_CASES` are set. Its default tests run locally with synthetic responses.
Do not run the live mode without permission for endpoint/model usage.

After approval, supply `WS_SUCCESS_CASES` as an absolute path to a cleared JSON
file outside the repository. It contains 2–10 cases, with at least one typed and
one audio invocation. Each case has exactly:

- `send`: one existing exchange-format frame (`{"text": <invoke>}` or
  `{"bytes": <invoke>}`). Use a real cleared JPEG and spoken WAV, not the placeholder
  recordings. Use fresh request/session IDs per run to avoid stale context.
- `expect`: `{"book": {"title": "...", "author": "...", "location": "..."},
  "sources": [{"title": "...", "url": "https://..."}]}`. Grounding expectations
  must come from independent known passages/citations, **not** the returned card.

The check requires one schema-valid card with matching request ID, ordered stages,
non-null HTTPS image/audio URLs, the exact expected book/position and all expected
source entries. An error terminal, missing media, wrong grounding, duplicate
terminal or trailing status fails. Diagnostics contain no response payloads.
The input file is limited to 16 MiB; the check does not save inputs or replies.

This proves only response-level assertions. URLs alone do not prove actual image
generation, retrievability, audio playback, correct speech recognition, hardware
UX, deployment revision or cleanup. Those remain separate manual/live evidence.
The original schema-only remote mode is unchanged and may still report drift.
See [base-live evidence](../docs/evidence/base-live.md) for the remaining checklist.
