# Plan 008: The public `/ws` endpoint cannot be used to run up the model bill, lock out the phone, or leak payloads into logs

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- backend/app/main.py backend/app/messages.py backend/app/pipeline.py backend/app/config.py backend/ai/page_reader.py backend/stt/speak.py backend/.env.example backend/README.md backend/tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition. Plans 002 and 005 also edit
> `pipeline.py`/`page_reader.py`; sequence after them or coordinate on the board.

## Status

- **Priority**: P1 (the demo URL goes into a public submission form on Sunday)
- **Effort**: M (half a day)
- **Risk**: MED — the shared token must ship on the phone in the same window or every request is refused; mitigated by making the token optional (absent = auth off, loud warning) so local, CI and contract runs are unchanged
- **Depends on**: none (coordinate with the iOS owner for the token; plan 002/005 for `pipeline.py` line ranges)
- **Category**: security
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

`backend/app/main.py:47-60` accepts any WebSocket client with no credential,
origin check, rate limit or size limit, then (`pipeline.py:162-208`) makes up to
four paid calls per message — Nemotron, Gemini reasoning, Gemini image
(pay-as-you-go), Gemini TTS. A typed `text` invoke skips speech-to-text and its
two-slot limiter, so one script can fire them as fast as the models answer.
The service is one Modal container with 20 concurrent inputs
(`modal_app.py:41,45`); twenty idle sockets lock the real phone out. The
`wss://<workspace>--metalab-web.modal.run/ws` URL will be in the submission
form and on slides.

Three smaller holes compound it: there is no upper bound on the base64 `frame`
and `audio` fields (`messages.py:14-15`), so a 15 MB clip ties up a Whisper slot
for minutes; a missing `IMAGE_BASE_URL` silently turns off images *and* voice
(`image.py:328`, `speak.py:87-93`) and the documented deploy flow
(`backend/README.md:31`) guarantees the first deploy runs that way; and upstream
error bodies are copied unbounded into exception messages that are logged with
tracebacks (`page_reader.py:234-237`, `reasoning.py:131-132`, `main.py:105,115`),
which is how a validation error that echoes the request would put frame base64
into Modal's logs, against PRD §6.

## Current state

- `backend/app/main.py:47-62`:
  ```python
  @app.websocket("/ws")
  async def ws(websocket: WebSocket) -> None:
      await websocket.accept()
      try:
          while True:
              event = await websocket.receive()
              if event["type"] == "websocket.disconnect":
                  break
              raw = event.get("text")
              if raw is None:
                  raw = event.get("bytes")  # the iPhone client sends JSON as binary frames
              if raw is None:
                  continue
              await handle(websocket, raw)
      except WebSocketDisconnect:
          pass
  ```
  Messages on one socket are already processed one at a time (the loop awaits
  `handle`). Concurrency comes from many sockets.
- `backend/app/messages.py:13-15`:
  ```python
  NonEmpty = Annotated[str, StringConstraints(min_length=1)]
  Base64 = Annotated[str, StringConstraints(
      min_length=4, pattern=r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")]
  ```
  `Frame.b64`, `Audio.b64`, `request_id`, `session_id`, `text` have no maximum length.
  The shared schema `contracts/ws-messages.schema.json` (owned by `@moterodiaz`)
  has no `maxLength` either; the backend may be stricter than the schema without
  breaking any fixture (all fixtures are tiny), but the limits should be proposed
  upstream (Step 6).
- `backend/app/config.py:19-28` — `REQUIRED = ("NVIDIA_API_KEY", "GEMINI_API_KEY")`;
  `DEFAULTS` lists five model/URL vars. `IMAGE_BASE_URL` and `IMAGE_SESSION_TTL_SECONDS`
  are read elsewhere but not declared here or in `.env.example`.
- `backend/stt/speak.py:84-93` — `speak(text)` reads `IMAGE_BASE_URL` from the
  environment and returns `None` (no audio) unless it starts with `https://`.
- `backend/ai/image.py:326-338` — `_resolve_base_url(override)` reads the same var and
  raises `ImageConfigError` when missing; `draw(image_prompt, session_id, base_url=None, client=None)` already accepts `base_url`.
- `backend/app/pipeline.py:126-134, 196-208` — `draw(...)` and `_speak()` do not pass a base URL.
- `backend/ai/page_reader.py:265-278` — `_parse_response`: empty `choices` → `NoTextFoundError`; `content` that is `None` or non-string → `""` → `NoTextFoundError`. The student is told "No readable text was found on the page" for an API fault; `main.py:105` logs it with `log.exception`.
- `backend/ai/page_reader.py:231-242` — HTTP errors become `PageReadError(f"Nemotron API returned HTTP {resp.status_code}: {resp.text}")` with the **whole** body.
- `backend/app/latency.py:33` and `main.py:100` log the client-chosen `request_id` verbatim (it may contain newlines).
- `backend/app/modal_app.py:37-45` — `@modal.concurrent(max_inputs=20)`, one container.
- The contract harness `contracts/test_conformance.py` and `contracts/test_remote.py`
  connect **without** any token; they must keep working when the token variable is unset.
- Test conventions: stdlib `unittest`, `fastapi.testclient.TestClient`, env patched with `mock.patch.dict(os.environ, ...)`; see `backend/tests/test_ws.py` and `test_startup.py`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Backend tests | `cd backend && ./test.sh` | `OK` |
| Contracts tests (must stay keyless and tokenless) | `cd contracts && ./test.sh` | `OK (skipped=1)` |
| Token refusal, by hand | `cd backend && METALAB_WS_TOKEN=t .venv/bin/python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); import pytest" 2>/dev/null; echo "(use the unit test instead)"` | see Step 1 tests |

## Scope

**In scope**:
- `backend/app/main.py` (token check, idle timeout, global in-flight limit, log sanitising)
- `backend/app/messages.py` (max lengths)
- `backend/app/config.py`, `backend/.env.example`, `backend/README.md` (declare `METALAB_WS_TOKEN`, `IMAGE_BASE_URL`, `MAX_INFLIGHT`, `WS_IDLE_S`)
- `backend/app/pipeline.py` (pass `public_base` into `draw`/`speak`; lines 126–134 and 196–208 only)
- `backend/stt/speak.py` (`speak(text, base=None)`)
- `backend/ai/page_reader.py` (`_parse_response` codes; truncate error bodies)
- `backend/tests/test_ws.py`, `backend/tests/test_startup.py`, `backend/tests/test_page_reader.py` (add tests)

**Out of scope**:
- `contracts/**` — propose `maxLength` in an issue to `@moterodiaz` (Step 6); do not edit.
- `ios/**` — the iOS owner adds the token to the URL/setting (Step 6 issue).
- `backend/app/modal_app.py` concurrency numbers — leave `max_inputs=20`.
- Any model-client logic beyond the parse/error-message lines named above.

## Git workflow

Follow `AGENTS.md`: task issue (REQ-WS-03, REQ-PRIV-02, REQ-DEPLOY-01; PRD §6, §7) →
claim → `tools/wt N-ws-hardening` → PR `Closes #N` → auto-merge → board post that
names the new secret variable (**name only**) so the Modal secret owner adds it.
`backend/ai/page_reader.py` is `@Marcus228`'s: ask on the board before Step 5, or
hand that step to him. Commit style: `feat(backend): shared token, size caps and an in-flight limit on /ws`.

## Steps

### Step 1: Shared token on the handshake (optional var; absent = off, loudly)

In `backend/app/main.py`:

```python
import hmac, os
WS_TOKEN = os.environ.get("METALAB_WS_TOKEN", "").strip()

def _presented_token(websocket: WebSocket) -> str:
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return websocket.headers.get("x-metalab-token") or websocket.query_params.get("token") or ""

@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    if WS_TOKEN and not hmac.compare_digest(_presented_token(websocket), WS_TOKEN):
        await websocket.close(code=1008)  # policy violation; sent before accept -> HTTP 403
        return
    await websocket.accept()
    ...
```

In `create_app(require_keys=True)` log at WARNING when `WS_TOKEN` is empty:
`"METALAB_WS_TOKEN is not set: /ws accepts any client"` (deploys see it in Modal logs).
Read the token via `config.py`: add `"METALAB_WS_TOKEN": ""` to a new `OPTIONAL`
mapping (or to `DEFAULTS` with default `""`) and a `ws_token` field on `Settings`
(`repr=False`), so `.env.example` can document it. Tests (`test_ws.py`):
- with `METALAB_WS_TOKEN=secret` patched into `os.environ` **and `main.WS_TOKEN` reloaded** (patch `main.WS_TOKEN` directly, simplest), `TestClient(app).websocket_connect("/ws")` raises `WebSocketDisconnect` (code 1008/403) and `websocket_connect("/ws?token=secret")` works; the header form works too.
- with the token unset, the existing tests pass unchanged.

**Verify**: `cd backend && ./test.sh` → `OK`; `cd contracts && ./test.sh` → `OK (skipped=1)`.

### Step 2: Size caps and id limits (`backend/app/messages.py`)

```python
NonEmpty = Annotated[str, StringConstraints(min_length=1, max_length=128)]           # request_id, session_id
Text = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Base64Frame = Annotated[str, StringConstraints(min_length=4, max_length=4_000_000, pattern=...)]  # ~3 MB JPEG
Base64Audio = Annotated[str, StringConstraints(min_length=4, max_length=2_000_000, pattern=...)]  # ~45 s of 16 kHz mono 16-bit
```
Use them on `Frame.b64`, `Audio.b64`, `Invoke.text`. Tests: a frame `b64` of 4,000,004
characters is rejected with the fixed `Invalid request.` error (reuse
`test_invalid_invoke_error_does_not_echo_input`'s shape); a 3,000,000-character one
is accepted (patch `read_page` so no model is called). Keep the regex anchored.

**Verify**: `cd backend && ./test.sh` → `OK`; `cd contracts && ./test.sh` → `OK (skipped=1)`
(every fixture is far below the caps).

### Step 3: Idle timeout and a global in-flight limit (`backend/app/main.py`)

- Idle: wrap the receive in `asyncio.wait_for(websocket.receive(), WS_IDLE_S)` with
  `WS_IDLE_S = float(os.environ.get("WS_IDLE_S", "120"))`; on `TimeoutError`
  `await websocket.close(code=1001)` and return. The phone opens one socket per
  question (iOS `BackendSocket.swift`), so 120 s is generous.
- In-flight: `_INFLIGHT = asyncio.Semaphore(int(os.environ.get("MAX_INFLIGHT", "4")))`.
  In `handle`, after validation: `if _INFLIGHT.locked(): await send(websocket, Error(request_id=invoke.request_id, code="internal", message="Busy. Try again in a moment.", retryable=True)); return`
  else `async with _INFLIGHT: ... pipeline.run(...)`. (`internal` is the only contract
  code that fits; say so in a comment.)
- Tests: patch `main.WS_IDLE_S` to 0.05 → a connected socket that sends nothing is
  closed; patch `main._INFLIGHT = asyncio.Semaphore(1)` and hold it → the reply is
  the `Busy` error and the socket stays open.

**Verify**: `cd backend && ./test.sh` → `OK`.

### Step 4: Derive the public base URL from the request; declare `IMAGE_BASE_URL`

- In `main.handle`, compute `public_base = os.environ.get("IMAGE_BASE_URL", "").strip() or f"https://{websocket.headers.get('host', '')}"` (only when `host` is non-empty) and pass it to `pipeline.run(invoke, send_stage, public_base=public_base)`.
- In `pipeline.py`: thread `public_base` to `draw(answer["image_prompt"], invoke.session_id, base_url=public_base)` and `speak(answer["speech_text"], base=public_base)`; `image.draw` already takes `base_url`; add `base: str | None = None` to `speak.speak` and use it before the environment variable.
- `config.py`: add `"IMAGE_BASE_URL": ""` to `DEFAULTS` and an `image_base_url` field; in `create_app(require_keys=True)` log at WARNING if unset ("images and audio will use the request Host header").
- `.env.example`: document `IMAGE_BASE_URL` (optional; derived from the request when unset) and `METALAB_WS_TOKEN`, `MAX_INFLIGHT`, `WS_IDLE_S`.
- `backend/README.md:31`: replace the "add IMAGE_BASE_URL, then deploy again" step with "optional; the backend derives it from the request's Host header".
- Tests: a TestClient request with `headers={"host": "demo.modal.run"}` (TestClient sets `host` from `base_url`: use `TestClient(app, base_url="https://demo.modal.run")`) and `draw`/`speak` patched to record their `base_url`/`base` → both receive `https://demo.modal.run`.

**Verify**: `cd backend && ./test.sh` → `OK`; `grep -n "IMAGE_BASE_URL" backend/.env.example backend/app/config.py` → ≥ 2 matches.

### Step 5: Honest page-reader errors and bounded log text (`backend/ai/page_reader.py`, `main.py`)

- `_parse_response`: empty `choices`, `content is None`, or a non-`stop` `finish_reason`
  → `raise PageReadError("Nemotron returned no usable content", code="internal", retryable=True)`;
  keep `NoTextFoundError` for the explicit `NO_TEXT_FOUND` signal and for empty/whitespace **string** content.
- Truncate upstream bodies in error messages: `resp.text[:300]` (both httpx and urllib paths), after
  `re.sub(r"[A-Za-z0-9+/=]{120,}", "<base64>", body)`.
- `main.py:104-112`: log `NoTextFoundError` at `log.info` without a traceback; keep
  `log.exception` for other `PageReadError`s. Sanitise ids once at the top of
  `handle`: `safe_id = invoke.request_id.replace("\n", " ").replace("\r", " ")[:64]`
  and use it in every log call and in `StageTimer(safe_id)`.
- Tests (`test_page_reader.py`, `test_ws.py`): `{"choices": []}` → `internal`; `{"choices":[{"message":{"content":None}}]}` → `internal`; a 10 kB error body produces an exception message < 400 chars with no 200-char base64 run; a `request_id` containing `\n` appears in the latency log line without a newline.

**Verify**: `cd backend && ./test.sh` → `OK`.

### Step 6: Hand-offs and PR

- File two task issues: (a) `contracts`: add `maxLength` to `nonEmptyString`,
  `base64String` (frame/audio) and `text` in `ws-messages.schema.json` matching the
  backend caps, REQ-WS-01, owner `@moterodiaz`; (b) `ios`: send the token (`?token=`
  on the configured `wss://` URL or `X-MetaLab-Token` header), REQ-WS-03, owner
  `@maksymmatviievskyi`.
- Post on the board: the new variable **names** (`METALAB_WS_TOKEN`, `IMAGE_BASE_URL`
  now optional, `MAX_INFLIGHT`, `WS_IDLE_S`) and that the Modal secret owner must add
  `METALAB_WS_TOKEN` *after* the phone can send it (or keep it unset until then).
- Open the PR per "Git workflow".

## Test plan

- `test_ws.py`: token required/accepted/absent; frame/audio/text over-limit → `Invalid request.`; idle close; busy error; base URL derived from Host; `request_id` with a newline is sanitised in logs (`assertLogs("metalab.latency")`).
- `test_startup.py`: warnings logged when `METALAB_WS_TOKEN`/`IMAGE_BASE_URL` are unset with `require_keys=True`.
- `test_page_reader.py`: empty choices / null content → `internal`; truncated, redacted error body.
- Pattern: existing tests in those files (TestClient + `mock.patch.object(pipeline, ...)`).
- `cd backend && ./test.sh` and `cd contracts && ./test.sh` → all pass.

## Done criteria

- [ ] `grep -n "compare_digest" backend/app/main.py` → 1 match; `grep -n "max_length=4_000_000" backend/app/messages.py` → 1 match
- [ ] `grep -n "Semaphore" backend/app/main.py` → ≥ 1; `grep -n "WS_IDLE_S" backend/app/main.py` → ≥ 1
- [ ] `grep -n "def speak(text: str, base" backend/stt/speak.py` → 1 match
- [ ] `grep -n "resp.text\[:300\]\|\[:300\]" backend/ai/page_reader.py` → ≥ 1
- [ ] `grep -c "IMAGE_BASE_URL\|METALAB_WS_TOKEN\|MAX_INFLIGHT\|WS_IDLE_S" backend/.env.example` → 4
- [ ] `cd backend && ./test.sh` exits 0 with ≥ 160 tests; `cd contracts && ./test.sh` exits 0 and no exchange recording changed
- [ ] Two hand-off issues filed (contracts `maxLength`; iOS token)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `contracts/test.sh` fails after Step 1 or 2: the harness must stay tokenless and
  its fixtures must stay valid; you changed a default — revert it.
- `websocket.close()` before `accept()` raises in Starlette/FastAPI versions in the venv (check `backend/.venv/bin/python -c "import starlette; print(starlette.__version__)"`): report the version and the traceback; do not call `accept()` first.
- The iOS owner cannot ship the token change before the demo: leave
  `METALAB_WS_TOKEN` **unset** in the Modal secret (auth stays off) and say so in
  the Tieto concept card's "Limits".
- Plan 002 or 005 changed `pipeline.py` lines 126–134 / 196–208 in a way the
  excerpts no longer match.

## Maintenance notes

- Rotate `METALAB_WS_TOKEN` after the event; it will have been typed into a phone and shown on slides.
- When Modal is given `min_containers=1` for the demo, re-check `MAX_INFLIGHT`
  against the measured stage latencies (plan 006): 4 in-flight × ~60 s is the
  realistic ceiling for one container.
- Reviewer: confirm no code path logs `exc` of a model client without truncation,
  and that the token never appears in a log line (grep the test logs).
- Deferred: per-token rate limiting and provider budget alerts (human action in
  the NVIDIA and Google consoles).
