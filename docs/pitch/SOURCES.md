# Sources for the pitch drafts

Every number or model claim in `gemini-pitch.md` and `submission-text.md` carries a tag like **[E1]** that points here. Paths are relative to the repository root; PRs are in moterodiaz/Junction. Checked against `main` at b1928c6 (2026-11-14).

| Tag | What it supports | Source |
|---|---|---|
| E1 | One live request, 14:05 on 2026-11-14: card in 25.0 s (reading 0.3 s, thinking 10.1 s, drawing 13.5 s); `card.models` read `nemotron-3.5-super-vl`, reason `gemini-4-hydrogen`, image `gemini-nano-banana-2.1`; `image_url` set; `audio_url` null | `backend/app/DELIVERY_EVIDENCE.md`, section "Live checks", 14:05 row |
| E2 | `WS_URL=…/ws contracts/test.sh` against the live server: 17 tests, every live reply passed the schema | `backend/app/DELIVERY_EVIDENCE.md`, "Live checks", ~15:25 row |
| E3 | Not yet checked: real speech on the live server, live spoken-answer audio, grounded citations, glasses hardware, a redeploy of current `main` | `backend/app/DELIVERY_EVIDENCE.md`, section 6 "Not checked, and why" |
| E4 | Page reading: Nemotron 3.5 Super VL first; Gemini (`gemini-4-hydrogen`) reads the same frame if Nemotron misses an 8 s budget; `card.models.read` names the reader that succeeded | `backend/ai/page_reader.py` (`DEFAULT_READ_FALLBACK_AFTER_S = 8.0`), PR #74, PR #99, REQ-READ-01, REQ-READ-02 |
| E5 | Lens image: Gemini image model `gemini-nano-banana-2.1`; prompt asks for a pure black background because the Ray-Ban Display lens is additive (black stays transparent) | `backend/ai/image.py` (`format_display_prompt`), PR #75, PR #105, REQ-IMG-01 |
| E6 | Reasoning over the passage plus the book session's history; the tenth answer can use the first nine (offline test) | `backend/ai/reasoning.py`, `backend/ai/session.py`, `backend/tests/test_reasoning.py::test_tenth_question_uses_first_nine`, PR #77, REQ-REASON-01 |
| E7 | Spoken answer: Gemini TTS (`gemini-3.8-flash-tts`) served at `card.audio_url`, phone falls back to the system voice; on the live card `audio_url` was null | `backend/stt/speak.py`, PR #94, REQ-TTS-01; live result in E1 |
| E8 | Reasoning model default in code is `gemini-4-argon`; the live deploy reported `gemini-4-hydrogen` (E1), so the deploy overrides the default | `backend/app/config.py` (`MODEL_REASON`), PR #67 |
| E9 | Privacy: the offline backend writes nothing to disk for a request; no frame or audio is kept after the card; the detectors catch a deliberately leaky stage. The test covers the backend only, not the iPhone "Keep a sample frame" option (off by default, saves to `Documents/sample-frames`, `ios/MetaLab/AppModel.swift`) | `backend/tests/test_errors_privacy.py::PrivacyTest`, PR #86, REQ-PRIV-01 |
| E10 | Deadlines: 25 s per stage and 85 s per request, inside the phone's 30 s idle and 90 s overall limits | `backend/app/pipeline.py` (`STAGE_TIMEOUT_S`, `REQUEST_TIMEOUT_S`), PR #96 |
| E11 | Backend on Modal with a public `wss://` endpoint | `backend/app/modal_app.py`, PR #84; config in `backend/app/DELIVERY_EVIDENCE.md` |
| E12 | Strict live success checks (illustration retrieval, audible playback, citations) are not yet validated | `docs/evidence/base-live.md`, PR #191, issue #81 |
| E13 | Gemini voice feedback and a decision model in the workflow: **planned**, lane task still open | issue #185 (REQ-VOICE-02) |
| E14 | Grounded act/scene/line citations from the public-domain text: **planned**, not wired into answers | issue #129 (REQ-SRC-01); loader in PR #80, PR #179 |
| E16 | The iPhone app sends one frame and one clip per invocation, and the camera stops before the lens draws (proxy tests; no hardware run recorded) | REQ-IOS-01, `ios/test.sh`, PR #70; hardware gap in E3 |
| E15 | How the team trusted agent-written code: 46 PRs merged, escapes, the required `trust` check and a live drill | `docs/evidence/TRUST-PIPELINE.md` |

Derived figure: 94% of the 25.0 s live request was Gemini work = (10.1 s thinking + 13.5 s drawing) / 25.0 s, from E1.
