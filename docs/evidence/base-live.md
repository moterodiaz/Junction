# BASE live evidence, #81

Requirements: REQ-INT-01, REQ-BASE-01. PRD §§7, 12.2, 14.1.

**Not yet validated.** The live endpoint returns cards for typed and spoken
requests, but the strict success check fails on grounding and spoken output (see
"Live run, 2026-11-14"). The iOS round trip on hardware has not run.

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
     Real synthesized speech was transcribed and answered. It **failed** for the same
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
  transcription works with real speech. The generated illustration is retrievable.
- **Grounding:** the scene is wrong and the cited sources are generic, because
  `backend/app/pipeline.py` does not yet pass loader matches into the card. That is
  #129, which waits for @Marcus228's lane #194, then a redeploy.
- **Spoken output:** `audio_url` is null. Gemini TTS output is @Marcus228's lane #185.
- **Deploy:** the live build is older than #107 and #171–#174, so a redeploy is needed
  before the success check is repeated. The deployment revision is still unrecorded.
- **Not checked:** unknown-book no-source behaviour, audible playback, and the iOS
  round trip on hardware with @maksymmatviievskyi.

## Required evidence before closing #81

- [ ] Record deployment revision (the test-client revision is recorded above).
- [x] Obtain permission for live endpoint/model usage and cleared test inputs.
- [x] Run `contracts/test.sh` locally with no live environment variables.
- [x] Run schema-only remote conformance with `WS_URL`.
- [x] Run the strict typed/audio cases with both `WS_URL` and `WS_SUCCESS_CASES`.
  They ran and **failed** (above). Repeat after #129, #185 and a redeploy.
- [ ] Verify generated illustration retrieval/display and audible answer playback.
  Retrieval passed. Display and playback were not checked.
- [ ] Record actual latency, model attribution, Hamlet citations and unknown-book
  no-source behavior. Latency and attribution are recorded above. Citations are wrong
  today, and unknown-book behaviour is not checked.
- [ ] Obtain Maksym's real iOS typed/audio round-trip evidence, including device,
  SDK/client revision, status progression, resulting card and recovery limitations.
- [x] Record failures and missing checks, not only successful outcomes.

Keep raw inputs outside Git and logs, release them after the approved check, and
retain only cleared metadata. No automatic evidence upload or media download is
part of the checker. This checklist is not G0 acceptance or proof of lifecycle/auth.
