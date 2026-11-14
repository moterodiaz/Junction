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
  - `request_id`: non-empty string
  - `code`: `"no_text_found" | "stt_failed" | "model_timeout" | "internal"`
  - `message`: non-empty string
  - `retryable`: boolean

## Validation

Run `./test.sh` from `contracts/` to validate all fixtures in `fixtures/valid/` and `fixtures/invalid/` against `ws-messages.schema.json`.
