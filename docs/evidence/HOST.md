# Host and track evidence: Meta, Gemini, Modal, Nemotron, Verda, ElevenLabs (HOST-D1, #138)

Requirement: REQ-HOST-01. PRD §12.12. Owner: Mateo (@moterodiaz, lead).

This file keeps one state per challenge, and records separately what ran live, what is only configured, and what is missing (credentials, forms, sponsor confirmation). **No track is submitted, and none is marked submission-ready.** The drafts in section 3 are not sent anywhere. Sending them needs the lead's separate decision.

Sources: `docs/evidence/base-live.md` (live runs v1 to v7; v6 and v7 in "Live reruns after v6 and v7"), `backend/ai/DELIVERY_EVIDENCE.md` (configured models), `backend/app/DELIVERY_EVIDENCE.md`, `ios/DELIVERY_EVIDENCE.md`. Revision: `main` at `5991baa`, 2026-11-15 (live deploy v10, `99ae635`).

## 1. Per-challenge state

| Challenge | State | What ran live (dated) | Missing |
|---|---|---|---|
| Meta (main 342) | implementation present, built on hardware | Lead report, 2026-11-15: the Xcode build runs with the Meta Display glasses on a teammate's machine. No dated rehearsal record yet | Device, DAT and Xcode versions and the rehearsal outcomes (capture, display, audio, recovery) recorded in `ios/DELIVERY_EVIDENCE.md` (#140, #81, #141) |
| Gemini (tech 48) | implementation present, partly validated | 2026-11-14, first build and v5 probes: cards report reasoning `gemini-4-hydrogen` and image `gemini-nano-banana-2.1` (the v6 and v7 records print no model names). The illustration was fetched over HTTPS (HTTP 200, `image/png`) on the first build only; not repeated on v5 to v7. The strict runs on v5, v6 and v7 pass the exact Hamlet grounding and source and get an HTTPS `image_url` (`base-live.md`); the image itself was not fetched on those runs | Speech moved to ElevenLabs (v10, row below): the Gemini key has no speech access (v8, `base-live.md`), so Gemini TTS is only the fallback. `models.reason` is the requested name, not one the provider confirmed. Billing and quota not checked |
| Modal (tech 40) | implementation present, partly validated | App `metalab` deployed v5 `5d1a6ee`, v6 `53b35ff` and v7 `9d10e28` by the lead. Public endpoint `wss://junction26-vision--metalab-web.us-east.modal.run/ws`, `/health` 200. Whisper `small.en` runs on Modal: synthesized speech was transcribed live (`transcribing` stage, then a correct card) | A human voice has not been tested. No load test. GPU not used; the CPU image only |
| Nemotron (tech 46) | implementation present, live contribution seen | The metadata probes on the first live build and on v5 reported read model `nemotron-3.5-super-vl`, so the Gemini reading fallback was not used on those requests. The strict runs on v6 and v7 do not print `models` | The model-use note (draft in section 3) is not submitted. A per-request share of Nemotron vs fallback over many requests is not measured |
| Verda (tech 56) | implementation present (DataCrunch endpoint, confirmed by the lead) | Lead confirmation, 2026-11-15: the deployed secret sets `NVIDIA_BASE_URL` to a DataCrunch (now Verda) container endpoint. The repo default stays NVIDIA's hosted API (`integrate.api.nvidia.com`); only the deployed secret points at Verda. Live cards that reported read model `nemotron-3.5-super-vl` (first build, v5) were read through the deployed secret | Verda's written confirmation of eligibility, if they require one. The Discord summary (section 3) is final but not posted; posting stays with the lead. No move off Modal |
| ElevenLabs (tech 50) | implementation present, live on v10 | v10 `99ae635` (2026-11-15): the strict run passes for typed and spoken requests, including `audio_url`. An extra request returned HTTP 200 `audio/wav`, 28.6 s at 24 kHz (`base-live.md`, "Live reruns after v8, v9 and v10"). ElevenLabs `eleven_flash_v2_5` speaks first; Gemini is tried once if it fails, within one 20 s budget | Nobody has listened to the clip yet. The card's `models` field does not name the speech model. Playback through the glasses (#140) |

## 2. Endpoint and model ledger

| Role | Configured (repo) | Reported live | Provenance |
|---|---|---|---|
| Backend host | Modal app `metalab`, `debian_slim` Python 3.12 | v7 `9d10e28` | `modal deploy backend/app/modal_app.py`, lead's Modal profile |
| Page reading | `nvidia/nemotron-3.5-super-vl-120b-a12b` at `integrate.api.nvidia.com/v1` (repo default); deployed: DataCrunch (now Verda) endpoint | `nemotron-3.5-super-vl` (first build and v5 probes) | `backend/ai/page_reader.py`; deployed host confirmed by the lead, 2026-11-15 |
| Reading fallback | `gemini-4-hydrogen` | not seen live | `backend/ai/page_reader.py` |
| Reasoning | `gemini-4-argon` (default) | `gemini-4-hydrogen` | Differs from the default; the secret probably overrides `MODEL_REASON`. Not checked |
| Image | `gemini-nano-banana-2.1` | `gemini-nano-banana-2.1` | `backend/ai/image.py` |
| Speech out | ElevenLabs `eleven_flash_v2_5`, then Gemini `gemini-3.8-flash-tts` once, then the phone's system voice | `audio_url` returned on v10 (`audio/wav`); the card does not name the speech model | `backend/stt/elevenlabs.py`, `backend/stt/speak.py`; v6 to v9 failed on Gemini TTS (`base-live.md`; #226), v10 attached the ElevenLabs secrets (#246) |
| Speech in | faster-whisper `small.en` on Modal | used (spoken case reached a card) | `backend/stt/` |

No keys, prompts, page text or responses are recorded here.

## 3. Drafts (not sent)

**Nemotron model-use note (draft):**
> MetaLab reads a photographed book page with NVIDIA Nemotron (`nemotron-3.5-super-vl`, served from a Verda, formerly DataCrunch, endpoint). Nemotron is the first step of every request: it turns the page image into text, which grounds the explanation in the exact act, scene and line of the public-domain text. Gemini is a fallback reader used only when Nemotron is slow or fails; each card reports which reader ran. In the live cards we inspected on 2026-11-14, the reader was Nemotron.

**Verda summary (final draft, not posted; the lead posts it in Verda's Junction Discord channel with the submission link):**
> MetaLab is a reading companion for Meta Ray-Ban Display glasses, built at Junction 2026. Every request starts on Verda: our Modal backend sends the photographed book page to NVIDIA Nemotron 3.5 Super VL, served from a Verda (formerly DataCrunch) container endpoint through its OpenAI-compatible API, with thinking turned off. Nemotron turns the page into text, and that text grounds Gemini's explanation and lens illustration in the exact act, scene and lines of the public-domain play. Frames are processed in memory and never stored. Gemini reads the page only if the Verda call misses its budget, and each card names the reader that ran. Repo: https://github.com/moterodiaz/Junction. Submission: <link>.

## 4. Limits

- Live evidence comes from a few scripted requests (one sample page, one synthesized voice prompt, one unknown-book page per deploy), not real use.
- "Reported" model names come from the card, which the backend fills in; only `models.read` reflects which reader actually returned.
- Sponsor forms, Discord posts and submissions are out of scope for agents.
