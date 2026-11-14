# MetaLab

A high-school student is reading Shakespeare and hits a passage they cannot picture. They ask for help out loud. The Ray-Ban Display glasses take one photo of the page, and a few seconds later an illustration of that passage appears on the lens with a two-line explanation, which is also read aloud. MetaLab is built for Junction 2026; the product requirements are in [`Junction-Prep/metalab_prd.md`](Junction-Prep/metalab_prd.md).

**Live backend:** `wss://junction26-vision--metalab-web.us-east.modal.run/ws` (health: `https://junction26-vision--metalab-web.us-east.modal.run/health`; see [Deploy](#deploy))
**Video:** coming before submission
**License:** MIT (see [`LICENSE`](LICENSE))

## What it does

- One invocation sends one camera frame and one spoken (or typed) command. Nothing is captured in the background.
- MetaLab reads the photographed page.
- It answers with the memory of the book session: which play, where the student is, and what they already asked.
- It draws an illustration made for the additive lens (bright subject on black) and shows it with a short caption.
- It speaks the answer, so the flow works with the display off.

## Architecture

```
Ray-Ban Display glasses
   camera frame, mic audio, lens display, speakers
        |  Bluetooth, Meta Wearables Device Access Toolkit (DAT)
        v
iOS app, Swift (ios/)            thin client, no model calls
   invoke -> one frame + one audio clip
        |  WebSocket (contracts/)
        v
FastAPI orchestrator on Modal (backend/app/)
   1. speech to text + command match        (backend/stt/)
   2. Nemotron 3.5 Super VL reads the page  (backend/ai/)
   3. Gemini reasons: passage + book session -> explanation + image prompt
   4. Gemini generates the image
   5. image stored, served at an HTTPS URL
        |
        v
iOS app sends a DAT display layout (Image + Text) to the lens
and plays the spoken answer
```

All logic stays in the backend. The phone app only captures, sends, shows and speaks. The WebSocket messages are defined once in [`contracts/ws-messages.schema.json`](contracts/ws-messages.schema.json).

## Models used

- **Read the page:** NVIDIA Nemotron 3.5 Super VL (`nemotron-3.5-super-vl`) through its OpenAI-compatible API at `https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1`, with thinking disabled (`chat_template_kwargs.enable_thinking=false`, see [`backend/ai/page_reader.py`](backend/ai/page_reader.py)). The output is text only and goes to the reasoning step. Frames are processed in memory and never stored.
- **Page reading fallback:** Gemini `gemini-4-hydrogen` reads the same frame if Nemotron does not answer in time (`MODEL_READ_FALLBACK`, same file).
- **Reason:** Gemini `gemini-4-argon` with a per-book session ([`backend/ai/reasoning.py`](backend/ai/reasoning.py), [`backend/ai/session.py`](backend/ai/session.py)).
- **Draw:** Gemini `gemini-nano-banana-2.1` ([`backend/ai/image.py`](backend/ai/image.py)), with prompts conditioned for a black background.
- **Speak:** Gemini `gemini-3.8-flash-tts` ([`backend/stt/speak.py`](backend/stt/speak.py)); the phone falls back to the system voice.
- **Speech to text:** faster-whisper `small.en` on Modal ([`backend/stt/engine.py`](backend/stt/engine.py)).

Every card reports which models actually produced it in its `models` field (`contracts/ws-messages.schema.json`).

## Tracks

| Track | What we use it for | Where |
|---|---|---|
| Meta: AI glasses | capture, lens display, voice invocation | `ios/` |
| Google DeepMind: Gemini API | reasoning with book memory, illustration, spoken answer | `backend/ai/`, `backend/stt/speak.py` |
| NVIDIA: Nemotron | reading the photographed page | `backend/ai/page_reader.py` |
| Modal | the FastAPI WebSocket backend and Whisper | `backend/app/modal_app.py` |
| Tieto: Earned trust in AI code | the bounded agent PR pipeline | `AGENTS.md`, `.github/workflows/` |

## Run and test

```sh
backend/test.sh      # backend unit tests (builds backend/.venv)
contracts/test.sh    # schema, fixtures, and recorded exchanges replayed against the backend
ios/test.sh          # iOS-side client tests
```

Run the backend locally after `backend/test.sh` has built its virtualenv:

```sh
cd backend && .venv/bin/uvicorn app.main:app --reload
```

Without keys the stages run as offline stubs. `WS_URL=wss://…/ws contracts/test.sh` replays the exchanges against a deployed backend (see [`contracts/README.md`](contracts/README.md)).

## Deploy

See [`backend/README.md`](backend/README.md) (Modal).

## Privacy

- One frame and one audio clip per invocation, only after the user asks.
- The backend processes the frame and audio in memory and drops them once the card is built, without writing them to disk. On the phone, enabling "Keep a sample frame for the reading test" saves captured photos in the app's Documents folder.
- Generated images stay in backend memory so the lens can load them. Closing the connection or starting a new book does not delete them. Later image requests remove images for sessions idle longer than `IMAGE_SESSION_TTL_SECONDS` (one hour by default).
- The book session holds text only: book, position, earlier questions and answers.
- If a frame has no readable text, MetaLab says so and discards it.

## Repository map

- `ios/`: the Swift phone app (capture, WebSocket client, lens layout, speech).
- `backend/app/`: FastAPI orchestrator, config, pipeline, error mapping, Modal app.
- `backend/stt/`: speech to text, command matching, spoken answer.
- `backend/ai/`: page reading, Hamlet source text, book session, reasoning, image generation.
- `contracts/`: the WebSocket schema, fixtures, recorded exchanges and the conformance harness.
- `tools/`: team scripts (`board`, `task`, `wt`, `kickoff`, `onboard`).
- `docs/`: team process documentation.
- `Junction-Prep/`: the PRD and the challenge strategy.

## Team process

Coding agents coordinate on a pinned GitHub issue; see [`docs/AGENT_BOARD.md`](docs/AGENT_BOARD.md) and [`AGENTS.md`](AGENTS.md).
