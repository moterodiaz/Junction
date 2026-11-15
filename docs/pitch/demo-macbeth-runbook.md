# Macbeth demo runbook (proof of concept, canned backend)

Goal: film a student wearing the glasses, looking at a page of *Macbeth*, asking "can you explain this?", waiting a few seconds, and getting the dagger illustration and a spoken answer.

## What is real and what is canned

| Stage | In this demo build | Real pipeline (default) |
|---|---|---|
| Wake word, glasses camera, microphone, lens, speaker | **real** | real |
| Listening | **real**; stops shortly after the wearer stops talking (end-of-speech detection in `ios/`) | fixed 4 s window |
| Speech to text, page reading, reasoning, drawing | **skipped**: the backend returns one fixed card (`backend/app/demo.py`) | about 25 s, 44 s cold |
| Status messages on the lens ("Reading", "Thinking", "Drawing") | **real messages**, spread over `DEMO_DELAY_S` seconds (default 2) | sent as each stage starts |
| The card | fixed Macbeth Act 2 Scene 1 card; `models` says `demo-canned` | models that made it |

Say this plainly in the video voice-over or captions ("demo build: answer prepared in advance for this page"). Do not describe the canned answer as live Gemini output. If you also want a "real pipeline" shot, film a separate run with `DEMO_CANNED` off and show its real timing bar.

## The page

Use the dagger soliloquy, Macbeth Act 2 Scene 1. It is the strongest demo page because a floating dagger is bright on black, which is what the additive lens needs, and a student really cannot picture "a dagger of the mind".

> Is this a dagger which I see before me,
> The handle toward my hand? Come, let me clutch thee.
> I have thee not, and yet I see thee still.
> Art thou not, fatal vision, sensible
> To feeling as to sight? or art thou but
> A dagger of the mind, a false creation,
> Proceeding from the heat-oppressed brain?

Print or open a real edition at that page. The canned backend does not read the frame, so any frame works, but the footage must show the dagger lines, because the viewer is judging the match. Other quotes are in `backend/app/demo_assets/macbeth_quotes.json` if you want a second take ("Out, damned spot!" is the next best).

## Before filming

1. **Backend.** From the repo root, logged in to Modal: `DEMO_CANNED=on modal deploy backend/app/modal_app.py`. This also keeps one container warm, so there is no cold start on camera. A plain `modal deploy` afterwards turns the demo path off again.
   Check: `curl -s -o /dev/null -w '%{http_code}\n' https://junction26-vision--metalab-web.us-east.modal.run/demo/macbeth_dagger.png` should print `200`. The Modal secret `metalab` must contain `IMAGE_BASE_URL` (the live cards already had image URLs, so it does); without it the card has no picture.
2. **Picture.** `macbeth_dagger.png` in `backend/app/demo_assets/` is a drawn placeholder. For the real look, run `GEMINI_API_KEY=... python backend/app/demo_assets/make_dagger.py --gemini`, look at the result, then redeploy.
3. **Voice (optional).** With no clip the phone reads the answer in its own voice. To use a better voice, save the spoken answer (text is `SPEECH` in `backend/app/demo.py`) as a WAV named `macbeth_dagger.wav` in `backend/app/demo_assets/` and redeploy; the card then offers it automatically.
4. **Phone.** Pull branch `demo-macbeth-canned`, open `ios/MetaLab.xcodeproj` in Xcode 26, set the team, put `wss://junction26-vision--metalab-web.us-east.modal.run/ws` in the backend field, run on the iPhone paired to the glasses in Developer Mode. Do one dry run before recording.

## The take (about 20 seconds)

| Time | Wearer | Lens / phone |
|---|---|---|
| 0:00 | Looks at the dagger lines. Says "Hey Meta, start MetaLab." | MetaLab opens |
| 0:03 | Says "Can you explain this?" and stops. | "Listening", then status messages |
| about 0:07 | Waits, looking at the page. | "Reading", "Thinking", "Drawing" |
| about 0:10 | | The dagger card, spoken answer starts |

Timings are estimates and not yet measured on the glasses. Time the first dry run and put the real numbers in the video.

## Recording it

Use two cameras plus a screen capture, then cut them together:

1. **Second phone on a tripod, over the wearer's shoulder or from the side**: the wearer's face, the book and their reaction through the whole wait. This is the shot that proves "looking at the book".
2. **Glasses lens view**: if the Meta tools can mirror or record the display, use it. If not, film the lens close up through a dim room, and keep the room light low so the lens is readable.
3. **Phone screen recording** of the MetaLab app (status and card), as the backup for the lens.
4. **Audio**: record the room or a lapel mic; the answer is spoken from the glasses, so a quiet room matters more than a good mic.

Film three or four takes. Wake word and speech are the most likely failures; keep going and pick the best.

## If it goes wrong

- **Listening never stops or cuts you off**: the end-of-speech thresholds are untested on real glasses; speak in a clear sentence and leave a beat of silence. Report the symptom to the iOS owner.
- **No picture on the lens**: the lens only loads https images. Check the `curl` above, and that `IMAGE_BASE_URL` is set. The card still shows text and is spoken.
- **Glasses will not work on the day**: phone-only fallback with the typed command box; the card appears on the phone screen.
