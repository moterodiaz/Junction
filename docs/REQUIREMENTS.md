# Requirements registry

Every task issue and every PR names at least one requirement id from this table (AGENTS.md §3 rule 7). The ids are stable: an id is never renumbered or reused, and a retired requirement keeps its row with "retired" in the last column. The PRD (`Junction-Prep/metalab_prd.md`) is the source of truth; if this table and the PRD disagree, the PRD wins and this table is fixed by PR.

To add a requirement, add a row in the same PR as the task that needs it. Use the next free number in its group.

| ID | PRD | Requirement | Acceptance check | Delivered by |
|---|---|---|---|---|
| REQ-WS-01 | §7 | `invoke`, `status`, `card` and `error` messages validate against `contracts/ws-messages.schema.json` | `contracts/test.sh` | #71, #73, #85 |
| REQ-WS-02 | §7 | An `invoke` carries exactly one of `audio` or `text`; `text` is the no-glasses test path | `contracts/test.sh` (fixtures) | #71, #68 |
| REQ-WS-03 | §7 | Malformed input gets a fixed `error` reply and never closes the socket or echoes the input | `backend/tests/test_ws.py` | #78, #85 |
| REQ-INT-01 | §7 | The recorded exchanges replay against a deployed backend over a real socket and every reply passes the schema | `WS_URL=wss://…/ws contracts/test.sh` | #87 (live run: #81) |
| REQ-PRIV-01 | §6 | A request writes nothing to disk; the frame and audio are dropped once the card is built | `test_errors_privacy.py::test_a_request_writes_nothing_to_disk` | #86 |
| REQ-PRIV-02 | §6 | Logs and error replies never contain user text, audio or frame data | `test_ws.py::test_invalid_invoke_error_does_not_echo_input`, `test_errors_privacy.py` | #78, #104 |
| REQ-ERR-01 | §7 | Every failure maps to `no_text_found`, `stt_failed`, `model_timeout` or `internal`, with `retryable` | `backend/tests/test_errors_privacy.py` | #86 |
| REQ-LAT-01 | §9 | One latency summary line per request covering every stage | `backend/tests/test_latency.py` | #88 |
| REQ-LAT-02 | §9 | Stage and request timeouts sit inside the phone's 30 s idle and 90 s overall deadlines | `backend/tests/test_deadlines.py` | #96 |
| REQ-STT-01 | §5 L0 | Spoken commands match the L0 command words (explain, draw, who is this); anything else gives `stt_failed` | `backend/tests/test_stt.py` | #79, #106 |
| REQ-READ-01 | §4 | The page is read by Nemotron 3.5 Super VL with thinking off and text out; a blank page gives `no_text_found` | `backend/tests/test_page_reader.py`, `backend/ai/measure_accuracy.py` | #74 |
| REQ-READ-02 | §4 | If Nemotron does not answer in time, Gemini reads the same frame, and `card.models.read` names the model that actually read | `backend/tests/test_page_reader_fallback.py` | #99 |
| REQ-REASON-01 | §2, §4 | One session per book; the tenth answer can use the first nine | `test_reasoning.py::test_tenth_question_uses_first_nine` | #77 |
| REQ-SRC-01 | §2 | Hamlet explanations cite act, scene and line from the loaded public-domain text; other books are marked "no source text" | `backend/tests/test_source_loader.py` | #80 (pipeline wiring open) |
| REQ-IMG-01 | §4 | The lens image has a black background, is served over https, and is optional: a slow or failed image never costs the card | `backend/tests/test_image.py`, `backend/tests/test_pipeline.py` | #75, #104, #105 |
| REQ-TTS-01 | §3 | The spoken answer is served at `card.audio_url`; the phone falls back to the system voice | `backend/tests/test_speak.py` | #94 |
| REQ-DEPLOY-01 | §4 | A public `wss://` URL on Modal; secrets come only from the `metalab` Modal secret and a missing one fails at startup | `backend/tests/test_startup.py`, `backend/README.md` | #84, #92, #93, #98, #107 |
| REQ-IOS-01 | §3, §6 | One frame and one clip per invocation; the camera stops before the lens draws | `ios/test.sh` (proxy tests) | #70 |
| REQ-PROC-01 | AGENTS.md | Every change traces to a task issue and a REQ id, and no bot merges without the gates in AGENTS.md §3 rule 9 | this file, `docs/TIETO_CONCEPT_CARD.md` | #117 |
