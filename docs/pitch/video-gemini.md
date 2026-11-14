# MetaLab: Gemini track video, 2:00 (draft)

Script and shot list for Google DeepMind's "Best Use of Gemini API" track (#207, LANE-A5). Recording and submitting stay with the lead (#145). Tags point to `docs/pitch/SOURCES.md`. A shot marked **to record** needs footage that does not exist yet. None of them is described as done.

| Time | On screen | Voice-over | Source |
|---|---|---|---|
| 0:00–0:10 | A student frowning at a page of Hamlet | "You're reading Hamlet. You hit a line you can't picture." | (story) |
| 0:10–0:20 | Title card: "Cluely sees your screen. MetaLab sees your page." | "Cluely showed people want AI that sees what they see. We pointed that at a book." | (framing) |
| 0:20–0:50 | **To record:** the student wears the glasses and says "draw this". The lens view, mirrored to the phone, shows "reading", "thinking", "drawing", then the card. **Fallback if the glasses run isn't ready:** a screen recording of one live typed request with the same page | "One photo, only when you ask. Gemini works out what this passage means and paints it for the lens." | E1, E16, E17 |
| 0:50–1:05 | **To record:** a close-up of the generated illustration over the page | "The lens adds light, so black is see-through. Gemini draws bright on pure black, so the picture sits over the page." | E5 |
| 1:05–1:20 | **To record:** a follow-up question, and the answer that builds on the first | "It remembers the session, so follow-ups build on each other." | E6 (offline test; live follow-up not recorded yet) |
| 1:20–1:35 | Graphic: a timing bar (read 0.3 s, think 10.1 s, draw 13.5 s) | "On our live server: about 25 seconds, and 94% of it is Gemini thinking and drawing." | E1, E17 |
| 1:35–1:50 | Privacy card: "one photo, only when you ask; the server never stores it" | "Cluely is built so nobody can tell. MetaLab is built so you always can." | E9 |
| 1:50–2:00 | Logo and team | "MetaLab. Look at the page. Ask. See it." | — |

## Rules for the edit

- **Don't show or say that Gemini speaks the answer** unless it plays in the footage: `audio_url` was still null on every live card so far **[E7, E17]**. Today the phone's own voice reads it.
- **Don't show act, scene and line citations as working:** the live run got the scene wrong and cited generic sources. That is *planned* work in #129 and #194 **[E14, E17]**.
- **Gemini voice feedback and the decision model** (#185, merged as #206, off by default) are not deployed: leave them out, or mark them *planned* **[E13]**.
- **Use the timing you actually film.** One recorded request took 25.0 s; a later one took 22.4 s warm and 44.2 s cold **[E1, E17]**.
- **Models to name on screen:** Gemini for reasoning (`gemini-4-hydrogen` on the live card) and for the lens image (`gemini-nano-banana-2.1`) **[E1]**.
