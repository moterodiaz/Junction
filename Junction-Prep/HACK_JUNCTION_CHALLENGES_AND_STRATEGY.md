@@PART1@@
---

## 2. Official Deadlines, Rules, Judging Criteria & Submission Checklist

Extracted directly from the official Junction 2026 Participant Guide (`https://hackjunction.app/participate/45/guide`).

### Hard Schedule & Deadlines
1. **Friday 13.11 @ 23:59 — Pre-Submission Deadline:**
   - Create your draft project submission on the Junction Platform and select initial challenges.
   - You **can edit your submission and switch/add challenges** up until the final deadline on Sunday at 10:00.
   - **Rule Confirmation:** *"You are also allowed to submit a project to multiple challenges."*
2. **Saturday 14.11 @ 12:00 — Final Submission Form Opens:**
   - All final submission fields become editable on the Junction Platform.
3. **Sunday 15.11 @ 10:00 AM SHARP — FINAL SUBMISSION DEADLINE:**
   - The submission form closes automatically at **10:00:00**. Late submissions are strictly rejected.
   - **CRITICAL:** You must switch your submission toggle from **`DRAFT`** to **`FINAL`** and save before 10:00 AM.
4. **Sunday 15.11 @ 10:30–14:00 — Mandatory Live Peer & Partner Reviewing:**
   - Takes place physically at your assigned numbered table (published Saturday evening).
   - **Disqualification Warning:** Every team must review their assigned peer projects during the peer-review window AND remain at their table when partners/peers visit. If a reviewer presses **"Not Present"** for your table or your team fails to submit its assigned peer reviews, **your team is automatically disqualified from the €10,000 Main Prize**.
5. **Sunday 15.11 @ 14:15–15:10 — Top 5 Finalists Stage Pitching (for €10,000 Main Prize):**
   - Chosen via peer review scores across all tracks.
   - Format: **3 minutes pitch** (microphones are cut at 3:00 sharp) + **3 minutes Q&A** with a panel of 7 judges. Live demos from your own laptop are allowed and encouraged.

### Mandatory Submission Deliverables Checklist
Before Sunday 10:00 AM, verify every box below is complete:
- [ ] **Project Name, Punchline & Detailed Description** (including the mandatory model note for **NVIDIA Nemotron**, template in Section 5 below).
- [ ] **Challenges Selected** on the Junction Platform (Main Challenge(s) + all integrated Tech Challenges).
- [ ] **Technologies Used** tags populated.
- [ ] **Video Pitch (STRICTLY ≤ 2:00 minutes):**
  - Official guide warning: *"The demo video should not be a second longer than 2 minutes, and we will be very strict with this."* Make it **1:50–1:58** to avoid YouTube player rounding to `2:01`.
  - Hosted publicly (YouTube Unlisted/Public or Vimeo — test in an Incognito window!).
- [ ] **Public GitHub Repository Link with MIT License:**
  - Official rule: All submissions must use the **MIT Open Source License** (`LICENSE` already exists in `Junction-Prep/LICENSE` — ensure it is at the root of the submitted GitHub repo `moterodiaz/Junction`).
- [ ] **Live Demo URL** (e.g., your `modal deploy` public backend URL).
- [ ] **Pitch Deck (`PDF` file uploaded to the platform).**
- [ ] **Team Contact Info:** Phone numbers and Discord usernames for `@moterodiaz`, `@Ahm3d-KA`, `@maksymmatviievskyi`, and `@Marcus228`.
- [ ] **External Sponsor Forms (if entering these tracks):**
  - [ ] **Cloudinary:** Fill out `https://cld.media/hackathon-survey`
  - [ ] **Verda Compute Track (if used):** Post a short summary + submission link in Verda's channel on the Junction Discord.
  - [ ] **Arduino (if used):** Publish project on `https://projecthub.arduino.cc/` with tag `Junction Finland 2026`.

### General Junction Evaluation Criteria (Used in Peer Review & €10,000 Main Prize)
1. **Innovation (33%):** Is the concept or prototype new, original, or meaningfully differentiated from existing products?
2. **Impact (33%):** Could the solution have a significant impact on society and help a high ratio of people?
3. **Implementation (33%):** Is the prototype realistic, viable, and technically feasible in a live demonstration?

---

@@PART3A@@

### Free add-on: Tieto — "Earned Trust in AI Code" (`ID: 351`, Agentic AI Track)
- **Prizes:**
  - **1st Place:** **€2,000 Cash**
  - **2nd Place:** **€1,000 Cash**
  - **3rd Place:** **€500 Cash**
- **Why You Have an Unfair Advantage Here:**
  - In `.github/workflows/claude-fix.yml`, `AGENTS.md`, and `tools/board`, you have *already built* a working multi-agent PR review factory with Greptile automated code review, an autonomous fixer (`claude-fix`) capped at 5 commits, explicit human escalation (`needs human: fix loop cap hit` or merge conflicts posted to the pinned GitHub Issue #1 board tagging the named human author), and a hard rule preventing agents from running `gh pr merge` without human accountability.
- **Official Judging Rubric (100%):**
  1. **Clarity (30%):** A clear recommendation with stated principles, explicit trade-offs, and limits.
  2. **Practicality (25%):** The concept works in a real pull-request flow and scales, with a named human owning each decision.
  3. **Measurement (25%):** Shows how trust is measured: reverts and incidents don't rise as review time falls, AI findings are real and accepted, time to merge, share routed to humans.
  4. **Evidence (20%):** Evidence traceable to a requirement ID lets a named human accept a change without a full line-by-line read, including **what the AI found, what it refused to decide, and why**.
- **Mandatory Deliverables Required by Tieto:**
  1. **Concept Card (`docs/TIETO_CONCEPT_CARD.md`):** Recommendation, core principles (balancing risk, hallucination, transparency, confidence, and quality), what the named owner signs off on (*what was checked, what was NOT checked & why, residual risk accepted*), trade-offs, and limits.
  2. **Live Walkthrough on 1 Sample Agent-Written PR with Requirement ID:**
     - Add a self-explaining PR header generated by your workflow on a real PR in `moterodiaz/Junction` (tied to a Requirement ID, e.g., `REQ-WS-01: WebSocket message schema` across `contracts/`, `backend/` and `ios/`).
     - Explicitly display three blocks in the PR comment:
       - **Verified by AI (with traceable evidence/tests)**
       - **Refused by AI / Escalated to Named Human (`@moterodiaz`) & Why** (e.g., security boundary change, contract breaking change, or loop cap hit)
       - **Named Human Accountability Sign-Off Block** + Metrics panel (Review Time Saved, AI Finding Acceptance Rate, Escape/Revert Rate, % Routed to Human).
  3. **Lessons Log (`docs/TIETO_LESSONS_LOG.md`):** Document the real failure modes you already encountered today (e.g., Devin reporting "pass" while reviewing nothing due to credits, infinite bot-fix loops requiring the 5-commit cap, rebase vs. merge conflicts on bot-pushed branches).

---
@@PART3B@@

---

## 6. Complete Reference Catalog of All 38 Junction 2026 Challenges

For completeness, every single Main and Tech challenge on the Junction 2026 platform (`hackjunction.app/participate/45/challenges`) has been cross-checked below. Fit scores were set for the earlier AR idea and are kept only as reference. The Verdict columns are current for MetaLab.

### All 19 Main Challenges

| ID | Sponsor & Title | Track | Prizes | Fit Score | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **298** | **Exa** — *The Internet Butler / Your Personal Assistant* | Agentic AI | **1st:** $2,500 + $5k cred + hoodie + TRMNL<br>**2nd:** $1,500 + $3k cred + macropad<br>**3rd:** $500 + $1k cred | **9.5/10** | **NOT TARGETED.** Dropped in the MetaLab pivot; the base case has no live web search. |
| **351** | **Tieto** — *Earned Trust in AI Code* | Agentic AI | **1st:** €2,000<br>**2nd:** €1,000<br>**3rd:** €500 | **9.5/10** | **FREE ADD-ON.** The existing `.github/workflows/claude-fix.yml` + `tools/board` pipeline. Concept card, walkthrough and lessons log only. |
| **342** | **Meta** — *AI Glasses for Everyone, Everyday* | Hardware | **1st:** Ray-Ban Meta glasses per teammate | **10/10** | **CORE (Main).** MetaLab is built for this: a Device Access Toolkit iOS app on a borrowed Ray-Ban Display. |
| **335** | **Stoa** — *Make Blueprints Talk* | AI Infra | **1st:** €1,000 + Work Trial<br>**2nd:** €750<br>**3rd:** €250 | **8.0/10** | **STRETCH (L3).** Blueprint mode, only if L2 ships. |
| **356** | **Arduino** — *The Green European Renaissance* | Hardware | **1st:** Ventuno Q/member<br>**2nd:** UNO Q 4G + Kit<br>**3rd:** Plug & Make Kit | **4.0/10** | **SKIP.** No Arduino hardware in MetaLab. |
| **343** | **Aalto University** — *Beyond the Clinic* | Healthcare | To be announced | **3.5/10** | **SKIP.** Uncertain prize pool ("TBA") and requires depression TMS home-maintenance framing. |
| **350** | **Cala** — *Make Unicorns Real* | Agentic AI | **1st:** €5,000 Hackathon Travel Package + €1k cred<br>**2nd:** €500 cred | **3.0/10** | **SKIP.** Requires founder/investor startup intelligence product built around Cala (`MAKEUNICORNSREAL`). |
| **334** | **Context.dev** — *Build a Live Database of Anything* | Data | **1st:** €2,000<br>**2nd:** €500 | **3.0/10** | **SKIP.** |
| **338** | **MariaDB** — *Unlock Wikipedia's Untapped Potential* | Data | **1st:** €1,000 + €1k UpCloud<br>**2nd:** €500<br>**3rd:** €250 | **3.0/10** | **SKIP.** Specifically requires Finnish Wikipedia history datasets + MariaDB Vector or System-Versioned Tables. |
| **357** | **Hostinger** — *Decode the Noise* | Agentic AI | **1st:** €2,000<br>**2nd:** €1,000<br>**3rd:** €500 | **2.0/10** | **SKIP.** Requires propaganda/bot-network/traffic-log detector deployed on Hostinger VPS. |
| **346** | **Valio Aimo** — *Trusted Trade Agents* | Agentic AI | **1st:** €4,000<br>**2nd:** €2,000<br>**3rd:** €1,000 | **1.5/10** | **SKIP.** Requires B2B foodservice wholesale purchasing agent interface. |
| **348** | **AfterQuery** — *Break the Agent* | Agentic AI | **1st:** €3,000 + Work Trial<br>**2nd:** €1,500<br>**3rd:** €500 | **1.5/10** | **SKIP.** Requires building a custom RL environment + reproducible evaluation harness that breaks frontier agents. |
| **349** | **Bahn Express** — *Spread* | Agentic AI | **1st:** €2,000<br>**2nd:** €1,000<br>**3rd:** €500 | **1.0/10** | **SKIP.** Dedicated car-transport dispatch simulation game (`spread-kmu9z6`) with Sunday 08:00 tournament. |
| **341** | **Ignite Next x Intel** — *The Intel Physical AI Challenge* | Hardware | **1st:** €5,000<br>**2nd:** €3,000<br>**3rd:** €2,000 | **1.0/10** | **SKIP.** Requires on-site SO-101 robot arm teleoperation + Duplo brick defect sorting with Anomalib & OpenVINO. |
| **340** | **Rokoko** — *The Robot Teleoperation Challenge* | Hardware | Mocap gloves / suit hardware | **1.0/10** | **SKIP.** Requires Rokoko motion-capture suit/gloves controlling robotic arms/humanoids. |
| **339** | **Aalto University** — *Humanoid Touches the World* | Hardware | **1st:** €2,000 | **1.0/10** | **SKIP.** Requires Unitree G1 humanoid block sorting in NVIDIA Isaac Sim. |
| **344** | **AstraZeneca** — *Equal Care Across Finland* | Healthcare | **1st:** €1,000<br>**2nd:** €750<br>**3rd:** €250 | **1.0/10** | **SKIP.** Requires Finnish national cancer care pathway bottleneck analytics. |
| **337** | **S-Pankki** — *Talk to Your Bank* | Data | **1st:** €2,000 Airbnb<br>**2nd:** €1,000 Airbnb<br>**3rd:** €500 Airbnb | **1.0/10** | **SKIP.** Requires conversational analytics over S-Pankki's synthetic personal banking dataset. |
| **336** | **City of Espoo** — *Match Skills to Work that Matters* | Data | **1st:** €1,500<br>**2nd:** €1,000<br>**3rd:** €500 | **1.0/10** | **SKIP.** Requires public-sector HR/recruitment matching platform. |

---

### All 19 Tech / Side Challenges

| ID | Sponsor & Title | Prizes | Fit Score | Verdict & Special Requirements |
| :--- | :--- | :--- | :--- | :--- |
| **48** | **Google DeepMind** — *Best Use of Gemini API* | **1st:** €4,000 + $1k GCP/member<br>**2nd:** €2,000<br>**3rd:** €1,000 | **10/10** | **CORE.** Gemini reasons over the passage with whole-book context and generates the lens image. Model IDs in section 4. |
| **40** | **Modal** — *Best use of Modal* | **1st:** $2,000 Cash + $3,000 credits | **9.5/10** | **ADD.** FastAPI WebSocket orchestrator and faster-whisper STT on Modal (`modal deploy`). |
| **46** | **NVIDIA** — *Best Use of Nemotron* | **2x Winners:** 1x NVIDIA RTX 5080 GPU | **9.5/10** | **ADD.** `Nemotron 3.5 Super VL` reads the photographed page + include required text explanation in submission. |
| **47** | **Google DeepMind** — *Best Use of Gemma* | **Top 3 Teams:** €1,000 Cash each | **9.0/10** | **NOT TARGETED.** |
| **43** | **Aiven** — *Best Use of Aiven* | **1st:** €1,000<br>**2nd:** €750<br>**3rd:** €500 | **8.5/10** | **NOT TARGETED.** |
| **32** | **Oxylabs** — *Best agentic usecase of Oxylabs Web API* | **1st:** €1,000 Apple Voucher + $500 cred/member | **8.5/10** | **NOT TARGETED.** |
| **44** | **Context.dev** — *Best Use of Context.dev* | **1st:** €750 + swag<br>**2nd:** €250 + swag | **8.5/10** | **NOT TARGETED.** |
| **41** | **Cloudinary** — *Best Use of Cloudinary* | **1st:** $500 Amazon Gift Card / member | **8.5/10** | **NOT TARGETED.** |
| **42** | **CRACI** — *Best use of CRACI* | **1st:** LEGO set/member<br>**2nd:** 24-pack Red Bull/member<br>**Top 5:** 50k build mins | **9.5/10** | **NOT TARGETED.** |
| **50** | **MLH** — *Best Use of ElevenLabs* | Wireless Earbuds / member | **9.0/10** | **STRETCH (L2).** ElevenLabs voice for the spoken answer and follow-up questions. |
| **51** | **MLH** — *Best Use of Entire* | Mini Portable Projector | **9.0/10** | **NOT TARGETED.** |
| **49** | **OpenAI** — *Best Use of Codex* | **1st:** $10k API cred<br>**2nd:** $5k cred<br>**3rd:** $2.5k cred | **9.0/10** | **NOT TARGETED.** |
| **56** | **Verda** — *Verda Compute Track* | **1st:** $10k cloud cred + hoodies<br>**2nd/3rd:** $2.5k cred | **6.0/10** | **SKIP.** Compute is on Modal. |
| **45** | **Arduino** — *Best use of Arduino Uno Q* | UNO Q + Plug & Make Kit / member | **5.0/10** | **SKIP.** No Arduino hardware in MetaLab. |
| **29** | **Atech** — *Atech Real World Challenge* | Pro Atech hardware kit | **4.0/10** | **SKIP.** No custom hardware in MetaLab. |
| **55** | **MLH** — *Best Use of MongoDB Atlas* | M5Stack IoT Kit | **3.0/10** | **SKIP.** |
| **54** | **MLH** — *Best Use of Vultr* | M5Stack mini programmable monitor | **3.0/10** | **SKIP** in favor of Modal ($2,000 cash vs. monitor). |
| **53** | **MLH** — *Best Use of Tiger Data* | Stream Deck Mini | **3.0/10** | **SKIP** unless you already use Timescale/Tiger Data. |
| **52** | **MLH** — *Best Use of Solana* | Unruggable Hardware Wallets | **1.0/10** | **SKIP.** Unrelated. |
