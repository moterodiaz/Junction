# Plan 010: What serves the demo is a reviewed commit deployed by CI, stamped with its SHA, and smoke-tested over the real socket

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- backend/app/modal_app.py backend/app/main.py backend/README.md .github/workflows/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2 (P1 if the Tieto walkthrough wants an unbroken requirement → PR → CI → running-system chain)
- **Effort**: M (3–4 hours plus two human actions: Modal token secrets, a GitHub Environment)
- **Risk**: MED — an automatic deploy can ship a broken `main`; mitigated by a GitHub Environment with a required reviewer (the lead) and a post-deploy smoke test
- **Depends on**: plans/007 (pinned actions, `permissions`, lint gate) merged first; Modal account access (`@Marcus228` holds it per the board)
- **Category**: dx / tests
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

Today deployment is `modal deploy backend/app/modal_app.py` from a laptop
(`backend/README.md:24`). `modal_app.py:30-31` uploads the deployer's **working
tree** (`add_local_dir(BACKEND_DIR, …)`), so uncommitted, unreviewed edits can go
live, and nothing records which commit is serving. `/health` returns only
`{"ok": true}` (`main.py:42-44`). The only end-to-end check against real models,
`contracts/test_remote.py`, is `skipUnless(WS_URL)` and has never run in CI.

For the Tieto judges this is the last link of the evidence chain (requirement →
task → PR with header → CI → **the running system**); for the demo it answers
"are we sure the phone is talking to the code we tested?". Both are one small
workflow and three lines of Python away.

This plan also adds the macOS job that compiles the iOS **app target**, which no
CI job does today (plan 009 explains why that matters).

## Current state

- `backend/app/modal_app.py:25-34` — image build and `app = modal.App("metalab", image=image)`; `:37-54` the `web()` function with `create_app(require_keys=True)` and `stt.warm()`.
- `backend/app/main.py:42-44`:
  ```python
  @app.get("/health")
  async def health() -> dict:
      return {"ok": True}
  ```
- `backend/README.md:11-33` — manual deploy instructions; the URL pattern `https://<workspace>--metalab-web.modal.run`.
- `contracts/test.sh` + `contracts/test_remote.py` — `WS_URL=wss://…/ws ./test.sh` replays the recorded exchanges against a live backend; `WS_TIMEOUT_S` default 300.
- Secrets that exist in the repo today (names only, from `gh secret list`): `BOT_PUSH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `GEMINI_API_TOKEN`, `NVIDIA_NEMOTRON_KEY`. **No Modal token secrets.**
- `ios/MetaLab.xcodeproj` — scheme `MetaLab`; `ios/README.md:22` says Xcode 26; MWDAT is a public Swift package (`project.pbxproj:293-296`). `ios/test.sh` runs only the Core package tests.
- Conventions: workflows use `env: GH_TOKEN: ${{ github.token }}`, board posts via `gh api repos/$REPO/issues/1/comments -f body=…` (see `pr-sweeper.yml:45`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Backend tests | `cd backend && ./test.sh` | `OK` |
| Health with SHA (after deploy) | `curl -fsS https://<url>/health` | `{"ok":true,"sha":"<40-hex>"}` |
| Remote smoke | `WS_URL=wss://<url>/ws WS_TIMEOUT_S=120 contracts/test.sh` | `OK` (remote tests not skipped) |
| iOS app build (Mac) | `xcodebuild -project ios/MetaLab.xcodeproj -scheme MetaLab -destination 'generic/platform=iOS' build CODE_SIGNING_ALLOWED=NO` | `** BUILD SUCCEEDED **` |

## Scope

**In scope**:
- `backend/app/main.py` (`/health` adds `sha`)
- `backend/app/modal_app.py` (bake `GIT_SHA` into the image env)
- `backend/tests/test_ws.py` (`test_health` asserts the `sha` key)
- `.github/workflows/deploy.yml` (create)
- `.github/workflows/ios-app-build.yml` (create; non-required check)
- `backend/README.md` (deploy section: CI is the normal path; laptop is emergency)

**Out of scope**:
- Making `ios-app-build` a required check (needs the lead to confirm macOS minutes and Xcode 26 availability).
- Any change to what the contract harness asserts.
- `ci.yml` (plan 007).

## Git workflow

Follow `AGENTS.md`: task issue (REQ-DEPLOY-01, REQ-PROC-01) → claim → `tools/wt N-deploy-from-ci`
→ two PRs: PR A `backend/**` (auto-merge), PR B `.github/workflows/**` + README (human merge; tag `@moterodiaz`).
Commit style: `feat(backend): /health reports the deployed git sha`, `chore(ci): deploy main to Modal from CI and smoke-test the live /ws; macOS app build job`.

## Steps

### Step 1: Stamp the build

- `backend/app/main.py`: `return {"ok": True, "sha": os.environ.get("GIT_SHA", "dev")}` (add `import os`).
- `backend/app/modal_app.py`: after building `image`, add
  `image = image.env({"GIT_SHA": os.environ.get("GIT_SHA", "dev")})` (import `os`).
  A laptop deploy without `GIT_SHA` reports `dev` — which is the point.
- `backend/tests/test_ws.py::test_health`: assert `resp.json()["ok"] is True` and `"sha" in resp.json()`.

**Verify**: `cd backend && ./test.sh` → `OK`.

### Step 2: Human actions (list them in PR B's body; do not attempt them yourself)

1. Modal account owner: `modal token new` → create repo secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` (`gh secret set …`).
2. Lead: create a GitHub Environment `production` with **required reviewer `@moterodiaz`**; store the deployed URL as a repo variable `MODAL_WEB_URL` (e.g. `https://<workspace>--metalab-web.modal.run`) after the first CI deploy prints it.
3. Confirm the Modal secret `metalab` holds every key `backend/.env.example` marks required (plan 008 adds `METALAB_WS_TOKEN`; the smoke test needs it too — see Step 3).

### Step 3: `.github/workflows/deploy.yml`

```yaml
name: deploy
on:
  push:
    branches: [main]
    paths: [backend/**, .github/workflows/deploy.yml]
  workflow_dispatch:
permissions:
  contents: read
  issues: write
concurrency:
  group: deploy-production
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: production          # requires the lead's approval before the job runs
    env:
      GH_TOKEN: ${{ github.token }}
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
      GIT_SHA: ${{ github.sha }}
    steps:
      - uses: actions/checkout@<sha>        # same pinned SHA as ci.yml
      - uses: actions/setup-python@<sha>
        with: { python-version-file: .python-version }
      - run: python -m pip install -q --disable-pip-version-check "modal>=1.0"
      - name: Deploy
        run: modal deploy backend/app/modal_app.py 2>&1 | tee deploy.log
      - name: Health must report this commit
        env: { URL: ${{ vars.MODAL_WEB_URL }} }
        run: |
          test -n "$URL" || { echo "::error::set repo variable MODAL_WEB_URL"; exit 1; }
          for i in 1 2 3 4 5 6; do
            sha="$(curl -fsS "$URL/health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sha",""))' || true)"
            [ "$sha" = "$GIT_SHA" ] && break; sleep 10
          done
          [ "$sha" = "$GIT_SHA" ] || { echo "::error::live sha=$sha expected=$GIT_SHA"; exit 1; }
      - name: Smoke-test the live socket
        env:
          WS_URL: ${{ vars.MODAL_WEB_URL }}
          WS_TIMEOUT_S: "120"
          METALAB_WS_TOKEN: ${{ secrets.METALAB_WS_TOKEN }}   # only if plan 008 landed; else remove
        run: |
          WS_URL="wss://${WS_URL#https://}/ws${METALAB_WS_TOKEN:+?token=$METALAB_WS_TOKEN}" contracts/test.sh
      - name: Announce
        if: always()
        run: |
          status="${{ job.status }}"
          gh api "repos/${{ github.repository }}/issues/1/comments" \
            -f body="[Junction's deploy] main@${GIT_SHA:0:7} deploy ${status}: ${{ vars.MODAL_WEB_URL }} (run ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }})" >/dev/null
```
Notes for the executor: the `contracts/test.sh` remote mode treats differences
from the recordings as *drift only* and enforces schema and flow (see
`contracts/README.md` "Remote mode"), so a live run with real models passes when
the backend speaks the contract. If plan 008's token is not deployed yet, delete
the `METALAB_WS_TOKEN` lines.

**Verify**: `actionlint .github/workflows/deploy.yml` (if available) → no errors. After the human merge and
the first approved run: `curl -fsS $MODAL_WEB_URL/health` → `{"ok":true,"sha":"<the merged sha>"}`;
the board shows a `[Junction's deploy]` line.

### Step 4: `.github/workflows/ios-app-build.yml` (non-required check)

```yaml
name: ios-app-build
on:
  pull_request: { paths: [ios/**] }
  push: { branches: [main], paths: [ios/**] }
permissions: { contents: read }
jobs:
  build:
    runs-on: macos-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@<sha>
      - run: sudo xcode-select -s /Applications/Xcode_26.app || ls /Applications | grep -i xcode
      - run: xcodebuild -project ios/MetaLab.xcodeproj -scheme MetaLab -destination 'generic/platform=iOS' build CODE_SIGNING_ALLOWED=NO
      - run: cd ios && swift test --package-path MetaLabCore
```
If `macos-latest` lacks Xcode 26 (check `ls /Applications` in the first run's log),
STOP and report the available versions; the lead decides whether to lower the
deployment target or keep this job manual.

**Verify**: the job is green on a PR touching `ios/`, or the STOP condition is reported with the Xcode list.

### Step 5: README and board

`backend/README.md` "Deploy on Modal": "Normal path: merge to `main`; the `deploy`
workflow deploys after the lead approves the `production` environment and posts the
URL and SHA on the board. `curl $URL/health` shows the deployed commit. Laptop
deploys (`modal deploy …`) are for emergencies and report `sha: dev`." Keep the
one-time setup lines. Open the PRs per "Git workflow".

## Test plan

- `backend/tests/test_ws.py::test_health` extended (sha key present).
- `deploy.yml`: one approved run after merge; the health-SHA step is the test.
- `ios-app-build.yml`: one run on a PR touching `ios/`.

## Done criteria

- [ ] `curl -fsS $MODAL_WEB_URL/health` returns the SHA of `origin/main`
- [ ] `gh run list --workflow deploy.yml --limit 1 --json conclusion --jq '.[0].conclusion'` → `success`
- [ ] The board has a `[Junction's deploy] main@… deploy success` post
- [ ] `ios-app-build` ran at least once (green, or STOP reported with the Xcode list)
- [ ] `backend/README.md` describes CI as the normal deploy path
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The Modal token secrets or the `production` environment do not exist: the
  workflow cannot be tested; open PR B anyway with the human actions listed, and
  mark the plan BLOCKED on them in `plans/README.md`.
- The health SHA never matches after 60 s: Modal may still be building; check
  `modal app list`; if the deploy printed a different URL than `MODAL_WEB_URL`, fix the variable, not the code.
- The remote smoke fails on **schema/flow** (not drift): the live backend
  violates the contract; do not loosen the harness — report which exchange failed.
- `xcodebuild` fails resolving the MWDAT package on the runner (network/auth): report; do not vendor the SDK.

## Maintenance notes

- Every deploy now appears on the board with its SHA; quote the latest one in
  the Tieto concept card's walkthrough as the end of the evidence chain.
- Reviewer: the `production` environment reviewer is the named human sign-off
  for releases — say so in the concept card.
- Deferred: a nightly `live-smoke` run of `contracts/test.sh` in remote mode
  (same job, `schedule:` trigger) once provider budgets allow.
- Deferred: a Modal `min_containers=1` toggle for demo day (`modal_app.py:42`) — a one-line change the deployer flips; document the cost.
