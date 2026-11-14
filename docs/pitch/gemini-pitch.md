# MetaLab: Gemini pitch, slide by slide (draft)

Draft for Google DeepMind's "Best Use of Gemini API" track (#200, LANE-A3). Submitting stays with the lead (#145). Tags like **[E1]** point to `docs/pitch/SOURCES.md`; anything marked *planned* is not done.

The angle: Cluely showed that people want an AI that sees what they see and helps the moment they're stuck. MetaLab takes that idea off the screen and puts it on the page. The words stay plain, there is one idea per slide, and every number is one we measured.

---

## 1. Cover

**On the slide:** "Cluely sees your screen. MetaLab sees your page." Under it: "Glasses that look at the book you're reading, and draw the passage you can't picture." Team: Ahmed, Mateo, Maksym, Marcus.

**Say:** Cluely is the desktop AI that sees your screen and helps in real time. We pointed the same idea at a book.

## 2. The problem

**On the slide:** "You're reading Hamlet. You hit a line you can't picture."

**Say:** You put the book down, unlock your phone, type the line in, open three tabs, and lose your place. Or you skip it. No numbers here: we have none, so we tell one student's story.

## 3. The idea, next to Cluely

**On the slide:** a four-row comparison.

| | Cluely | MetaLab |
|---|---|---|
| Sees | your screen | the page in your hands |
| Listens for | the conversation | "draw this" |
| Answers with | text in an overlay | a picture on the lens, plus two lines on what it means |
| Watches | the whole time it runs | one photo, only when you ask |

**Say:** It's the same instinct, help exactly where your attention already is. The last row is where we differ on purpose (slide 7).

## 4. Look. Ask. See.

**On the slide:** four steps, each with the time it took on the live server **[E1]**.

1. **You:** look at the page and say "draw this". The glasses take one photo.
2. **Read:** Nemotron reads the page, in 0.3 s **[E1, E4]**.
3. **Think:** Gemini works out what the passage means, using what you asked earlier, in 10.1 s **[E1, E6]**.
4. **Draw:** Gemini paints the scene for the lens, with a two-line explanation, in 13.5 s **[E1, E5]**.

The card lands 25.0 s after you ask **[E1]**, and the lens shows what it is doing at each step.

**Say, honestly:** that was one typed request with a real photo of a Hamlet page, on a deploy that predates our latest fixes **[E1, E3]**. A full run on the glasses is still to be rehearsed **[E3]**.

## 5. Why Gemini is the product, not a plugin

**On the slide:** four cards.

- **Thinks about this passage, not passages in general.** Gemini reasons over the page and the whole book session, so a follow-up builds on what came before. The tenth answer can use the first nine **[E6]**.
- **Draws pictures made for glass.** The lens adds light, so black is see-through. We ask Gemini's image model (`gemini-nano-banana-2.1`) for a bright scene on pure black, so it floats over the page **[E5, E1]**.
- **Reads when Nemotron is slow.** If the page reader misses its 8-second budget, Gemini reads the same photo, and the card names whichever model actually read it **[E4]**.
- ***Planned:* speaks the answer.** Gemini TTS is wired in **[E7]**, but the live card had no audio, so the phone's own voice reads it for now **[E1, E7]**. Gemini voice feedback and a decision model that routes requests are Marcus's open lane, *planned* **[E13]**.

**Models, from the live card:** reasoning `gemini-4-hydrogen`, image `gemini-nano-banana-2.1` **[E1]**. The code's reasoning default is `gemini-4-argon`, and the deploy overrides it **[E8]**. Say which one the demo build uses on the day.

## 6. The numbers

**On the slide:** "25 seconds from question to picture. 94% of it is Gemini." **[E1, derived in SOURCES.md]**

- A bar showing reading 0.3 s, thinking 10.1 s, drawing 13.5 s, and 1.1 s for everything else **[E1]**.
- 17 contract tests passed against the live server **[E2]**.
- 1 photo per question, not stored by default (the backend never writes it to disk) **[E9]**.
- 8 s before Gemini takes over reading **[E4]**.

**Say:** this is a single measurement, not an average. Every stage has a 25 s limit inside the phone's 30 s, so the user sees an error they can retry, never a silent hang **[E10]**.

## 7. Privacy, the other way round

**On the slide:** "Cluely is built so nobody can tell it's there. MetaLab is built so you always can."

- **One photo, only when you ask.** Nothing runs in the background.
- **Used, then gone.** The photo and voice are processed in memory, and the backend writes nothing to disk **[E9]**. The phone app saves a photo only if someone turns on the off-by-default "Keep a sample frame" setting.
- **Tested, not promised.** A test plants a stage that leaks on purpose, and the checks catch it **[E9]**.

## 8. Built on

**On the slide:** a simple architecture strip: Ray-Ban Display → iPhone app → FastAPI on Modal (public `wss://`) **[E11]** → Nemotron reads **[E4]**, Gemini thinks and draws **[E5, E6]** → card back to the lens.

**Say:** one shared message contract, validated on every reply **[E2]**.

## 9. Limits, said out loud

- Spoken questions with real speech have not been run on the live server yet **[E3]**.
- Gemini speech returned no audio on the live card **[E1, E7]**.
- Citing act, scene and line from the play's text is *planned* (#129) **[E14]**.
- The strict live success checks are not validated yet **[E12]**.

## 10. Close

**On the slide:** "Look at the page. Ask. See it."

**Say:** MetaLab, on Gemini. Then, if time allows: the same four people let AI agents write most of this code and still put their names on it **[E15]**.

---

### Before this goes on a screen

- Re-run one live request on the current deploy and replace E1's figures if they change.
- Decide whether the demo shows Gemini speech or the phone voice. Don't claim Gemini speech unless it plays **[E7]**.
- Keep "*planned*" on anything from #185 or #129 until those PRs merge.
