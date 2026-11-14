# Plan 001: The public repo presents MetaLab (not the template) and carries an MIT LICENSE at root

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- README.md LICENSE docs/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S (1–2 hours)
- **Risk**: LOW (documentation and a license file; no code paths change)
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

Every judge, in every track, opens the GitHub repo first. Today the root
`README.md` of `moterodiaz/Junction` is the unmodified README of the
*"Hackathon agent board"* template it was cloned from: it talks about Cal Hacks
and Knight Hacks, links a Notion page, and embeds `docs/banner.jpg`, a file that
does not exist (there is no `docs/` directory). Nothing on the landing page says
"MetaLab", "Ray-Ban", "Gemini" or "Nemotron".

Junction's rules require every submission to be MIT-licensed and the organisers
to be able to read the source. The repo is **public** and GitHub reports
**"license: none"** because the only `LICENSE` file sits in
`Junction-Prep/LICENSE`, where GitHub does not look. The NVIDIA Nemotron track
additionally *requires* a "Models used" note in the submission; putting the same
note in the README makes it verifiable from the code.

This is the cheapest, highest-visibility fix in the whole plan set. It touches
the "Implementation 33%" criterion of the main prize and the mandatory
deliverables of two sponsor tracks.

## Current state

- `README.md` (root) — 59 lines, template content. Line 3:
  `![The hacking floor at Cal Hacks](docs/banner.jpg)` (broken image). Lines
  5–59 describe `tools/board`; this content is still useful and must be kept,
  moved to `docs/AGENT_BOARD.md`.
- `LICENSE` (root) — **does not exist**.
- `Junction-Prep/LICENSE` — exists; begins:
  ```
  MIT License

  Copyright (c) 2026 Mateo Otero-Diaz
  ```
- `docs/` — **does not exist**.
- Product truth lives in `Junction-Prep/metalab_prd.md` (PRD). Section 1 is the
  pitch, section 4 has the architecture diagram and the models table, section 6
  the data-handling statement, section 7 the message contract.
- Model configuration lives in `backend/app/config.py` lines 22–28:
  ```python
  DEFAULTS = {
      "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
      "MODEL_READ": "nvidia/nemotron-3.5-super-vl-120b-a12b",
      "MODEL_REASON": "gemini-4-argon",
      "MODEL_IMAGE": "gemini-nano-banana-2.1",
      "MODEL_TTS": "gemini-3.8-flash-tts",
  }
  ```
  **The deployed values differ from these defaults.** On the team board
  (issue #1, post at 10:16 UTC on 2026-11-14) the backend owner reported that
  the team's NVIDIA key works against a Verda-hosted container,
  `NVIDIA_BASE_URL=https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1`,
  `MODEL_READ=nemotron-3.5-super-vl`, not against `integrate.api.nvidia.com`.
  The README's model note must state what is actually deployed (see STOP
  conditions).
- Thinking is disabled for Nemotron: `backend/ai/page_reader.py:202-204`
  sends `"chat_template_kwargs": {"enable_thinking": False}`.
- Speech to text: faster-whisper `small.en` (`backend/stt/engine.py:16`).
- Test entry points: `backend/test.sh`, `contracts/test.sh`, `ios/test.sh`.
- Deploy instructions already exist in `backend/README.md` (Modal). Link, do not duplicate.

Repo conventions: Markdown files use ATX headings (`#`), sentence-case headings,
and plain prose (see `backend/README.md`, `contracts/README.md`). Match that.

## Commands you will need

| Purpose | Command (from repo root) | Expected on success |
|---|---|---|
| CI shell checks (what ci.yml runs first) | `for f in tools/* .claude/hooks/*.sh; do head -n1 "$f" \| grep -q bash && bash -n "$f"; done` | no output, exit 0 |
| Backend tests | `cd backend && ./test.sh` | `OK` (147 tests at planned SHA) |
| Contracts tests | `cd contracts && ./test.sh` | `OK (skipped=1)` |
| iOS proxy tests | `cd ios && ./test.sh` | `OK` |
| Check license detection locally | `head -1 LICENSE` | `MIT License` |

## Scope

**In scope** (the only files you should create or modify):
- `README.md` (rewrite)
- `LICENSE` (create; byte-identical copy of `Junction-Prep/LICENSE`)
- `docs/AGENT_BOARD.md` (create; the old README content minus the broken banner line)

**Out of scope** (do NOT touch):
- `AGENTS.md`, `KICKOFF.md`, `CLAUDE.md` — team process rules; owned by the lead.
- `Junction-Prep/**` — keep `Junction-Prep/LICENSE` where it is (copy, don't move).
- `backend/README.md`, `contracts/README.md`, `ios/README.md` — link to them.
- Anything under `.github/` (workflow changes need a human merge).

## Git workflow

This repo's standing instruction (`AGENTS.md`, "START HERE") is that every change
goes through a task issue, a worktree, and a PR with auto-merge. Follow it:

1. File a task issue (template fields: Goal / PRD section / Scope / Acceptance
   check / Depends on / Area). Area: `contracts` is wrong for docs; use
   `backend` only if you own it, otherwise ask the lead on the board which area
   label to use for repo-root docs. Example:
   `gh issue create --label task --title "docs: MetaLab README and root MIT LICENSE" --body-file /tmp/body.md`
2. `tools/task claim <N>` then `tools/wt <N>-readme-license` → work in
   `../Junction-wt/<N>-readme-license/`.
3. Commit style (from `git log`): `docs: MetaLab README, root MIT LICENSE, agent board doc moved to docs/`.
4. Before pushing: `git pull --no-rebase`. Then `git push -u origin <N>-readme-license`.
5. `gh pr create --title "docs: MetaLab README and root MIT LICENSE" --body "Closes #<N> ..."`,
   then `gh pr merge <PR> --squash --auto`, then post the link on the board:
   `tools/board post "[<Your name>'s Claude] <PR url>: root README now describes MetaLab; LICENSE at root. @moterodiaz"`.

## Steps

### Step 1: Add the root LICENSE

`cp Junction-Prep/LICENSE LICENSE`

**Verify**: `diff Junction-Prep/LICENSE LICENSE && head -1 LICENSE` → no diff output, then `MIT License`.

### Step 2: Preserve the agent-board documentation

`mkdir -p docs && git mv README.md docs/AGENT_BOARD.md` is NOT possible while
also keeping a new README in the same commit with `git mv`; instead:

1. `mkdir -p docs`
2. `cp README.md docs/AGENT_BOARD.md`
3. In `docs/AGENT_BOARD.md`, delete the line `![The hacking floor at Cal Hacks](docs/banner.jpg)`
   and change the title line to `# Hackathon agent board (team process)`.
4. The template text speaks in the first person about *someone else's* results
   ("My teams ran this at two hackathons", Knight Hacks / Cal Hacks prizes, a
   Notion link). Left as-is in this repo it reads as this team's claim. Add a
   first paragraph: `Adapted from the open-source "hackathon agent board" template (see the upstream repo's README for its history and credits); the sections below describe how this team uses it.`
   and delete or rewrite the "Used at" section so no first-person claim about
   other hackathons remains.

**Verify**: `grep -c "banner.jpg" docs/AGENT_BOARD.md` → `0`; `head -1 docs/AGENT_BOARD.md` → `# Hackathon agent board (team process)`; `grep -c "My teams" docs/AGENT_BOARD.md` → `0`.

### Step 3: Write the MetaLab README

Replace the whole of `README.md` with a document that has exactly these
sections, in this order. Fill every `<...>` from the sources named; do not
leave placeholders in the committed file (see STOP conditions).

```markdown
# MetaLab

<One paragraph, lifted from PRD section 1: a student reading an assigned text asks
out loud; the glasses take one photo; an illustration plus a two-line explanation
appears on the lens and is read aloud.>

**Live demo:** `wss://<workspace>--metalab-web.modal.run/ws` (see "Deploy")
**Video:** <YouTube/Vimeo link, or "coming before submission">
**License:** MIT (see `LICENSE`)

## What it does
<3–5 bullets: one frame + one command per invocation; reads the page; answers
with memory of the book session; draws for the additive lens; speaks the answer;
works with the display off.>

## Architecture
<Copy the ASCII diagram from PRD section 4 verbatim (glasses → iOS app → WebSocket → FastAPI on Modal → stages).>

## Models used
<Mandatory for the NVIDIA Nemotron track. State exactly what is deployed:>
- **Read the page:** NVIDIA Nemotron 3.5 Super VL (`<MODEL_READ as deployed>`) via the
  OpenAI-compatible API at `<NVIDIA_BASE_URL as deployed>`, thinking **disabled**
  (`chat_template_kwargs.enable_thinking=false`, see `backend/ai/page_reader.py`).
  Output is text only and is passed to the reasoning step. Frames are processed in
  memory and never stored.
- **Reason:** Gemini `<MODEL_REASON>` with a per-book session (`backend/ai/reasoning.py`, `backend/ai/session.py`).
- **Draw:** Gemini `<MODEL_IMAGE>` (`backend/ai/image.py`), prompts conditioned for a black background.
- **Speak:** Gemini `<MODEL_TTS>` (`backend/stt/speak.py`); the phone falls back to the system voice.
- **Speech to text:** faster-whisper `small.en` on Modal (`backend/stt/engine.py`).
Every card reports which models actually produced it in its `models` field
(`contracts/ws-messages.schema.json`).

## Tracks
| Track | What we use it for | Where |
|---|---|---|
| Meta – AI glasses | capture, lens display, voice invocation | `ios/` |
| Google DeepMind – Gemini API | reasoning with book memory, illustration, TTS | `backend/ai/`, `backend/stt/speak.py` |
| NVIDIA – Nemotron | reading the photographed page | `backend/ai/page_reader.py` |
| Modal | the FastAPI WebSocket backend and Whisper | `backend/app/modal_app.py` |
| Tieto – Earned trust in AI code | the bounded agent PR pipeline | `docs/TIETO_CONCEPT_CARD.md`, `.github/workflows/` |

## Run and test
<The three test.sh commands and the uvicorn line from backend/README.md.>

## Deploy
See `backend/README.md` (Modal).

## Privacy
<PRD section 6 bullets: one frame and one clip per invocation, only after the
user asks; processed in memory, never written to disk; generated image kept for
the session then deleted; session holds text only.>

## Repository map
<One line each: ios/, backend/app/, backend/stt/, backend/ai/, contracts/, tools/, docs/, Junction-Prep/ (PRD and strategy).>

## Team process
Agents coordinate on a pinned GitHub issue; see `docs/AGENT_BOARD.md` and `AGENTS.md`.
```

Fill the model ids from the deployed Modal secret (ask the backend owner or the
lead on the board; the board post of 10:16 UTC gives the Nemotron values). If
the Tieto docs (`docs/TIETO_CONCEPT_CARD.md`) do not exist yet when you write
this, link to `AGENTS.md` instead and leave a one-line note that the concept card
is in progress under plan 003.

**Verify**: `grep -c "MetaLab" README.md` → ≥ 3; `grep -q "## Models used" README.md && echo ok` → `ok`; `grep -c "<" README.md` → `0` (no unfilled placeholders; the ASCII diagram uses `->` and `|`, not `<`... if the PRD diagram contains `<`, count only lines matching `<[A-Za-z ]*>` instead: `grep -cE "<[A-Za-z /]+>" README.md` → `0`).

### Step 4: Run the CI checks locally and open the PR

Run the four commands in "Commands you will need". Then follow "Git workflow".

**Verify**: `gh pr checks <PR>` → `ci pass`, `Greptile Review pass`; GitHub repo page shows "MIT license" in the sidebar after merge (`gh repo view --json licenseInfo --jq .licenseInfo.name` → `MIT License`).

## Test plan

No code changes; the gate is CI staying green plus the two machine checks in
Done criteria. Do not add tests.

## Done criteria

- [ ] `test -f LICENSE && head -1 LICENSE | grep -q "MIT License"` exits 0
- [ ] `gh repo view moterodiaz/Junction --json licenseInfo --jq .licenseInfo.name` → `MIT License` (after merge)
- [ ] `grep -rn "docs/banner.jpg" README.md docs/` returns no matches
- [ ] `grep -q "## Models used" README.md` and the section names the deployed `NVIDIA_BASE_URL` and model ids (no `<...>` placeholders remain)
- [ ] `docs/AGENT_BOARD.md` exists and contains the `tools/board` command table
- [ ] CI (`ci`, `Greptile Review`) green on the PR; PR merged with `Closes #<N>`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- You cannot find out the deployed `NVIDIA_BASE_URL` / `MODEL_READ` /
  Gemini model ids (ask on the board; if no answer in 15 minutes, commit the
  README with the `backend/app/config.py` defaults **and** a sentence "Deployed
  endpoint: see Modal secret `metalab`" — do not invent values).
- `Junction-Prep/LICENSE` is not an MIT license text (first line differs).
- `README.md` at HEAD is no longer the template (someone already rewrote it):
  merge your sections into theirs instead of overwriting, and report.
- The lead objects on the board to moving the board docs to `docs/`.

## Maintenance notes

- When the Modal URL, video link, or model ids change, update the README's
  "Live demo" and "Models used" lines in the same PR as the change — the NVIDIA
  submission note must match the code.
- Reviewer: check that nothing in the README claims a capability the code
  doesn't have yet (sources, whole-book memory, Nemotron live) — see plans 005
  and 006 for the current gap between pitch and code.
- Deferred: a hero screenshot/GIF of the lens card (needs real hardware); add
  under "What it does" once a recording exists.
