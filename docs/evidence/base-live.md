# BASE live evidence, #81

Requirements: REQ-INT-01, REQ-BASE-01. PRD §§7, 12.2, 14.1.

**Not yet validated.** From the v5 redeploy (2026-11-14, `5d1a6ee`) through v7
(`9d10e28`), the strict success check passes on stages, the illustration, book
grounding and the source citation, for both typed and spoken requests. It still fails
on spoken output: `audio_url` is null because Gemini speech synthesis fails (v5/v6: a
rejected request shape; v7: model not found for this key; see "Live reruns after v6
and v7"). An unknown book gets no invented citation, but the card
names it as Hamlet. The iOS round trip on hardware has not run.

## Live reruns after v6 and v7, 2026-11-14/15 (authorized by the lead, no glasses)

Same inputs, expected values and command as "Live rerun after redeploy" below. Inputs lived only in `/tmp` and were deleted after each run.

| Deploy | Commit | Strict run | Server log for speech (`metalab.speak`) |
|---|---|---|---|
| v6 | `53b35ff` (#230: log the failure reason, fall back on a missing model id) | 40 tests, **2 failures**, each only `audio_url` null. Typed card in 21.1 s, spoken card in 25.0 s. Grounding, stages and image pass | `ClientError code=400 status=INVALID_ARGUMENT reason=Invalid JSON payload received. Unknown name "speechConfig" at 'generation_config'` |
| v7 | `9d10e28` (#234: speech through the Gemini Interactions API) | 40 tests in 80.6 s, **2 failures**, each only `audio_url` null. Grounding, stages and image pass | `NotFoundError reason=Error code: 404 - … Model 'gemini-3.8-flash-tts' not found` |

What this shows:
- v6's logging found the first cause: `generateContent` rejected the request shape. #234 moved the call to the Interactions API.
- On v7 the Interactions call reaches the API, but this key gets 404 for `gemini-3.8-flash-tts`. The 404 fallback in `backend/stt/speak.py` did not run: the Interactions client's `NotFoundError` carries `status_code = 404`, and the code checks only `code` and `status`. So the log never listed the TTS models the key can use. Reported on #226 (@Ahm3d-KA).
- Spoken output is still **not validated**.
## Live rerun after redeploy, 2026-11-14 (authorized by the lead, no glasses)

| Item | Value |
|---|---|
| Deployment | Modal app `metalab`, version **v5**, commit **`5d1a6ee`** (origin/main), deployed by `oterodiazmateo1` with `modal deploy backend/app/modal_app.py`. Previous: v4 at `38cd91a` |
| Endpoint | `wss://junction26-vision--metalab-web.us-east.modal.run/ws` (`/health`: HTTP 200 `{"ok":true}` in 9.1 s, cold) |
| Test-client revision | `5d1a6ee`, `contracts/test.sh` on macOS (darwin 25.5.0) |
| Page input | `backend/ai/sample_frames/hamlet_act1_scene2.jpg`, as in the first run |
| Spoken input | "Explain this page." synthesized with macOS `say` to 16 kHz 16-bit WAV. No human voice |
| Expected grounding (independent) | `Hamlet` / `William Shakespeare` / `Act 1, Scene 2, lines 135-138`. The four sample lines ("O, that this too too solid flesh would melt" … "His canon 'gainst self-slaughter") are lines 135–138 of Act 1, Scene 2 in `backend/ai/data/plays/hamlet.json`. I found them by reading that file directly, not through the matcher. Source `Hamlet, public-domain text` / `https://www.gutenberg.org/ebooks/1524` |
| Unknown-book input | A rendered page of the *Moby-Dick* opening ("Call me Ishmael…"), 1280×1280 JPEG |

Inputs lived only in `/tmp` outside Git. No response text, transcript or media is kept here.

### Commands and outcomes

1. `env WS_URL=<endpoint> WS_SUCCESS_CASES=/tmp/<cases>.json WS_TIMEOUT_S=300 PIP_NO_INDEX=1 PIP_DRY_RUN=1 contracts/test.sh`
   ran 40 tests in 77.4 s, with **2 failures**. Both are in the strict live success check, and each fails on one thing only:
   - Strict typed case: `reading → thinking → drawing`, then one card. Book, location and
     source match exactly, and `image_url` is HTTPS. **Failed** only on `audio_url` null.
     Server latency: reading 1.4 s, thinking 5.0 s, drawing 13.9 s, total 20.2 s.
   - Strict audio case: `transcribing → reading → thinking → drawing`, then one card, with
     the same exact grounding. **Failed** only on `audio_url` null. Server latency:
     transcribing 2.7 s, reading 1.2 s, thinking 5.5 s, drawing 14.0 s, total 23.4 s.
2. Server logs for both requests show `speech synthesis failed, the phone will use its
   own voice: ClientError` (`backend/stt/speak.py`, model default
   `gemini-3.8-flash-tts`). The log records only the exception type, so the HTTP status
   and reason are not known yet.
3. Unknown-book typed probe (metadata only), in 24.2 s: stages `reading → thinking →
   drawing`, one card. `sources` = `[]` and `location` = `No source text`, so there is
   no invented citation (#218). But `book.title` = `Hamlet`, `author` =
   `William Shakespeare`, and the card title = `Hamlet`. A new session starts with
   Hamlet as its book (`backend/ai/session.py`), and nothing on this path replaces it.
   `models` = read `nemotron-3.5-super-vl`, reason `gemini-4-hydrogen`, image
   `gemini-nano-banana-2.1`.

### Open blockers after the rerun

- **Spoken output:** the Gemini TTS call fails with a client error on the deployed
  build. The next step is logging the status and reason, without content, and then
  fixing the request or model (`backend/stt/`, @Ahm3d-KA; TTS lane #185, @Marcus228).
- **Unknown-book label:** the no-source path keeps the session's default Hamlet title
  for a page from another book (`backend/ai/`, @Marcus228).
- **Not checked:** audible playback, display of the illustration on the glasses, and the
  iOS round trip on hardware with @maksymmatviievskyi.

## Live run, 2026-11-14 (authorized by the lead, no glasses)

| Item | Value |
|---|---|
| Endpoint | `wss://junction26-vision--metalab-web.us-east.modal.run/ws` (`/health`: HTTP 200 `{"ok":true}` in 7.0 s) |
| Test-client revision | `ae485be` (origin/main), `contracts/test.sh` from a worktree on macOS (darwin 25.5.0) |
| Deployment revision | Not exposed by the endpoint. Per `backend/app/DELIVERY_EVIDENCE.md` the live build predates #107 and #171–#174, so a redeploy is still needed |
| Page input | `backend/ai/sample_frames/hamlet_act1_scene2.jpg` (repo sample, 720×1280, Hamlet Act 1 Scene 2, "O, that this too too solid flesh would melt") |
| Spoken input | "Explain this page." synthesized with macOS `say` to 16 kHz 16-bit WAV (37 KB). No human voice |
| Expected grounding (independent) | Book `Hamlet` / `William Shakespeare` / `Act 1, Scene 2`, from the sample's known passage. Source `Hamlet, public-domain text` / `https://www.gutenberg.org/ebooks/1524` (the Project Gutenberg text in `backend/ai/data/plays/hamlet.json`) |

Inputs lived only in `/tmp` outside Git and were deleted after the run. No response
text, transcript or media is kept here.

### Commands and outcomes

1. `env WS_URL=<endpoint> WS_SUCCESS_CASES=/tmp/<cases>.json WS_TIMEOUT_S=300 PIP_NO_INDEX=1 PIP_DRY_RUN=1 contracts/test.sh`
   ran 40 tests in 92.5 s, with **2 failures**. Both failures are in the strict live success check. Everything else passed.
   - Schema-only remote conformance (placeholder recordings): every live reply
     validated against the schema. The drift is expected with placeholder media: the
     28-byte JPEG gives `internal`, and the empty WAV gives `stt_failed`.
   - Strict typed case: the complete `reading → thinking → drawing` sequence, then one
     card with a usable HTTPS `image_url`. It **failed** on `audio_url` null, on the
     book location and on the sources.
   - Strict audio case: `transcribing → reading → thinking → drawing`, then one card.
     The synthesized speech was transcribed and answered. It **failed** for the same
     three reasons.
2. A typed probe with the same frame gave the card's metadata (no content):
   `book` = Hamlet / William Shakespeare / **Act 1, Scene 1** (expected Scene 2).
   `sources` = Folger and MIT Shakespeare pages, the reasoning defaults, not the
   loader's Gutenberg citation. `models` = read `nemotron-3.5-super-vl`, reason
   `gemini-4-hydrogen`, image `gemini-nano-banana-2.1`. `audio_url` = null.
   Stages: reading and thinking at 40.9 s (container cold start), drawing at 42.4 s,
   card at 44.2 s.
3. A second typed probe (warm container) gave a card in 22.4 s, again with Act 1,
   Scene 1. `GET image_url` returned HTTP 200 `image/png`, 581,589 bytes, over HTTPS.

### What this shows, and the open blockers

- Working live: the typed and spoken paths reach a schema-valid card. Speech
  transcription works with synthesized speech. A human voice, with room noise and
  accent, is not tested yet. The generated illustration is retrievable.
- **Grounding:** the scene is wrong and the cited sources are generic, because
  `backend/app/pipeline.py` does not yet pass loader matches into the card. That is
  #129, which waits for @Marcus228's lane #194, then a redeploy.
- **Spoken output:** `audio_url` is null. Gemini TTS output is @Marcus228's lane #185.
- **Deploy:** the live build is older than #107 and #171–#174, so a redeploy is needed
  before the success check is repeated. The deployment revision is still unrecorded.
- **Not checked:** unknown-book no-source behaviour, audible playback, and the iOS
  round trip on hardware with @maksymmatviievskyi.

## Required evidence before closing #81

- [x] Record deployment revision: v5, `5d1a6ee` (see "Live rerun after redeploy").
- [x] Obtain permission for live endpoint/model usage and cleared test inputs.
- [x] Run `contracts/test.sh` locally with no live environment variables.
- [x] Run schema-only remote conformance with `WS_URL`.
- [x] Run the strict typed/audio cases with both `WS_URL` and `WS_SUCCESS_CASES`.
  The first run failed on grounding and audio. After the v5 redeploy, they fail only on `audio_url`.
- [ ] Verify generated illustration retrieval/display and audible answer playback.
  Retrieval passed. Display and playback were not checked.
- [ ] Record actual latency, model attribution, Hamlet citations and unknown-book
  no-source behavior. Latency, attribution and exact Hamlet citations are recorded for v5.
  The unknown-book card has no citation, but it is mislabelled as Hamlet.
- [ ] Obtain Maksym's real iOS typed/audio round-trip evidence, including device,
  SDK/client revision, status progression, resulting card and recovery limitations.
- [x] Record failures and missing checks, not only successful outcomes.

Keep raw inputs outside Git and logs, release them after the approved check, and
retain only cleared metadata. No automatic evidence upload or media download is
part of the checker. This checklist is not G0 acceptance or proof of lifecycle/auth.
