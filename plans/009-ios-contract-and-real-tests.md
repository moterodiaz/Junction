# Plan 009: The phone decodes every valid contract message, never silently drops a reply, and its CI tests exercise the Swift code against the shared fixtures

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- ios/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1 for the demo (a rejected invoke currently looks like a 30 s backend timeout); P2 for the tracks
- **Effort**: M (half a day; Steps 1–4 need only `swift` on Linux or a Mac; Step 5 needs Xcode)
- **Risk**: MED — touches the decode path every reply goes through; covered by new fixture-driven tests
- **Depends on**: none. Owner: `@maksymmatviievskyi` (`ios/`), per `AGENTS.md` §4 — hand this plan over or ask for a handoff on the board.
- **Category**: bug / tests
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

The iOS client is the only thing a judge sees. Three deterministic defects, all
confirmed by reading the code at `6491a8f`:

1. **The Swift error decoder rejects a valid message.** `contracts/ws-messages.schema.json`
   allows `error.request_id` to be `null` (documented in `contracts/README.md:32`,
   fixture `contracts/fixtures/valid/error-null-request-id.json`), and the backend
   sends exactly that for any message it could not parse (`backend/app/main.py:123-125`).
   `ios/MetaLabCore/Sources/MetaLabCore/Contract.swift:307` does
   `requestId = try container.decode(String.self, forKey: .requestId)`, which throws
   on `null`.
2. **Decode failures are silently dropped.** `ios/MetaLab/AppModel.swift:222`
   `guard let event = try? Contract.decode(data) else { return }` — the idle clock
   is not reset and nothing is shown, so a rejected invoke ("Invalid request.", not
   retryable) surfaces 30 s later as a *retryable* "The backend took too long".
   Any future stage or nested-field drift takes the same path.
3. **A typed test command is never cleared.** `AppModel.swift:18` `typedCommand`
   is only ever written by the text field (`RootView.swift:164`) and read by every
   invocation (`AppModel.swift:106-108`), including voice-triggered ones. After one
   desk test, every later "Hey Meta" invocation skips the microphone and re-sends
   the old typed question about the new page, with nothing on screen saying so.

And the verification gap that let (1) through: `ios/test.sh` runs
`ios/tests/test_client.py`, a Python *re-implementation* of the Swift logic
(it never opens a `.swift` file or a fixture; several assertions are
tautologies), and the `MetaLabCore` XCTest suite (which CI *does* compile and
run on ubuntu — confirmed in the ci log) decodes inline JSON strings, not the
shared fixtures (`grep -c fixtures ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift` → `0`).
The app target (`ios/MetaLab/*.swift`, ~1.3k lines: DAT, audio, socket) is never
compiled in CI at all.

A fourth, cosmetic but judge-visible mismatch: the backend sends
`models.image: "stub"` whenever no image was drawn (`backend/app/pipeline.py:219-223`),
and the phone prints it as if it were a model id (`RootView.swift:259-260` only
treats `""` as "pending").

## Current state

- `ios/MetaLabCore/Sources/MetaLabCore/Contract.swift:300-312` (ServerError decoder):
  ```swift
  public init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      type = try container.decodeIfPresent(String.self, forKey: .type) ?? "error"
      requestId = try container.decode(String.self, forKey: .requestId)
      let raw = try container.decode(String.self, forKey: .code)
      ...
  ```
- `ios/MetaLab/AppModel.swift:220-232`:
  ```swift
  private func receive(_ text: String) {
      guard phase == .waiting || phase == .speaking, let data = text.data(using: .utf8) else { return }
      guard let event = try? Contract.decode(data) else { return }
      switch event {
      case .status(let status):
          guard status.requestId == activeRequest else { return }
          lastServerMessage = Date()
          ...
      case .card(let card):
          guard card.requestId == activeRequest else { return }
  ```
  (the `.error` case follows the same `requestId == activeRequest` guard — read it.)
- `ios/MetaLab/AppModel.swift:18,106-108,170` — `typedCommand` lifecycle (see above).
- `ios/MetaLab/RootView.swift:258-261`:
  ```swift
  let reason = models.reason.isEmpty ? "reasoning pending" : models.reason
  let image = models.image.isEmpty ? "image pending" : models.image
  ```
- `ios/test.sh`:
  ```sh
  python3 tests/test_client.py
  if command -v swift >/dev/null 2>&1; then
    swift test --package-path MetaLabCore
  fi
  ```
- `ios/MetaLabCore/Tests/MetaLabCoreTests/MetaLabCoreTests.swift` — 20 XCTest cases; `ContractTests` decode inline JSON (`:53-88`).
- `contracts/fixtures/valid/*.json` — 14 files: `card.json`, `card-no-image.json`,
  `card-with-audio-url.json`, `error-*.json` (5, incl. `error-null-request-id.json`),
  `invoke.json`, `invoke-text-mode.json`, `status-*.json` (4). `contracts/fixtures/invalid/` — 14 files.
- Swift package tests can locate the repo via `#filePath`: the fixtures directory is
  `URL(fileURLWithPath: #filePath).deletingLastPathComponent()` × 4 → repo root, then `contracts/fixtures/valid`.
- Conventions: Swift 6 (`project.pbxproj: SWIFT_VERSION = 6.0`), `@MainActor` view
  model, XCTest, no logging framework anywhere in `ios/`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Core tests (Linux or Mac) | `cd ios && swift test --package-path MetaLabCore` | `Executed N tests, with 0 failures` |
| Area test script (what CI runs) | `cd ios && ./test.sh` | exit 0 |
| App target build (Mac only) | `xcodebuild -project ios/MetaLab.xcodeproj -scheme MetaLab -destination 'generic/platform=iOS' build CODE_SIGNING_ALLOWED=NO` | `** BUILD SUCCEEDED **` |
| Fixture sanity | `python3 -I -c "import json,glob;[json.load(open(f)) for f in glob.glob('contracts/fixtures/valid/*.json')];print('ok')"` | `ok` |

## Scope

**In scope**:
- `ios/MetaLabCore/Sources/MetaLabCore/Contract.swift` (ServerError `requestId` optional)
- `ios/MetaLab/AppModel.swift` (`receive`, `typedCommand` handling, a minimal logger)
- `ios/MetaLab/RootView.swift` (`"stub"` sentinel; "Typed mode" label)
- `ios/MetaLabCore/Tests/MetaLabCoreTests/` (fixture-driven tests; new test file allowed)
- `ios/test.sh`, `ios/tests/test_client.py` (replace the mirror with a fixture-shape check or delete it — see Step 4)
- `ios/README.md` lines 7 and 26–28 (describe what the tests really cover)

**Out of scope** (hardware-gated; listed for the owner's hardware session in "Maintenance notes"):
- `ios/MetaLab/GlassesBridge.swift` capture/display lifecycle.
- `.github/workflows/ci.yml` (a macOS job is proposed in plan 007).
- `contracts/**`.

## Git workflow

Follow `AGENTS.md`: task issue (REQ-WS-01, REQ-IOS-01; PRD §6 "technical execution", §7) →
claim → `tools/wt N-ios-contract-tests` → PR `Closes #N` → auto-merge → board post.
Commit style (from `git log`): `fix(ios): decode null error ids, surface undecodable replies, clear typed commands`
and `test(ios): decode every contracts/fixtures/valid file in Swift`.

## Steps

### Step 1: Failing fixture-driven tests first

Add `ios/MetaLabCore/Tests/MetaLabCoreTests/FixtureContractTests.swift`:

```swift
import XCTest
@testable import MetaLabCore

final class FixtureContractTests: XCTestCase {
    static let fixtures = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()  // -> repo root (adjust until `contracts` resolves)
        .appendingPathComponent("contracts/fixtures/valid")

    func testEveryValidServerFixtureDecodes() throws {
        let files = try FileManager.default.contentsOfDirectory(at: Self.fixtures, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" && !$0.lastPathComponent.hasPrefix("invoke") }
        XCTAssertGreaterThanOrEqual(files.count, 12)
        for file in files {
            let data = try Data(contentsOf: file)
            XCTAssertNoThrow(try Contract.decode(data), "failed to decode \(file.lastPathComponent)")
        }
    }

    func testNullErrorRequestIdDecodes() throws {
        let data = try Data(contentsOf: Self.fixtures.appendingPathComponent("error-null-request-id.json"))
        guard case .error(let err) = try Contract.decode(data) else { return XCTFail("not an error") }
        XCTAssertNil(err.requestId)
        XCTAssertFalse(err.retryable)
    }
}
```
Adjust the number of `deletingLastPathComponent()` calls until the directory exists
(print `Self.fixtures.path` once if unsure).

**Verify**: `cd ios && swift test --package-path MetaLabCore 2>&1 | tail -5` → the new tests **fail** on `error-null-request-id.json` only.

### Step 2: Decode `request_id: null` (`Contract.swift`)

Change `ServerError.requestId` to `String?` and line 307 to
`requestId = try container.decodeIfPresent(String.self, forKey: .requestId)`.
Fix the compile errors that follow (places that compare `error.requestId == activeRequest`).

**Verify**: `swift test --package-path MetaLabCore` → all pass, including the two new tests.

### Step 3: Never drop a reply silently (`AppModel.swift`)

In `receive(_:)`:
- Replace `guard let event = try? Contract.decode(data) else { return }` with a
  `do/catch` that, on failure, sets `lastServerMessage = Date()`, logs
  `Logger(subsystem: "metalab", category: "contract").error("undecodable reply: \(error.localizedDescription)")`
  (import `os`; never log the payload), and fails the request with the existing
  failure path used for `internal` errors (message "Unexpected reply from the backend.", not retryable).
- In the `.error` case: accept the message when `error.requestId == activeRequest`
  **or** `error.requestId == nil` (the backend only sends null when it could not
  parse the request; there is one in-flight request per socket).
- `typedCommand`: after a successful `send(frame:wav:text:)` set `typedCommand = ""`.
  In `RootView.swift`, next to the text field, show a small caption `"Typed mode: the microphone is skipped"` when `!model.typedCommand.isEmpty`.
- `RootView.swift:259-260`: treat `"stub"` like `""` → `"reasoning pending"` / `"image pending"`, or hide the line when both are stubs. Pick the simplest and say which in the PR.

Add Core-level tests where the logic is testable (e.g. a `SessionMachine` signal for
"unexpected reply" if you route it through the reducer); the `AppModel` behaviour
itself is app-target code — document the manual check in the PR.

**Verify**: `swift test --package-path MetaLabCore` → pass. Manual (simulator or
device): send a malformed message from a local backend (`cd backend && .venv/bin/uvicorn app.main:app`,
then type a non-JSON command path is not possible from the UI — instead run the backend with
`STAGE_TIMEOUT_S=0.001` so every request returns an `error`): the phone shows the
error within a second, not a 30 s timeout.

### Step 4: Make `ios/test.sh` honest

- `ios/test.sh`: require the toolchain —
  ```sh
  command -v swift >/dev/null 2>&1 || { echo "::error::swift toolchain required for ios/test.sh"; exit 1; }
  swift test --package-path MetaLabCore
  ```
  (CI's ubuntu runner has `swift`; the ci log for run 43596305049 shows "Build complete!" and the suites.)
- `ios/tests/test_client.py`: either delete it (it tests Python, not the app — say so in
  the PR; AGENTS.md's "never delete a test to pass" does not apply because nothing it
  asserts is about the product) or reduce it to one check: every file in
  `contracts/fixtures/valid` parses as JSON and has a `type` in `{invoke,status,card,error}`.
- `ios/README.md:7`: the wire format is `contracts/ws-messages.schema.json` (not "the PRD draft").
  `ios/README.md:26-28`: "`ios/test.sh` runs the MetaLabCore XCTest suite, which decodes every
  fixture in `contracts/fixtures/valid`; the app target is built and tested in Xcode, not in CI."

**Verify**: `cd ios && ./test.sh` → exit 0 with the XCTest summary; `grep -c "PRD draft" ios/README.md` → `0`.

### Step 5 (Mac with Xcode only): build the app target

`xcodebuild -project ios/MetaLab.xcodeproj -scheme MetaLab -destination 'generic/platform=iOS' build CODE_SIGNING_ALLOWED=NO`
→ `** BUILD SUCCEEDED **`. If no Mac is available to you, STOP after Step 4 and
say so in the PR; the owner builds before merging.

### Step 6: PR and board

Open the PR per "Git workflow". In the body: which fixtures now decode, the manual
check from Step 3, and the hardware checklist below copied verbatim for the owner.

## Test plan

- New Swift tests: every `contracts/fixtures/valid/*.json` server message decodes;
  `error-null-request-id.json` yields `requestId == nil`, `retryable == false`.
- Existing 20 XCTest cases keep passing.
- Manual: forced-error backend → phone shows the error immediately (Step 3).
- `cd ios && ./test.sh` → exit 0.

## Done criteria

- [ ] `grep -n "decodeIfPresent(String.self, forKey: .requestId)" ios/MetaLabCore/Sources/MetaLabCore/Contract.swift` → 1 match in the error decoder
- [ ] `grep -c "try? Contract.decode" ios/MetaLab/AppModel.swift` → `0`
- [ ] `grep -n 'typedCommand = ""' ios/MetaLab/AppModel.swift` → ≥ 1
- [ ] `test -f ios/MetaLabCore/Tests/MetaLabCoreTests/FixtureContractTests.swift`
- [ ] `grep -c "command -v swift" ios/test.sh` → 1 and the script no longer skips Swift silently
- [ ] `cd ios && ./test.sh` exits 0; CI green on the PR
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The fixture directory cannot be resolved from `#filePath` in CI (the checkout
  layout differs): fall back to an environment variable `METALAB_FIXTURES` set in
  `ios/test.sh` (`export METALAB_FIXTURES="$PWD/../contracts/fixtures/valid"`), and report.
- Making `requestId` optional cascades into `SessionMachine` changes beyond three
  call sites: report the list before continuing.
- You are about to change capture/display order in `GlassesBridge.swift`: that is
  hardware-gated (see below) and out of scope here.

## Maintenance notes

**Hardware checklist for the owner (from the iOS audit at `6491a8f`; verify on the glasses before changing):**
1. `GlassesBridge.swift:218-240, 251-255` — the display created by the first `show()` is never released before later captures; PRD §9 risk #1 ("do not combine capture with display") is only honoured on the *first* invocation. Test whether `display.stop()` + `addDisplay()` works twice in one session.
2. `GlassesBridge.swift:186-204` — the `installTap` closure is created in a `@MainActor` context under Swift 6; AVAudioEngine calls it on its I/O thread. One voice invocation on a device settles whether it traps.
3. `GlassesBridge.swift:363-365` + `AppModel.swift:127-129` — a "Hey Meta" invocation is acknowledged with `sendSuccess` and then dropped if `canInvoke` is false or the phase is not idle (cold launch, or while speaking). Consider a 10 s pending invocation.
4. `GlassesBridge.swift:33, 139-141` — DAT listener tokens accumulate per resume/reconnect.
5. `AppModel.swift:313` — glasses capture timeouts are reported as "backend took too long".
6. `Privacy.swift:39,47` — `ws://` is accepted and the placeholder `wss://your-modal-app…` passes validation; allow only `wss` outside DEBUG and treat the placeholder as unset.
7. `Info.plist` — no `audio` background mode; `RootView.swift:181` "Keep a sample frame" is in the release UI and writes JPEGs to Documents (gate behind `#if DEBUG`).

- Reviewer: check that no log line can contain the frame, audio or page text.
- Deferred to plan 007: a `macos-latest` CI job that builds the app target.
