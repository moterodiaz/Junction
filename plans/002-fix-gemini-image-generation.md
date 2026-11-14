# Plan 002: Image generation actually produces a lens image, and a slow image never fails the card

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- backend/ai/image.py backend/app/pipeline.py backend/stt/speak.py backend/tests/test_image.py backend/tests/test_ws.py backend/tests/test_speak.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M (half a day including a live check with a real key)
- **Risk**: MED — touches the production image client, which has never run against the real API; mitigated by a unit test with a fake SDK client and one live probe
- **Depends on**: none (a Gemini API key with pay-as-you-go billing is needed for Step 5 only)
- **Category**: bug
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

The pitch is "a picture, not a paragraph" (PRD section 2). The image path has
**never produced an image** and cannot, for two independent reasons:

1. `GeminiImageClient.generate_image` calls `client.aio.models.generate_images(...)`
   and then reads `response.images`. In the installed SDK (`google-genai` 3.3.0,
   checked in the backend venv) `GenerateImagesResponse` has the fields
   `['sdk_http_response', 'generated_images', 'positive_prompt_safety_attributes']`
   — there is no `images` attribute, so the call raises `AttributeError` even
   when the API succeeds.
2. `generate_images` is the Imagen-family endpoint. The configured model
   `gemini-nano-banana-2.1` is a Gemini-family image model; Google's current
   image-generation docs (https://ai.google.dev/gemini-api/docs/image-generation)
   generate with `client.interactions.create(model="gemini-nano-banana-2.1",
   input=prompt, response_format={"type": "image", ...})` and read
   `interaction.output_image.data` (base64).

Both failures are swallowed: `ai.image.draw` catches every exception and returns
`None`, `pipeline.draw` does the same, so the card ships with `image_url: null`
and `models.image: "stub"`. Tests never caught it because every test uses
`StubImageClient`; the real client has zero tests.

Separately, when image generation is merely *slow*, the whole request fails:
`pipeline._run` wraps the image stage in `timed(...)`, which turns a timeout into
`PipelineError("model_timeout")`, so a 26-second image generation discards a
perfectly good explanation and audio. The PRD (section 7) and the contract
(`contracts/README.md`: "`image_url`: `null` when image generation is
unavailable") say the image is optional. Make the code agree.

The TTS client (`backend/stt/speak.py`) uses the older
`generate_content(response_modalities=["AUDIO"])` shape, which the current TTS
docs no longer show. It has also never run for real. Step 5 verifies it with a
real key and switches it to the Interactions API only if it fails.

## Current state

- `backend/ai/image.py:276-299` — the broken production call:
  ```python
  async def generate_image(self, model: str, prompt: str) -> bytes:
      """Generate an image using Gemini image models."""
      try:
          from google import genai
          client = genai.Client(api_key=self.api_key)
          # Use client.aio for async generation
          response = await client.aio.models.generate_images(
              model=model or self.model,
              prompt=prompt,
          )
          if response.images and len(response.images) > 0:
              first_img = response.images[0]
              if hasattr(first_img, "image") and hasattr(first_img.image, "image_bytes"):
                  return first_img.image.image_bytes
              if hasattr(first_img, "image_bytes"):
                  return first_img.image_bytes
          raise RuntimeError("Gemini image response contained no image data")
      except Exception as exc:
          msg = str(exc).lower()
          # "quota" / rate limits are transient: let them surface as ordinary errors
          if any(term in msg for term in ("billing", "payment", "tier", "permission")):
              raise BillingNotEnabledError(str(exc)) from exc
          raise
  ```
- `backend/ai/image.py:258-274` — `check_billing` constructs a client and
  `return True` without calling anything. It is a no-op dressed as a probe; the
  module docstring (lines 16–18) claims "On the first call, billing status is
  checked". `draw()` (line ~364) calls it via `hasattr(active_client, "check_billing")`.
- `backend/ai/image.py:202-215` — `format_display_prompt` appends the
  black-background conditioning for the additive lens. Keep it.
- `backend/app/pipeline.py:196-208` — the stage that fails the request on a slow image:
  ```python
  await send_stage("drawing")
  # Speech runs alongside drawing so it adds no wait the phone's 30 s silence limit
  # would see. It is optional: None on any failure or timeout, and the phone speaks the text.
  async def _speak() -> str | None:
      try:
          return await asyncio.wait_for(speak(answer["speech_text"]), STAGE_TIMEOUT_S)
      except Exception as exc:
          log.warning("Speech unavailable: %s", exc)
          return None

  image_url, audio_url = await asyncio.gather(
      timed(draw(answer["image_prompt"], invoke.session_id)), _speak()
  )
  ```
  `timed()` (lines 90–96) raises `PipelineError("model_timeout", ...)` on `TimeoutError`.
- `backend/app/pipeline.py:126-134` — `pipeline.draw` already returns `None` on any exception from `image.draw`; only the *timeout* escapes, via `timed`.
- `backend/stt/speak.py:36-49` — TTS call:
  ```python
  response = await genai.Client(api_key=self.api_key).aio.models.generate_content(
      model=self.model,
      contents=text,
      config=types.GenerateContentConfig(
          response_modalities=["AUDIO"],
          speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
              prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
      ),
  )
  return response.candidates[0].content.parts[0].inline_data.data
  ```
  `to_wav()` (lines 74–81) wraps raw 24 kHz PCM in a WAV header.
- SDK facts (verified in `backend/.venv`, google-genai 3.3.0): `client.aio.interactions.create` exists;
  `client.aio.models.generate_content` and `generate_images` exist;
  `types.GenerateImagesResponse.model_fields` = `['sdk_http_response', 'generated_images', 'positive_prompt_safety_attributes']`.
- Docs excerpt (image-generation page, Python tab):
  ```python
  interaction = client.interactions.create(
      model="gemini-nano-banana-2.1",
      input=prompt,
      response_format={"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "16:9", "image_size": "2K"},
  )
  generated_image = interaction.output_image
  if generated_image:
      f.write(base64.b64decode(generated_image.data))
  ```
  REST equivalent: `POST https://generativelanguage.googleapis.com/v1beta/interactions`
  with header `x-goog-api-key: $GEMINI_API_KEY` and body
  `{"model": "...", "input": [{"type":"text","text":"..."}], "response_format": {"type":"image", ...}}`.
- The lens is 600×600 (PRD section 4): request `aspect_ratio: "1:1"`.
- Test conventions: stdlib `unittest`, async tests via `asyncio.run(...)` or
  `IsolatedAsyncioTestCase` (see `backend/tests/test_image.py`), fakes via
  `unittest.mock`. Tests must not touch the network or need keys.
- Documented decision to honour: `backend/app/modal_app.py:39-41` — one
  container, images in process memory. Do not change the storage design.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Backend tests | `cd backend && ./test.sh` | `OK` (147 tests + the ones you add) |
| Contracts tests | `cd contracts && ./test.sh` | `OK (skipped=1)` |
| Inspect SDK signature | `backend/.venv/bin/python -c "import inspect, google.genai as g; print(inspect.signature(g.Client(api_key='x').aio.interactions.create))"` | prints a signature; note whether `model`/`input`/`response_format` are explicit or `**body` |
| Live probe (Step 5, needs key) | see Step 5 | prints a `https://.../img/<id>.png` URL and `PNG ok` |

## Scope

**In scope** (the only files you should modify):
- `backend/ai/image.py` (class `GeminiImageClient`, module docstring)
- `backend/app/pipeline.py` (the "drawing" block only, lines ~196–208)
- `backend/stt/speak.py` (Step 5, only if the live probe fails)
- `backend/tests/test_image.py` (add tests)
- `backend/tests/test_ws.py` or `backend/tests/test_errors_privacy.py` (add one test)
- `backend/tests/test_speak.py` (only if speak.py changes)

**Out of scope** (do NOT touch):
- `backend/ai/image.py` storage/eviction/`image_router` code (lines ~47–200, ~430–520) — the in-memory store design is a documented decision.
- `backend/app/messages.py`, `contracts/**` — the contract already allows `image_url: null`.
- `backend/ai/reasoning.py`, `backend/ai/page_reader.py` — other plans own them.
- The image-model id or any `.env.example` default.

## Git workflow

Follow `AGENTS.md`: task issue → `tools/task claim N` → `tools/wt N-image-api`
→ small commits → `git pull --no-rebase` → push → PR `Closes #N` → `gh pr merge --squash --auto` → board post.
Commit style: `fix(ai): generate lens images with the Gemini Interactions API` /
`fix(backend): a slow image degrades to image_url null instead of failing the card`.
Area for the task issue: `backend-ai` for image.py, `backend-app` for pipeline.py.
These are two owners (`AGENTS.md` section 4): post on the board before editing
`backend/ai/image.py` if you are not its owner, or split into two PRs.

## Steps

### Step 1: Write the failing unit test for the real image client

In `backend/tests/test_image.py`, add a test class `GeminiImageClientTests`
that fakes the SDK and asserts the client returns PNG bytes:

```python
import base64
from types import SimpleNamespace
from unittest import mock

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")

class GeminiImageClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_image_uses_interactions_api_and_returns_png_bytes(self):
        create = mock.AsyncMock(return_value=SimpleNamespace(
            output_image=SimpleNamespace(data=base64.b64encode(PNG_1x1).decode())))
        fake_client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        with mock.patch("google.genai.Client", return_value=fake_client):
            png = await image.GeminiImageClient(api_key="k").generate_image("gemini-nano-banana-2.1", "a skull")
        self.assertTrue(png.startswith(b"\x89PNG"))
        kwargs = create.await_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-nano-banana-2.1")
        self.assertEqual(kwargs["response_format"]["type"], "image")
        self.assertEqual(kwargs["response_format"]["aspect_ratio"], "1:1")

    async def test_generate_image_without_output_image_raises(self):
        create = mock.AsyncMock(return_value=SimpleNamespace(output_image=None))
        fake_client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        with mock.patch("google.genai.Client", return_value=fake_client):
            with self.assertRaises(RuntimeError):
                await image.GeminiImageClient(api_key="k").generate_image("m", "p")

    async def test_billing_error_text_maps_to_billing_not_enabled(self):
        create = mock.AsyncMock(side_effect=RuntimeError("Image models require pay-as-you-go billing tier"))
        fake_client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
        with mock.patch("google.genai.Client", return_value=fake_client):
            with self.assertRaises(image.BillingNotEnabledError):
                await image.GeminiImageClient(api_key="k").generate_image("m", "p")
```

(`image` is already imported in that test file as the module under test; check the existing import line and reuse its name.)

**Verify**: `cd backend && ./test.sh 2>&1 | tail -5` → the three new tests **fail** (first with `AttributeError`/`TypeError` from the old `generate_images` path).

### Step 2: Rewrite `GeminiImageClient.generate_image`

Replace lines 276–299 of `backend/ai/image.py` with:

```python
    async def generate_image(self, model: str, prompt: str) -> bytes:
        """Generate one PNG with a Gemini image model via the Interactions API.

        Docs: https://ai.google.dev/gemini-api/docs/image-generation. The lens is
        600x600, so the aspect ratio is 1:1. The returned image is base64 in
        interaction.output_image.data.
        """
        from google import genai

        client = genai.Client(api_key=self.api_key)
        try:
            interaction = await client.aio.interactions.create(
                model=model or self.model,
                input=prompt,
                response_format={"type": "image", "mime_type": "image/png", "aspect_ratio": "1:1"},
            )
        except Exception as exc:
            msg = str(exc).lower()
            # "quota" / rate limits are transient: let them surface as ordinary errors
            if any(term in msg for term in ("billing", "payment", "tier", "permission")):
                raise BillingNotEnabledError(str(exc)) from exc
            raise
        output = getattr(interaction, "output_image", None)
        data = getattr(output, "data", None) if output is not None else None
        if not data:
            raise RuntimeError("Gemini image response contained no image data")
        return base64.b64decode(data) if isinstance(data, str) else bytes(data)
```

Make sure `import base64` exists at the top of `image.py` (add it if missing).
If the SDK signature from "Commands you will need" shows that
`interactions.create` does **not** accept `model=`/`input=`/`response_format=`
as keywords (e.g. it wants a single `request=` object), try the two fallbacks in
order and record which one worked in the PR body:

- **Option B (same SDK, older surface):**
  `resp = await client.aio.models.generate_content(model=..., contents=prompt, config=types.GenerateContentConfig(response_modalities=["IMAGE"]))`,
  then take the first `part` in `resp.candidates[0].content.parts` whose
  `inline_data` is not None and return `part.inline_data.data` (bytes). Keep the
  real `part.inline_data.mime_type` on the stored image instead of hard-coding
  `image/png` (`StoredImage` has a content-type field; see `image.py:52-70`).
- **Option C (no SDK):** a direct REST call with `httpx` (already a dependency)
  to `POST https://generativelanguage.googleapis.com/v1beta/interactions` with
  header `x-goog-api-key` and the body shown in "Current state".

If all three are rejected by the live API (HTTP 400 naming a field), STOP and
report the exact error text.

**Verify**: `cd backend && ./test.sh 2>&1 | tail -3` → `OK`, test count = previous + 3.

### Step 3: Remove the fake billing probe

In `backend/ai/image.py`:
1. Delete the `check_billing` method from `GeminiImageClient` (lines 258–274). `draw()` already skips the probe when the client has no `check_billing` attribute. Leave `StubImageClient.check_billing` alone (tests use it).
2. Change the module docstring lines 16–18 to:
   `- Billing: pay-as-you-go billing is required for image models. There is no separate probe; the first real generation that fails with a billing/tier error disables image generation for this process and the card ships with text and speech only.`

**Verify**: `grep -n "def check_billing" backend/ai/image.py` → exactly one match, inside `StubImageClient`; `cd backend && ./test.sh 2>&1 | tail -3` → `OK`.

### Step 4: A slow image degrades to `image_url: null`

In `backend/app/pipeline.py`, replace the `asyncio.gather(timed(draw(...)), _speak())`
block with a `_draw()` wrapper symmetric to `_speak()`:

```python
    # The image is optional (contracts/README.md: image_url is null when generation is
    # unavailable). A slow or failing generation must not discard the explanation and audio.
    async def _draw() -> str | None:
        try:
            return await asyncio.wait_for(draw(answer["image_prompt"], invoke.session_id), STAGE_TIMEOUT_S)
        except Exception as exc:
            log.warning("Image unavailable: %s", type(exc).__name__)
            return None

    image_url, audio_url = await asyncio.gather(_draw(), _speak())
```

Add a test next to `test_slow_stage_is_model_timeout` in
`backend/tests/test_errors_privacy.py` (it slows `think`; yours slows `draw`):

```python
    def test_slow_image_gives_a_card_without_an_image(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(5)

        with mock.patch.object(pipeline, "STAGE_TIMEOUT_S", 0.05):
            reply = self.last_reply_with("draw", slow)
        self.assertEqual(reply["type"], "card")
        self.assertIsNone(reply["image_url"])
        self.assertEqual(reply["models"]["image"], "stub")
```

(`last_reply_with(stage_name, fn)` already exists in that file at line ~55; it
patches `pipeline.<stage_name>` and returns the last reply.)

One existing test encodes the *wrong* behaviour and will fail after this change:
`backend/tests/test_errors_privacy.py:100-106`
`test_unexpected_exception_is_internal_and_retryable` patches `draw` to raise
`KeyError("secret detail")` and expects an `internal` error. The image is
optional, so a crashing `draw` must now yield a card with `image_url: null`.
Change that test to patch `think` instead of `draw` (the assertion — `internal`,
retryable, no "secret" in the message — stays exactly as it is). Do not delete it.

**Verify**: `cd backend && ./test.sh 2>&1 | tail -3` → `OK`; `cd contracts && ./test.sh 2>&1 | tail -3` → `OK (skipped=1)`.

### Step 4b (optional, S): a transient error must not disable images until redeploy

`backend/ai/image.py:408-416`: a `BillingNotEnabledError` sets the module-global
`_billing_enabled = False` for the life of the process, and lines 293–297 raise it
for any error text containing "billing", "payment", "tier" or "permission" —
Gemini's 429 quota message often contains "billing". With `min_containers=1`
one rate-limit burst turns images off until the next deploy. Fix: record
`_billing_disabled_at = time.monotonic()` when disabling, and in `draw()` treat
the flag as expired after 300 s (try again; if it fails the same way, disable
again). Add a test with a fake clock (model on `test_image.py`'s billing tests).

**Verify**: `cd backend && ./test.sh` → `OK`.

### Step 5: Live probe with a real key (image, then TTS)

Needs `GEMINI_API_KEY` with billing enabled, exported in your shell (never
committed, never pasted on the board). From `backend/`:

```sh
.venv/bin/python - <<'EOF'
import asyncio, os
from ai import image
async def main():
    url = await image.draw("A lone prince on a dark stage holding a skull", session_id="probe",
                           base_url="https://probe.invalid")
    print("url:", url)
    item = image.get_image(url.rsplit("/", 1)[-1].removesuffix(".png")) if url else None
    print("PNG ok" if item and bytes(item.data if hasattr(item, "data") else item.png_bytes)[:4] == b"\x89PNG" else "NO IMAGE")
asyncio.run(main())
EOF
```
(`StoredImage`'s byte field name is at `backend/ai/image.py:52-70`; read it and
adjust the attribute in the probe.) Expected: `url: https://probe.invalid/img/<hex>.png` and `PNG ok`.

Then probe TTS:
```sh
.venv/bin/python - <<'EOF'
import asyncio, os
os.environ["IMAGE_BASE_URL"] = "https://probe.invalid"
from stt import speak
print(asyncio.run(speak.speak("Hamlet is alone, weighing whether to keep living.")))
EOF
```
Expected: `https://probe.invalid/audio/<hex>.wav`. If it prints `None`, read the
warning logged by `speak.speak` (it logs the exception type). If the failure is
an API error (not a network/key error), switch `GeminiSpeechClient.synthesize`
to the Interactions API per https://ai.google.dev/gemini-api/docs/speech-generation:
`client.aio.interactions.create(model=self.model, input=text, response_format={"type": "audio"}, generation_config={"speech_config": [{"voice": VOICE}]})`
and return `base64.b64decode(interaction.output_audio.data)`. **Check the first
4 bytes**: if they are `RIFF`, the data is already WAV — change `speak()` to
store it as-is instead of calling `to_wav()`; if not, keep `to_wav()`. Update
`backend/tests/test_speak.py`'s fake client accordingly and keep all tests green.

**Verify**: both probes print URLs; `cd backend && ./test.sh` → `OK`.

### Step 6: Open the PR

Follow "Git workflow". In the PR body include: the SDK field evidence
(`generated_images` vs `images`), the docs URL, which probes ran and their output
(URLs only, never keys).

## Test plan

- New unit tests (Step 1) in `backend/tests/test_image.py`: success path returns PNG bytes
  and requests `type: image`, `aspect_ratio: 1:1`; missing `output_image` raises `RuntimeError`;
  billing text maps to `BillingNotEnabledError`.
- New test (Step 4) in `backend/tests/test_errors_privacy.py`: slow `draw` → card with
  `image_url: null`, not `model_timeout`.
- Pattern to follow: `backend/tests/test_image.py` (existing `IsolatedAsyncioTestCase`
  usage) and `backend/tests/test_errors_privacy.py::last_reply_with`.
- `cd backend && ./test.sh` → all pass, count = 147 + 4 (+ any TTS test changes).

## Done criteria

- [ ] `grep -n "generate_images\|response\.images" backend/ai/image.py` returns no matches
- [ ] `grep -n "interactions.create" backend/ai/image.py` returns one match
- [ ] `grep -c "def check_billing" backend/ai/image.py` → `1` (only the stub)
- [ ] `grep -n "timed(draw" backend/app/pipeline.py` returns no matches
- [ ] `cd backend && ./test.sh` exits 0 with ≥ 151 tests
- [ ] `cd contracts && ./test.sh` exits 0
- [ ] Live probe printed an `https://.../img/<id>.png` URL and `PNG ok` (paste the URL line into the PR body)
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at `backend/ai/image.py:276-299` or `backend/app/pipeline.py:196-208`
  no longer matches the excerpts (someone fixed or moved it).
- `interactions.create` rejects the keyword arguments and the REST body shape
  is also rejected (HTTP 400 naming a field): report the exact error text.
- The live probe returns a billing error: that is a human action (enable
  pay-as-you-go on the key), not a code change; report it.
- No `GEMINI_API_KEY` is available: finish Steps 1–4, open the PR, and mark
  Step 5 as pending in the PR body and in `plans/README.md`.
- A test outside the ones you added starts failing.

## Maintenance notes

- `aspect_ratio` and `mime_type` are the only knobs the lens needs; if the
  display size changes (PRD section 4 says 600×600), change the ratio here.
- Reviewer: confirm no exception from the image stage can reach `main.handle`
  any more; the only way the request fails after "thinking" is a disconnect.
- Deferred: a true billing probe (a cheap text call that inspects the error
  code) was removed on purpose; the first real generation is the probe.
- Plan 006/Direction: the `models.image` value on the card is what the phone
  shows; keep it truthful (`"stub"` when no image).
