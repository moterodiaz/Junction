# Build evidence: inputs for a dedicated CRACI build (BUILD-D1, #136)

Requirement: REQ-BUILD-01. PRD §12.10. Owner: Mateo (@moterodiaz, lead).

**Status: not validated.** No CRACI build has run. This file records what a dedicated CRACI build would have to cover: dependencies, images, test commands and runner needs, read from the repo at `315d2d3` (2026-11-14). It also records the required `ci` it would be compared against, and what blocks the run. Required `ci` stays as it is (`.github/workflows/ci.yml`, unchanged). A `craci-evaluation.yml` workflow would be a separate, lead-merged, protected-path change. It is not part of this file.

## 1. What CRACI is, and what we could not confirm

CRACI (Helsinki) makes a supply-chain compliance platform for the EU Cyber Resilience Act. It plugs into CI/CD, tracks components and vulnerabilities, and generates compliance documents (public sources: craci.com, news coverage). The challenge page (`hackjunction.app/participate/45/tech-challenges/42`) needs a sign-in, and CRACI publishes no public integration docs (`craci.com/docs` returns 404). So the following are **unknown**: the runner CRACI provides or needs, how it authenticates, its input format (SBOM, lockfile or repo scan), and whether it supports Swift/Xcode.

## 2. Build inputs, by area

| Area | Dependencies (as declared) | Pinning | Build or image | Test entry point |
|---|---|---|---|---|
| Backend (`backend/`) | fastapi>=0.115, uvicorn[standard]>=0.30, pydantic>=2.7, httpx>=0.27, google-genai>=3.2.0, jsonschema==4.23.0 | **Ranges** except jsonschema; no lockfile | Modal image: `debian_slim(python_version="3.12")`, `pip_install_from_requirements` for both files below, `add_local_dir(backend)` (`backend/app/modal_app.py`) | `backend/test.sh` (venv, pip install, `unittest discover`, 300 s deadline) |
| Speech engine (`backend/stt/`) | faster-whisper==1.2.1, av<16 | Exact / upper bound | Modal image only; never installed in CI | Stubbed in `backend/test.sh` |
| Contracts (`contracts/`) | jsonschema==4.23.0, websockets==17.4, plus backend's file | Exact for its own | none | `contracts/test.sh` (schema, fixtures, replay over `/ws`; live tests need `WS_URL`) |
| iOS core (`ios/MetaLabCore`) | none (Swift tools 6.0, iOS 17 / macOS 14) | n/a | `swift build` | `ios/test.sh`: Python proxy tests, then `swift test` if a toolchain exists |
| iOS app (`ios/MetaLab.xcodeproj`) | `meta-wearables-dat-ios` exactly 1.0.1, revision `0bd3692` (`Package.resolved`) | Exact | Xcode, Swift 6.0, iOS 17.2 target, signing | `xcodebuild … CODE_SIGNING_ALLOWED=NO build` (manual only) |

Gaps a supply-chain tool would flag, recorded rather than fixed here:
- Backend dependencies are version ranges with no lockfile, so the deployed image's versions are whatever pip picked on deploy day. `backend/app/DELIVERY_EVIDENCE.md` lists one resolved set (fastapi 0.162.7, pydantic 2.14.3, uvicorn 0.54.0, httpx 0.28.1, google-genai 3.3.0) at `03c24bd`.
- No SBOM is generated anywhere in the repo.
- The Modal base image (`debian_slim`) is pulled by tag, not digest.

## 3. Required `ci` today (the comparison baseline)

`ci` run 43649231648 on `53b35ff`, `ubuntu-latest`: success. Every step passed: shell syntax; guard hook tests; queue and pause policy tests; areas have tests; area tests (iOS proxy 7, MetaLabCore 27 with 0 failures, backend 408); trust gate tests.

| Coverage | Required `ci` | Dedicated CRACI build |
|---|---|---|
| Backend unit tests (stubbed models) | yes | unknown |
| Contract schema and replay | yes | unknown |
| `MetaLabCore` Swift tests | yes (Swift on `ubuntu-latest`) | unknown |
| iOS app target with DAT SDK | **no** (needs macOS + Xcode) | unknown; a blocker if not supported |
| Speech engine install (`faster-whisper`, `av`) | no | unknown |
| Dependency / vulnerability inventory | no | the point of CRACI |

## 4. Blockers before a CRACI run

1. **Access:** a CRACI account or token for this repo, and its integration docs. External, through the sponsor; nothing is sent from here.
2. **Runner:** whether CRACI runs on GitHub-hosted `ubuntu-latest` or needs its own runner, and whether it supports macOS/Xcode for the app target. A missing Swift/Xcode runtime is a blocker, not a waived check.
3. **Workflow:** `.github/workflows/craci-evaluation.yml` is a protected path, so the lead writes and merges it, and it runs alongside `ci`, never instead of it.

Each of these needs a person and credentials. None can be done by an agent.

## Reproduce

```
cat backend/requirements.txt backend/stt/requirements.txt contracts/requirements.txt
grep -n Image -A8 backend/app/modal_app.py
cat ios/MetaLab.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved
gh run view 43649231648 --json jobs
```
