# iOS: delivery evidence (EVID-B1, #131)

Area owner: Maksym (@maksymmatviievskyi), `ios/`. Requirements: REQ-BUILD-01, REQ-DEV-01.

This file records only commands that were actually run, with their revision, platform and outcome. Anything not run is listed under "Not checked". No secrets, page text, transcripts or user content appear here.

## 1. Revision and platform

| Item | Value |
|---|---|
| Tests below | `5d56e4e` (main, 2026-11-15). `ios/` is unchanged between that commit and `53b35ff` |
| Xcode app build | `6b3d353` (PR #205 head, later squashed to `5dbb607`). Not rebuilt on `5d56e4e` |
| Local platform | macOS (darwin 25.5.0), Apple Silicon, Xcode 26.5 (build 17F42) |
| CI platform | GitHub Actions `ubuntu-latest` runs `ios/test.sh`. This note does not claim a CI run on `5d56e4e` |

## 2. Commands run

| When | Command | Revision | Outcome |
|---|---|---|---|
| 2026-11-14 | `xcodebuild -project ios/MetaLab.xcodeproj -scheme MetaLab -destination 'generic/platform=iOS' build CODE_SIGNING_ALLOWED=NO` | `6b3d353` | **BUILD SUCCEEDED**. The app target compiled. Code signing was off. Not installed on a phone and not run on glasses |
| 2026-11-15 | `ios/test.sh` | `5d56e4e` | Python `tests/test_client.py`: 7 tests, OK. Then `swift test --package-path MetaLabCore` |
| 2026-11-15 | `swift test --package-path ios/MetaLabCore` (the second half of `ios/test.sh`) | `5d56e4e` | 27 tests, 0 failures. MetaLabCore only. The MetaLab app target is not part of this package |

## 3. Who wrote and reviewed what (REQ-DEV-01)

Commits that touch `ios/`, from `git log -- ios/` on `53b35ff`:

| Commit | Author | What |
|---|---|---|
| `178f237` (#70) | Maksym Matviievskyi | Thin client: capture, lens card, speech, recovery |
| `5dbb607` (#205) | Mateo Otero-Diaz | Nullable error `request_id`, stale socket replies, contract fixtures |
| `84091fd` (#224) | Mark (Marcus) | Optional status chimes in the app, plus backend speech changes in the same commit |

Codex does not appear as the author of any `ios/` commit. Greptile reviews pull requests in this repo. This note does not recount review-thread counts.

## 4. Not checked

- Hardware round trip (#140): not yet run. No glasses session, no photo of a page, no lens card, no spoken playback on the device.
- The Xcode app target was not rebuilt on `5d56e4e` or `53b35ff`. The succeeded build is `6b3d353` only.
- A signed install on a phone was not run (`CODE_SIGNING_ALLOWED=NO`).
