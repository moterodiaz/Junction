# Open questions 1–5

PRD section 10. These stay unanswered until a paired Ray-Ban Display is in the room. Do not copy a guess into the PRD. The client is already shaped so each answer has a place to land. Answers, once we have them, go in a small follow-up PR.

1. **Capture and display in one flow.** The client stops the camera before `Display.send`. That is plan A. Plan B is the "Show the lens" switch: off, the answer is spoken and the card stays on the phone.
2. **Stream frame versus `capturePhoto()`.** Default is one stream frame at 720×1280 and 2 fps, then the stream stops. "High-quality photo fallback" uses standalone photo capture. It stays off until a real page says the stream frame cannot be read.
3. **DAT release channel.** Not chosen here. Info.plist is ready for a Developer Center app id; Developer Mode works with an empty `MetaAppID`.
4. **Spoken app name.** The binary is MetaLab. The Developer Center name is separate, and it should not contain "AI".
5. **Microphone while a display session is up.** The HFP route is settled before the camera starts. Speech happens after the camera has stopped and the card is up. Whether HFP still works then is the hardware test.
