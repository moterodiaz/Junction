# BASE live evidence, #81

Requirements: REQ-INT-01, REQ-BASE-01. PRD §§7, 12.2, 14.1.

**Not yet validated.** The local success-check tests use synthetic responses.
No live model call, hardware run or deployment is authorized by those tests.
The historical schema-only run returned errors and does not demonstrate success.

## Required evidence before closing #81

- [ ] Record deployment revision and test-client revision.
- [ ] Obtain permission for live endpoint/model usage and cleared test inputs.
- [ ] Run `contracts/test.sh` locally with no live environment variables.
- [ ] After approval, run schema-only remote conformance with `WS_URL`.
- [ ] After approval, run the strict typed/audio cases with both `WS_URL` and
  `WS_SUCCESS_CASES`, using independent expected grounding and real cleared media.
- [ ] Verify generated illustration retrieval/display and audible answer playback.
- [ ] Record actual latency, model attribution, Hamlet citations and unknown-book
  no-source behavior, without retaining user media, transcripts or response text.
- [ ] Obtain Maksym's real iOS typed/audio round-trip evidence, including device,
  SDK/client revision, status progression, resulting card and recovery limitations.
- [ ] Record failures and missing checks, not only successful outcomes.

Keep raw inputs outside Git and logs, release them after the approved check, and
retain only cleared metadata. No automatic evidence upload or media download is
part of the checker. This checklist is not G0 acceptance or proof of lifecycle/auth.
