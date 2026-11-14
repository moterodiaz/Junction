# WebSocket Message Contract

`ws-messages.schema.json` is the authoritative JSON Schema (Draft 2020-12) for PRD Section 7 WebSocket messages exchanged between `ios/` and `backend/`.

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
  - `request_id`: non-empty string, or `null` only when the backend could not parse the incoming message and so has no request id to echo (the phone treats it as "the last request failed")
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
