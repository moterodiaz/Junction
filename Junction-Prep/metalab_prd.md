# MetaLab: product requirements

**Event:** Junction 2026. Final submission Sunday 15.11 at 10:00 sharp.
**Team:** @moterodiaz (lead), @Marcus228, @Ahm3d-KA, @maksymmatviievskyi
**Status:** replaces the Wearable AR Context Engine PRD (still in git history and in the `moterodiaz/Junction-Prep` repo). The work itself lives in GitHub issues labelled `task`; this document is the reference they point to.

Facts about Meta, Gemini and NVIDIA in this document were checked against the vendors' own docs on 2026-11-14. Anything we could not confirm is listed in section 10 as an open question with an owner. Do not promote an open question to a fact without testing it on the hardware.

## 1. Pitch and target user

A high-school student is reading Shakespeare and hits a passage they cannot picture. They ask for help out loud. The glasses take one photo of the page, and a few seconds later an illustration of that passage appears on the lens with a two-line explanation, which is also read aloud.

The target user is a student working through an assigned text. We prove that one scenario end to end. Textbooks, manuals and blueprints are the same pipeline with different prompts, and we say so in the pitch, but we only build them as stretch goals.

## 2. Why this is not Meta AI

This is the team's positioning. Sharpen it with the Meta mentors before the pitch.

- **Memory that lasts the whole book.** MetaLab keeps a session per book: which play, which act, who the characters are, what the student already asked. The answer to the tenth question uses the first nine.
- **Sources for that book.** For the demo plays we load the public-domain text, so explanations can quote and place the passage (act, scene, line) instead of guessing from one photo.
- **A picture, not a paragraph.** The answer is an illustration built for the lens, with a short caption and a spoken version.

## 3. Base-case flow

1. The student says "Hey Meta, start <app name>" or taps the button in the phone app.
2. The phone app records a short spoken command from the glasses microphone and grabs one frame from the glasses camera.
3. Both go to the backend over one WebSocket message.
4. The backend transcribes the command, reads the page, reasons over the passage with the book session, and generates an illustration.
5. The lens shows progress while this runs ("Reading page", "Drawing"), then the card: image plus caption.
6. The answer is spoken through the glasses speakers. The flow must make sense with the display off.

Capture happens only on invocation. There is no continuous video stream, for cost and for privacy.

## 4. Architecture

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

All logic stays in the backend. The phone app only captures, sends, shows and speaks, so the pipeline can be built and tested without glasses.

### Why a phone app and not a Meta web app

The team sync assumed a web app running on the glasses. Meta's docs rule that out: Web Apps on Ray-Ban Display cannot use the camera or the microphone. From Meta's `llms.txt`: "Only the Device Access Toolkit can use the glasses' camera or capture microphone audio." The Device Access Toolkit is a phone SDK (iOS Swift or Android Kotlin). The team chose iOS.

What that costs us: there is no HTML on the lens. A DAT display is built from a small set of components (FlexBox, Text, Image, Button, Icon, Video), and the app sends a whole layout each time.

### Client facts we build on (Meta docs)

- **Display.** 600×600. The phone app sends layouts over Bluetooth. The `Image` component loads from a URL, so the backend has to serve the generated image over HTTPS. On iOS, `send()` replaces the entire display; there are no partial updates. The user must start a display session explicitly, and there is one display capability per session.
- **The lens is additive.** Dark pixels disappear and bright ones show. Generated images need a black background and a bright, high-contrast subject.
- **Voice invocation.** "Hey Meta, start <app name>" launches or foregrounds the app and delivers an invocation event. It is configured in the Meta Developer Center, needs no camera or mic permission, and every invocation must be answered exactly once. There is no custom wake word.
- **Microphone.** Bluetooth HFP gives mono voice at 16 kHz or 8 kHz, beamformed to the wearer. iOS uses `.allowBluetoothHFP`. The HFP route has to be settled before a DAT camera stream starts.
- **Camera.** A stream is configured with `StreamConfiguration` (iOS resolutions 720×1280, 504×896, 360×640; frame rates 2, 7, 15, 24, 30), and a single frame can be taken from it. Standalone `capturePhoto()` is beta: usable here, but an app that uses it cannot be published. A stream and a photo capture cannot run at the same time.
- **Sessions.** `wearables.createSession(deviceSelector: AutoDeviceSelector(wearables: wearables))`, then `session.start()` and `session.stateStream()`. States are STOPPED, STARTED, PAUSED. One session per device. Folding the glasses forces STOPPED and a new session is needed afterwards.
- **Permissions.** The app registers once through the Meta AI app, then requests camera permission; the user picks "Allow once" or "Allow always". Without registration, permission requests fail. In Developer Mode only one third-party app can be registered at a time, and registering a new one unregisters the previous one.
- **Privacy.** "Meta does not access photos/videos or audio that is transferred directly from the glasses to the third-party mobile app."

Agents working in `ios/` should read `https://wearables.developer.meta.com/llms.txt?product=all&version=1.0&document=products/dat/sections/guides` before writing code.

### Models

| Step | Model | Notes |
|---|---|---|
| Read the page | `nvidia/nemotron-3.5-super-vl-120b-a12b` | OpenAI-compatible API at `https://integrate.api.nvidia.com/v1`, key in `NVIDIA_API_KEY`. Image goes in as an `image_url` content part (https URL or `data:image/jpeg;base64,...`). Text output only. Thinking can be turned off with `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`. |
| Reason | `gemini-4-argon` to start | `gemini-4-carbon` is stronger and slower, `gemini-4-hydrogen` is faster. 1M-token context, which is what makes whole-book memory cheap to build. |
| Draw | `gemini-nano-banana-2.1` | `gemini-3.1-flash-lite-image` is the faster, cheaper fallback. Image models need pay-as-you-go billing. |
| Speech to text | faster-whisper on Modal | `gemini-3.5-transcribe` is the alternative if the GPU cold start hurts. |
| Spoken answer | `gemini-3.8-flash-tts` | ElevenLabs replaces it in L2. |

Do not use `gemini-2.5-flash`, `gemini-2.5-flash-image` or Imagen. They are deprecated or shut down.

Secrets live in Modal secrets, never in the repo. Variable names other than `NVIDIA_API_KEY` are fixed in issue A2.

## 5. Layered goals

Each level ships on its own. If we miss a level, the one below is still a working product.

| Level | What it adds | Ships when |
|---|---|---|
| **L0 base** | Fixed command words ("explain", "draw", "who is this"). One book. Image card on the lens, spoken answer. | Must ship. |
| **L1** | Natural-language intent instead of command words. | After L0 runs end to end on the glasses. |
| **L2 stretch** | ElevenLabs voice, follow-up questions by voice. | Only if L1 is done by Saturday evening. |
| **L3 stretch** | Blueprint mode for the Stoa challenge. | Only if L2 is done. |

## 6. What the Meta judges score

The Meta rubric is four items at 25% each. Each one maps to something we build.

| Rubric item | What we show |
|---|---|
| Creativity and use case | First-person reading help that a phone screen cannot give: the student keeps the book open and looks at the page. |
| Technical execution | Explicit handling of permission denied, session PAUSED and STOPPED, hinges closed, Bluetooth link lost, backend timeout, unreadable page. Each has a visible state and a way back. |
| Real-world value | One named user (a student with an assigned text), a book the audience hands over, and a believable school pilot. |
| UX: input, accessibility, trust | Voice in, and an answer that works by audio alone. A clear "listening / capturing" state on lens and phone. One frame per invocation, nothing captured in the background, frames not stored. |

Data handling, stated plainly because it is a scoring item and a real concern in Europe:

- One frame and one audio clip per invocation, only after the user asks.
- The frame and the audio are processed in memory and dropped once the card is built. They are never written to disk.
- The generated image is kept for the session so the lens can load it, then deleted.
- The book session holds text only: book, position, earlier questions and answers.
- The camera is meant to be pointed at a page. If a frame has no readable text, we say so and discard it.

## 7. WebSocket contract (draft)

Issue A1 owns the final schema in `contracts/`. This draft exists so the four streams can start in parallel.

Phone to backend:

```json
{
  "type": "invoke",
  "request_id": "uuid",
  "session_id": "uuid",
  "frame": { "mime": "image/jpeg", "b64": "..." },
  "audio": { "mime": "audio/wav", "b64": "..." },
  "text": null
}
```

`text` carries a typed command instead of `audio`. It is how the backend gets tested without glasses.

Backend to phone:

```json
{ "type": "status", "request_id": "uuid", "stage": "transcribing | reading | thinking | drawing" }
```

```json
{
  "type": "card",
  "request_id": "uuid",
  "title": "Hamlet, Act 3, Scene 1",
  "caption": "Hamlet asks whether enduring pain is nobler than ending it.",
  "image_url": "https://.../img/<id>.png",
  "speech_text": "Hamlet is alone, weighing whether to keep living...",
  "audio_url": null,
  "book": { "title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1" },
  "sources": [ { "title": "Hamlet, public-domain text", "url": "https://..." } ],
  "models": { "read": "...", "reason": "...", "image": "..." }
}
```

```json
{ "type": "error", "request_id": "uuid", "code": "no_text_found | stt_failed | model_timeout | internal", "message": "...", "retryable": true }
```

If `audio_url` is null the phone speaks `speech_text` with the system voice.

## 8. Demo script

1. One sentence: who this is for and what they are about to see.
2. A teammate reads a page of Hamlet with the glasses on. "Hey Meta, start <app name>." "Draw this." The card appears; the phone mirrors the lens on the projector.
3. A second question on the next page that only makes sense with memory ("why is he angry at her now?").
4. An audience member hands over a book. Same flow. If we have no source text for it, the card says so.
5. Display off, same question: the answer still arrives by voice.
6. Thirty seconds on privacy: one frame, on request, not stored.

Rehearse steps 2 to 4 on the real hardware at least five times. Keep a recorded run as the fallback for the 2-minute video.

## 9. Risks

| Risk | What we do |
|---|---|
| Meta's known issue for Ray-Ban Display: "Do not combine capture with display capabilities". Updates are held back while a capture transfers. | B1 tests it first. Plan A: capture, stop the stream, then send the display. Plan B: answer by audio on the glasses and show the card on the phone. Audio-first is scored on equal footing, so plan B is still a valid entry. |
| A book page is not readable at 720×1280 after Bluetooth compression. | B1 saves real frames; C1 measures reading accuracy on them. Try a lower frame rate, then beta `capturePhoto()`. |
| Image generation needs pay-as-you-go billing on the Gemini key. | C3 checks on the first call. Without it, ship text plus audio and ask Google's booth for credits. |
| End-to-end latency is too long to feel like help. | Status on the lens at every stage. Thinking off on Nemotron. Measure each stage in A3 before optimising anything. |
| Bluetooth or the session drops mid-request. | B4: banner, new session on reconnect, last card kept on the phone. |
| The fourth collaborator invite is still pending. | Lead re-sends it. Stream D cannot push until it is accepted. |

## 10. Open questions

Owned by B1 unless noted. Answers go on the board and into this section.

1. Can camera capture and the display be used in one flow on Ray-Ban Display, in sequence if not together?
2. Does a frame taken from the stream carry enough detail to read a page, or do we need `capturePhoto()`?
3. Which DAT release channel does the loaner unit need? In-stream audio and photo capture are beta features.
4. What does voice invocation need in the Developer Center, and which app name is allowed? Meta's docs say to avoid "AI" in the name. The spoken app name may have to differ from "MetaLab".
5. Does the HFP microphone work while a display session is active?
6. Does the Gemini key have billing enabled for image models? (C3)
7. Which Shakespeare plays do we preload, and from which public-domain source? (C4)

Hardware B1 needs before it can start: a Mac with Xcode, an iPhone paired to the Ray-Ban Display unit, the Meta AI app at the version the DAT docs list, Developer Mode on, and DAT set up as in Meta's getting-started guide. The DAT mentors at the Meta booth are Amanda Le and Dennis Punjabi.

## 11. Non-goals

- Custom camera hardware or a third-party AR display. The glasses are the only device.
- Continuous video streaming or always-on listening.
- A web app on the glasses.
- An Android client.
- User accounts, a database, or anything that outlives the demo session.
- More than one proven scenario. Everything else is a slide.
