# MetaLab: submission text (draft)

Draft for the hackathon submission (#200, LANE-A3). Submitting stays with the lead (#145). Tags like **[E1]** point to `docs/pitch/SOURCES.md`; anything marked *planned* is not done.

## One line

MetaLab turns Ray-Ban Display glasses into a reading companion: look at a page, say "draw this", and Gemini draws that exact passage on the lens, with two lines on what it means.

## Short description (~60 words)

Cluely showed that people want AI that sees what they see. MetaLab brings that to the page. A student stuck on a line of Hamlet asks out loud; the glasses take one photo; Gemini works out what the passage means, using the whole reading session, and draws it for the lens. One photo, only on request, not stored by default.

## Long description (~200 words)

You're reading Hamlet and hit a line you can't picture. Today you put the book down, search on your phone, and lose your place. MetaLab keeps you on the page.

You look at the page and say "draw this". The glasses take one photo. NVIDIA Nemotron reads the text **[E4]**, and Gemini reasons over the passage and everything you asked earlier in the session, so follow-ups build on each other **[E6]**. Then Gemini's image model paints the scene for the lens. The Ray-Ban Display adds light, so black is see-through, and we ask for a bright scene on pure black that floats over the page **[E5]**. On our live server, one request with a real Hamlet page came back in 25.0 s, and 94% of that time was Gemini thinking and drawing **[E1]**. A later run came back in 22.4 s with the server already warm (44.2 s from a cold start), and the illustration downloaded over HTTPS **[E17]**.

MetaLab takes the idea behind Cluely and turns its biggest choice around. Cluely is built to go unnoticed. MetaLab is built to be obvious: one photo, only when you ask, processed in memory and not saved by default. The backend never writes to disk, and a test proves it, including one that plants a leaky stage on purpose **[E9]**. The iPhone app has an off-by-default "Keep a sample frame" setting for collecting test pages; when someone turns it on, photos are saved on the phone.

## How we built it

- **Glasses to phone:** the iPhone app captures one frame and one voice clip on request through Meta's Wearables toolkit, and draws the card on the lens **[E16]**.
- **Backend:** FastAPI on Modal with a public `wss://` endpoint **[E11]**. Every message is checked against one shared contract; 17 contract tests passed against the live server **[E2]**.
- **Reading:** NVIDIA Nemotron 3.5 Super VL reads the page (the live card names it **[E1]**). If it misses an 8-second budget, Gemini reads the same photo, and the card names whichever model actually read it **[E4]**.
- **Reasoning:** Gemini, with the book session's history. An offline test checks that the tenth answer can use the first nine **[E6]**. The live card reported `gemini-4-hydrogen` **[E1]**; the code default is `gemini-4-argon` **[E8]**.
- **Drawing:** Gemini `gemini-nano-banana-2.1`, prompted for an additive lens **[E5, E1]**.
- **Speaking:** Gemini TTS is wired in **[E7]**; the phone's own voice reads the answer when no audio comes back, as on the live card **[E1]**.
- **Deadlines:** 25 s per stage and 85 s per request, inside the phone's limits, so a slow model gives a clear "try again", never a hang **[E10]**.
- **How we worked:** four people let AI agents write, review and fix most of the code. Each change names its requirement and a human owner, and GitHub holds merges in any area where a defect slipped through **[E15]**.

## Models and tools

| Role | Model or tool | Evidence |
|---|---|---|
| Reasoning | Gemini (`gemini-4-hydrogen` on the live card; `gemini-4-argon` code default) | E1, E8 |
| Lens illustration | Gemini `gemini-nano-banana-2.1` | E1, E5 |
| Spoken answer | Gemini TTS `gemini-3.8-flash-tts`, phone voice as fallback | E7 |
| Page reading | NVIDIA Nemotron 3.5 Super VL, with Gemini as the fallback reader | E1, E4 |
| Hosting | Modal | E11 |
| Speech to text | Whisper on Modal: transcribed a synthesized voice clip live; a human voice is not tested yet | E17 |
| Glasses | Meta Ray-Ban Display, via the Meta Wearables toolkit | E3 (hardware rehearsal pending) |

## Challenges we ran into

- **A slow shared model endpoint.** The hosted Nemotron endpoint could queue for minutes, so we gave it a budget and let Gemini take over **[E4]**.
- **Drawing for glass, not a screen.** On an additive lens a normal image washes out, so the prompt asks for pure black backgrounds **[E5]**.
- **Speed.** 25 s is long. Most of it is generation **[E1]**, so the lens shows each stage while it works.
- **Trusting agent-written code.** We measured it and made GitHub enforce it **[E15]**.

## What's next (*planned*)

- Gemini voice feedback and a decision model that routes each request **[E13]**.
- Answers that cite act, scene and line from the play's text **[E14]**.
- A full hardware run on the glasses and a redeploy of the latest backend **[E3, E12]**.

## Tracks

- **Main:** Meta, the Ray-Ban Display reading companion.
- **Google DeepMind, Best Use of Gemini API:** Gemini reasons, draws for the lens, backs up page reading, and speaks (*speech not yet heard live*).
- **Also relevant:** Modal (hosting), NVIDIA Nemotron (page reading), and Tieto (Earned Trust in AI Code), with its own submission in `docs/pitch/tieto-submission.md` **[E15]**.
