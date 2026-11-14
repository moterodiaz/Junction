# Host and track evidence: Meta, Gemini, Modal, Nemotron, Verda (HOST-D1, #138)

Requirement: REQ-HOST-01. PRD §12.12. Owner: Mateo (@moterodiaz, lead).

This file keeps one state per challenge, and records separately what ran live, what is only configured, and what is missing (credentials, forms, sponsor confirmation). **No track is submitted, and none is marked submission-ready.** The drafts in section 3 are not sent anywhere. Sending them needs the lead's separate decision.

Sources: `docs/evidence/base-live.md` (live runs v1 to v7; v6 and v7 in "Live reruns after v6 and v7"), `backend/ai/DELIVERY_EVIDENCE.md` (configured models), `backend/app/DELIVERY_EVIDENCE.md`, `ios/DELIVERY_EVIDENCE.md`. Revision: `main` at `9d10e28`, 2026-11-15.

## 1. Per-challenge state

| Challenge | State | What ran live (dated) | Missing |
|---|---|---|---|
| Meta (main 342) | implementation present | Nothing on hardware. The iOS app target built once without signing at `6b3d353` | DAT capture, display and audio on glasses; five hardware rehearsals (#140, @maksymmatviievskyi) |
| Gemini (tech 48) | implementation present, partly validated | 2026-11-14, first build and v5 probes: cards report reasoning `gemini-4-hydrogen` and image `gemini-nano-banana-2.1` (the v6 and v7 records print no model names). The illustration was fetched over HTTPS (HTTP 200, `image/png`) on the first build only; not repeated on v5 to v7. Grounded Hamlet citation correct on v5; on v6 and v7 only that grounding and image tests pass, per `base-live.md` | Speech (`gemini-3.8-flash-tts`) fails live on every deploy so far (#226). `models.reason` is the requested name, not one the provider confirmed. Billing and quota not checked |
| Modal (tech 40) | implementation present, partly validated | App `metalab` deployed v5 `5d1a6ee`, v6 `53b35ff` and v7 `9d10e28` by the lead. Public endpoint `wss://junction26-vision--metalab-web.us-east.modal.run/ws`, `/health` 200. Whisper `small.en` runs on Modal: synthesized speech was transcribed live (`transcribing` stage, then a correct card) | A human voice has not been tested. No load test. GPU not used; the CPU image only |
| Nemotron (tech 46) | implementation present, live contribution seen | The metadata probes on the first live build and on v5 reported read model `nemotron-3.5-super-vl`, so the Gemini reading fallback was not used on those requests. The strict runs on v6 and v7 do not print `models` | The model-use note (draft in section 3) is not submitted. A per-request share of Nemotron vs fallback over many requests is not measured |
| Verda (tech 56) | candidate | No recorded Verda request. The repo default reader endpoint is NVIDIA's hosted API (`integrate.api.nvidia.com`), but the deployed secret can override `NVIDIA_BASE_URL`, so the live host is unverified | The deployed `NVIDIA_BASE_URL` host (@Marcus228, host only); Verda's written confirmation of eligibility; a dated Nemotron request through a Verda endpoint. The Discord summary is drafted only (section 3). No move off Modal |

## 2. Endpoint and model ledger

| Role | Configured (repo) | Reported live | Provenance |
|---|---|---|---|
| Backend host | Modal app `metalab`, `debian_slim` Python 3.12 | v7 `9d10e28` | `modal deploy backend/app/modal_app.py`, lead's Modal profile |
| Page reading | `nvidia/nemotron-3.5-super-vl-120b-a12b` at `integrate.api.nvidia.com/v1` | `nemotron-3.5-super-vl` (first build and v5 probes) | `backend/ai/page_reader.py`; the deployed secret's base URL is not visible to the lead's agent |
| Reading fallback | `gemini-4-hydrogen` | not seen live | `backend/ai/page_reader.py` |
| Reasoning | `gemini-4-argon` (default) | `gemini-4-hydrogen` | Differs from the default; the secret probably overrides `MODEL_REASON`. Not checked |
| Image | `gemini-nano-banana-2.1` | `gemini-nano-banana-2.1` | `backend/ai/image.py` |
| Speech out | `gemini-3.8-flash-tts` | none (`audio_url` null) | v6: `400 INVALID_ARGUMENT` ("Unknown name speechConfig"); v7: Interactions API `404` "Model 'gemini-3.8-flash-tts' not found" (`base-live.md`, "Live reruns after v6 and v7"; #226) |
| Speech in | faster-whisper `small.en` on Modal | used (spoken case reached a card) | `backend/stt/` |

No keys, prompts, page text or responses are recorded here.

## 3. Drafts (not sent)

**Nemotron model-use note (draft):**
> MetaLab reads a photographed book page with NVIDIA Nemotron (`nemotron-3.5-super-vl`; hosting provider unverified until the deployer confirms the host). Nemotron is the first step of every request: it turns the page image into text, which grounds the explanation in the exact act, scene and line of the public-domain text. Gemini is a fallback reader used only when Nemotron is slow or fails; each card reports which reader ran. In the live cards we inspected on 2026-11-14, the reader was Nemotron.

**Verda summary (draft, blocked):** not writable truthfully yet. Whether any request has gone through a Verda endpoint is unverified, because the deployed host is unknown. A summary needs the three items in section 1 first.

## 4. Limits

- Live evidence comes from a few scripted requests (one sample page, one synthesized voice prompt, one unknown-book page per deploy), not real use.
- "Reported" model names come from the card, which the backend fills in; only `models.read` reflects which reader actually returned.
- Sponsor forms, Discord posts and submissions are out of scope for agents.
