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

## Proposed natural intent extension (INTENT-D1, not runtime implementation)

Issue [#142](https://github.com/moterodiaz/Junction/issues/142), REQ-INTENT-01,
REQ-INTENT-02 and REQ-WS-04; PRD §§6–7, §12.1 and §12.3. **Contract proposal,
built ahead of its activation gate [#141](https://github.com/moterodiaz/Junction/issues/141)
under the lead's build-ahead waiver.** Nothing here is deployed, advertised or
enabled. Backend (INTENT-A1/C1) and iOS (INTENT-B1) adopt it only after the gate.

### Negotiation and default-off guarantee

Frame-free follow-ups change the meaning of a required field (`frame`), and
clarification is a new terminal reply. Both are incompatible with strict old
clients, so they need a negotiated version. They reuse the
[LIFECYCLE.md](LIFECYCLE.md) mechanism with one more subprotocol token:

- A new client offers `Sec-WebSocket-Protocol: metalab.v2.intent, metalab.v2`
  (preference order). It may use the features below only after the HTTP
  upgrade selects **exactly** `metalab.v2.intent`.
- The server selects `metalab.v2.intent` only when it is offered, `metalab.v2`
  is supported and the server's INTENT runtime flag is on. **The flag defaults
  off.** Otherwise it selects `metalab.v2` (when offered and supported) or
  nothing (legacy).
- `metalab.v2.intent` is a strict superset of `metalab.v2`. Every LIFECYCLE.md
  rule (ownership, `cancel`, `session_end`, expiry, `lifecycle_error` codes,
  one terminal per accepted invocation) applies unchanged, with
  `ws-lifecycle.schema.json` unchanged.
- No new wire stage, error code or lifecycle code. `status.stage` stays
  `transcribing | reading | thinking | drawing`; intent resolution happens
  inside `thinking`.

The root `oneOf` of `ws-messages.schema.json` and every pre-existing `$defs`
entry are byte-identical (pinned by digest in `test_intent.py`). The new `$defs`
entries are not referenced from the root, so legacy validation accepts and rejects
exactly what it did before. On `metalab.v2.intent`, application messages validate
against `$defs/intentProtocolMessage` instead of the root.

| Selected subprotocol | What the client may send | What the server sends |
|---|---|---|
| none (old client, old server, flag off without v2) | legacy `invoke` only | legacy `status`/`card`/`error` only; nothing new |
| `metalab.v2` | legacy `invoke`, v2 controls | legacy messages, v2 lifecycle messages; no `clarify`, no intent card |
| `metalab.v2.intent` | `invoke` (framed or frame-free), v2 controls | `status`, intent `card`, `clarify`, legacy `error`, v2 lifecycle messages |

### What an old client sees

Nothing new. With no selected subprotocol (an old client, or a new client whose
offer was ignored) the server behaves exactly as today:

- A natural sentence is handled by today's L0 path (no command word means
  `explain`) and gets a legacy card.
- Ambiguity keeps today's behaviour (for example the existing book question
  shipped as a legacy card), never `clarify`.
- An invoke with `frame: null` is rejected with the existing fixed
  invalid-request error (`internal`, `"Invalid request."`, `retryable: false`)
  echoing its `request_id`; the connection keeps working.
- Back-to-back invokes run one at a time in arrival order; a repeated
  `request_id` simply runs again (legacy has no duplicate rejection).

The same holds for `metalab.v2` connections, which additionally keep the
LIFECYCLE.md controls.

### Messages on `metalab.v2.intent`

- **`invoke`** (phone to backend): either the unchanged legacy invoke, or a
  frame-free follow-up (`$defs/followUpInvokeMessage`): identical fields with
  `frame` present and `null`. Exactly one of `audio` or `text` still applies; no
  other field is added. `audio`/`text` carry the whole utterance as today.
- **`card`** (`$defs/intentCardMessage`): every legacy card field with the same
  schema and meaning (`image_url` null when generation is unavailable,
  `audio_url` null means the phone speaks `speech_text` with the system voice,
  `sources` HTTPS citations, `models` read/reason/image), plus two required
  fields:
  - `intent`: the dispatched bounded intent, one of `reading | research | document`;
  - `utterance`: the full preserved utterance (the typed `text` exactly, or the
    full transcript of `audio`), never an L0 token.
- **`clarify`** (`$defs/clarifyMessage`, terminal): `request_id`, `session_id`,
  `reason`, `utterance`, `speech_text`, `audio_url` (card meaning), `options`.
  - `ambiguous_intent`: the utterance fits two or more **enabled** intents;
    `options` lists 2–3 of them.
  - `ambiguous_book`: the book cannot be identified; `options` is empty.
  - `needs_frame`: a frame-free follow-up in a session with no book context;
    `options` is empty. It is a reply, not an error, so the question survives.
  - `unsupported_intent`: outside the bounded set, or an intent whose module is
    disabled; `options` is empty. Disabled modules never start.
- **`error`**: unchanged legacy error, same codes.

### Rules

- **Full utterance.** The server resolves intent over the whole utterance, the
  extracted page text and the session. A failed or timed-out classifier falls
  back to the established L0 resolver (`reading`), never losing the question.
  The utterance is user text: never logged, persisted beyond the session or put
  in evidence (PRD §6).
- **Bounded intents.** Only `reading` is enabled by default. `research` and
  `document` stay `unsupported_intent` until their modules pass their gates.
- **Exactly one terminal.** An accepted invocation ends with exactly one of
  `card`, `error`, `clarify` or (v2) `cancelled`; nothing follows it.
- **Frame-free follow-ups** reuse only this session's committed context (book,
  position and earlier questions/answers, at least the last ten committed turns).
  Stages are a subsequence in PRD order without `reading`. Without context the
  reply is `clarify` with `needs_frame`; another session's context is never used.
  A frame-free invoke is an accepted invocation and refreshes expiry like any other.
- **Clarification context.** `clarify` commits no answer to history. After an
  `ambiguous_*` clarification on a framed invoke, the page text and the pending
  question are kept session-only so the next follow-up can answer without a new
  frame. They are deleted on end/expiry like all session text.
- **Cancel** is the LIFECYCLE.md `cancel`: its only terminal is `cancelled`,
  nothing it produced is appended, and earlier committed context stays.
- **Reset** is `session_end` (pending invocations get `cancelled` first, then
  `session_ended` with `cleanup: "complete"`) followed by a fresh session ID.
  The ended ID is never reused (`session_unavailable`); the phone discards any
  late reply for the old session.
- **Overlapping and repeated requests.** One connection processes invocations
  one at a time in arrival order, as today; controls are handled immediately,
  even while an invocation runs or waits. A follow-up sees every card committed
  before it starts. A reused `request_id` on the connection is rejected at
  admission with `duplicate_request` and starts no work. To interrupt, the
  phone sends `cancel` before the new invoke.
- **Deadlines unchanged.** The phone keeps its 30 s idle / 90 s overall
  deadlines per invocation (queue time included) and the backend keeps its
  current request/stage limits. Classification and clarification get bounded
  portions of that budget, not larger deadlines.

### Fixtures, exchanges and tests

- `fixtures/intent/valid/` and `fixtures/intent/invalid/`: message shapes for
  `$defs/intentProtocolMessage`. The legacy `fixtures/valid` and
  `fixtures/invalid` folders are unchanged and still pass/fail the root schema.
- `exchanges/intent/*.json`: ordered `steps` (`{"send": ...}` or
  `{"receive": ...}`) with `offered`, `server` (`v2`, `intent` flags),
  `selected`, `enabled_intents`, `live` and `deadlines`. They live in a
  subfolder so the legacy conformance and remote harnesses do not replay them.
  Exchanges with `"live": true` are old-client cases replayed against the
  actual current backend; the rest are proposed protocol traces.
- `test_intent.py` (run by `./test.sh`) pins the legacy schema, validates every
  new fixture, checks the negotiation table and default-off flag, runs every
  exchange through a test-only model of the rules above (including mutated
  exchanges that must fail), and replays the live old-client exchanges against
  `../backend` to show that nothing new reaches an old client.

These are proposed protocol tests, not backend/iOS conformance. INTENT-G1 still
needs deployed natural requests, a real spoken follow-up, reset and cancel on
hardware, and lead acceptance.

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

The check requires one schema-valid card with matching request ID, the complete
`reading → thinking → drawing` stage sequence (preceded by `transcribing` for audio),
non-null HTTPS image/audio URLs, the exact expected book/position and all expected
source entries. An error terminal, missing media, wrong grounding, duplicate
terminal or trailing status observed within the post-terminal window fails.
`WS_SUCCESS_EXTRA_WAIT_S` controls that window: default 1 second, greater than 0
and at most 30 seconds, finite. The socket is closed after that wait or the first
extra reply; replies arriving later are **not checked**. This finite observation
does not prove the server can never send another response. The schema-only mode
keeps its existing 0.5-second window. Diagnostics contain no response payloads.
The input file is limited to 16 MiB; the check does not save inputs or replies.

This proves only response-level assertions. URLs alone do not prove actual image
generation, retrievability, audio playback, correct speech recognition, hardware
UX, deployment revision or cleanup. Those remain separate manual/live evidence.
The original schema-only remote mode is unchanged and may still report drift.
See [base-live evidence](../docs/evidence/base-live.md) for the remaining checklist.
