import XCTest
@testable import MetaLabCore

final class ContractTests: XCTestCase {
    func testTypedCommandOmitsAudioAndKeepsNulls() throws {
        let message = try Contract.makeInvoke(
            requestId: "req-1",
            sessionId: "book-1",
            jpegBase64: "abc",
            wavBase64: "should-not-be-sent",
            text: " explain "
        )
        let object = try jsonObject(Contract.encode(message))
        XCTAssertEqual(object["type"] as? String, "invoke")
        XCTAssertEqual(object["request_id"] as? String, "req-1")
        XCTAssertEqual(object["session_id"] as? String, "book-1")
        XCTAssertEqual(object["text"] as? String, "explain")
        XCTAssertTrue(object.keys.contains("audio"))
        XCTAssertNil(object["audio"] as? [String: Any] ?? nil)
        let frame = object["frame"] as? [String: String]
        XCTAssertEqual(frame?["mime"], "image/jpeg")
        XCTAssertEqual(frame?["b64"], "abc")
    }

    func testAudioCommandEncodesWavAndNullText() throws {
        let message = try Contract.makeInvoke(
            requestId: "req-2",
            sessionId: "book-1",
            jpegBase64: "frame",
            wavBase64: "wav",
            text: "  "
        )
        let object = try jsonObject(Contract.encode(message))
        XCTAssertNil(object["text"] as? String)
        let audio = object["audio"] as? [String: String]
        XCTAssertEqual(audio?["mime"], "audio/wav")
        XCTAssertEqual(audio?["b64"], "wav")
    }

    func testInvokeRequiresAFrameAndACommand() {
        XCTAssertThrowsError(try Contract.makeInvoke(
            requestId: "r", sessionId: "s", jpegBase64: "", wavBase64: "a", text: nil
        )) { error in
            XCTAssertEqual(error as? ContractError, .missingFrame)
        }
        XCTAssertThrowsError(try Contract.makeInvoke(
            requestId: "r", sessionId: "s", jpegBase64: "a", wavBase64: nil, text: nil
        )) { error in
            XCTAssertEqual(error as? ContractError, .missingCommand)
        }
    }

    func testDecodesStatusCardAndError() throws {
        let status = Data(#"{"type":"status","request_id":"r","stage":"reading"}"#.utf8)
        guard case .status(let stage) = try Contract.decode(status) else {
            return XCTFail("expected status")
        }
        XCTAssertEqual(stage.stage, .reading)

        let cardJSON = """
        {"type":"card","request_id":"r","title":"Hamlet, Act 3, Scene 1","caption":"Hamlet asks.","image_url":null,"speech_text":"Hamlet is alone.","audio_url":null,"book":{"title":"Hamlet","author":"William Shakespeare","location":"Act 3, Scene 1"},"sources":[{"title":"Hamlet, public-domain text","url":"https://example.com/hamlet"}],"models":{"read":"nemotron","reason":"gemini-4-argon","image":"gemini-nano-banana-2.1"}}
        """
        guard case .card(let card) = try Contract.decode(Data(cardJSON.utf8)) else {
            return XCTFail("expected card")
        }
        XCTAssertEqual(card.title, "Hamlet, Act 3, Scene 1")
        XCTAssertNil(card.imageURL)
        XCTAssertEqual(card.models.reason, "gemini-4-argon")
        XCTAssertEqual(card.book?.location, "Act 3, Scene 1")
        XCTAssertEqual(card.sources.count, 1)

        let error = Data(#"{"type":"error","request_id":"r","code":"no_text_found","message":"blank","retryable":true}"#.utf8)
        guard case .error(let failure) = try Contract.decode(error) else {
            return XCTFail("expected error")
        }
        XCTAssertEqual(failure.code, .noTextFound)
        XCTAssertTrue(failure.retryable)
    }

    func testUnknownErrorCodeBecomesInternalWithoutCrashing() throws {
        let error = Data(#"{"type":"error","request_id":"r","code":"future_code","message":"later","retryable":false}"#.utf8)
        guard case .error(let failure) = try Contract.decode(error) else {
            return XCTFail("expected error")
        }
        XCTAssertEqual(failure.code, .internalError)
        XCTAssertEqual(failure.rawCode, "future_code")
        XCTAssertFalse(failure.retryable)
    }

    private func jsonObject(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

final class CapturePlanTests: XCTestCase {
    func testCameraStopsBeforeTheLensAndSpeechStillRunsWithDisplayOff() {
        let shown = CapturePlan.steps(settings: .demo, typedCommand: nil)
        XCTAssertEqual(shown, [
            .settleHFP, .recordAudio, .startCamera, .takeOneFrame, .stopCamera, .showProgress, .sendInvoke, .speak,
        ])
        XCTAssertTrue(CapturePlan.cameraStopsBeforeDisplay(shown))
        XCTAssertTrue(CapturePlan.speaksEvenIfDisplayIsOff(shown))

        var hidden = CaptureSettings.demo
        hidden.displayEnabled = false
        let voiceOnly = CapturePlan.steps(settings: hidden, typedCommand: nil)
        XCTAssertFalse(voiceOnly.contains(.showProgress))
        XCTAssertTrue(CapturePlan.cameraStopsBeforeDisplay(voiceOnly))
        XCTAssertTrue(CapturePlan.speaksEvenIfDisplayIsOff(voiceOnly))
    }

    func testTypedCommandSkipsTheMicrophone() {
        let steps = CapturePlan.steps(settings: .demo, typedCommand: "draw")
        XCTAssertFalse(steps.contains(.recordAudio))
        XCTAssertFalse(steps.contains(.settleHFP))
        XCTAssertTrue(steps.contains(.takeOneFrame))
    }

    func testPageCapturePrefersASlowHighResolutionStream() {
        XCTAssertEqual(CaptureSettings.demo.frameRate, 2)
        XCTAssertEqual(CaptureSettings.demo.resolution, .high)
        XCTAssertEqual(CaptureSettings.demo.resolution.pixelSize.width, 720)
        XCTAssertFalse(CaptureSettings.demo.useStandalonePhoto)
    }
}

final class SessionMachineTests: XCTestCase {
    func testPausedDoesNotAskForANewSessionAndStoppedDoes() {
        var state = ready()
        state = SessionMachine.reduce(state, .link(.paused))
        XCTAssertFalse(state.needsNewSession)
        XCTAssertFalse(state.canInvoke)
        XCTAssertEqual(state.action, .waitForResume)
        XCTAssertEqual(state.lastCard?.title, "kept")

        state = SessionMachine.reduce(state, .link(.started))
        XCTAssertTrue(state.canInvoke)
        XCTAssertNil(state.banner)
        XCTAssertEqual(state.lastCard?.title, "kept")

        state = SessionMachine.reduce(state, .link(.stopped))
        XCTAssertTrue(state.needsNewSession)
        XCTAssertEqual(state.action, .startNewSession)
        XCTAssertEqual(state.lastCard?.title, "kept")
        XCTAssertFalse(state.canInvoke)
    }

    func testHingesAndBluetoothKeepTheSpecificBannerWhenTheLinkDrops() {
        var state = ready()
        state = SessionMachine.reduce(state, .failure(.hingesClosed, retryable: false))
        XCTAssertTrue(state.needsNewSession)
        XCTAssertTrue(state.banner?.contains("folded") == true)
        state = SessionMachine.reduce(state, .link(.stopped))
        XCTAssertTrue(state.banner?.contains("folded") == true)

        state = ready()
        state = SessionMachine.reduce(state, .failure(.bluetoothLost, retryable: false))
        state = SessionMachine.reduce(state, .link(.stopped))
        XCTAssertTrue(state.banner?.contains("Bluetooth") == true)
        XCTAssertEqual(state.lastCard?.title, "kept")
    }

    func testPermissionDeniedAndUnreadablePageHaveAWayBack() {
        var state = ready()
        state = SessionMachine.reduce(state, .permission(false))
        XCTAssertEqual(state.action, .requestPermission)
        XCTAssertFalse(state.canInvoke)
        XCTAssertEqual(state.lastCard?.title, "kept")

        state = SessionMachine.reduce(state, .permission(true))
        XCTAssertTrue(state.canInvoke)
        XCTAssertNil(state.banner)

        state = SessionMachine.reduce(state, .failure(.unreadablePage, retryable: true))
        XCTAssertEqual(state.action, .retryInvoke)
        XCTAssertTrue(state.canInvoke)
        XCTAssertEqual(state.lastCard?.title, "kept")
    }

    func testACardReplacesTheBannerAndIsWhatThePhoneKeeps() {
        var state = ready()
        state = SessionMachine.reduce(state, .failure(.backendTimeout, retryable: true))
        let card = sampleCard(title: "next")
        state = SessionMachine.reduce(state, .card(card))
        XCTAssertNil(state.banner)
        XCTAssertEqual(state.lastCard?.title, "next")
        XCTAssertEqual(state.action, .none)
    }

    func testBackendCodesMapOntoVisibleFailures() {
        XCTAssertEqual(FailurePolicy.kind(for: .noTextFound), .unreadablePage)
        XCTAssertEqual(FailurePolicy.kind(for: .sttFailed), .speechFailed)
        XCTAssertEqual(FailurePolicy.kind(for: .modelTimeout), .modelTimeout)
        XCTAssertEqual(FailurePolicy.kind(for: .internalError), .backend)
        XCTAssertEqual(FailurePolicy.recovery(for: .backend, retryable: false).action, .none)
        XCTAssertEqual(FailurePolicy.recovery(for: .backend, retryable: true).action, .retryInvoke)
    }

    private func ready() -> PhoneSession {
        var state = PhoneSession()
        state = SessionMachine.reduce(state, .registration(true))
        state = SessionMachine.reduce(state, .permission(true))
        state = SessionMachine.reduce(state, .link(.started))
        state = SessionMachine.reduce(state, .card(sampleCard(title: "kept")))
        return state
    }

    private func sampleCard(title: String) -> CardMessage {
        CardMessage(
            requestId: "r",
            title: title,
            caption: "caption",
            imageURL: nil,
            speechText: "spoken",
            audioURL: nil,
            book: nil,
            sources: [],
            models: ModelTrace()
        )
    }
}

final class LensAndSpeechTests: XCTestCase {
    func testStatusCopyUsesTheWordsTheLensShows() {
        XCTAssertEqual(LensCopy.content(for: .reading), .status(headline: "Reading page", detail: "Finding the passage."))
        XCTAssertEqual(LensCopy.content(for: .drawing), .status(headline: "Drawing", detail: "Making a picture for the lens."))
    }

    func testLensDropsAnythingThatIsNotHTTPS() {
        XCTAssertNil(LensCopy.lensImageURL(nil))
        XCTAssertNil(LensCopy.lensImageURL("http://example.com/a.png"))
        XCTAssertEqual(
            LensCopy.lensImageURL("https://example.com/a.png")?.absoluteString,
            "https://example.com/a.png"
        )
        var card = CardMessage(
            requestId: "r", title: "T", caption: "C", imageURL: "http://insecure/a.png",
            speechText: "Say it", audioURL: nil, book: nil, sources: [], models: ModelTrace()
        )
        guard case .card(_, _, let image) = LensCopy.content(for: card) else {
            return XCTFail("expected card")
        }
        XCTAssertNil(image)
        card.imageURL = "https://cdn.example/a.png"
        guard case .card(_, _, let secure) = LensCopy.content(for: card) else {
            return XCTFail("expected card")
        }
        XCTAssertNotNil(secure)
    }

    func testSpeechWorksWithTheDisplayOffAndFallsBackWhenThereIsNoClip() {
        let card = CardMessage(
            requestId: "r", title: "T", caption: "C", imageURL: nil,
            speechText: "Hamlet is alone.", audioURL: nil, book: nil, sources: [], models: ModelTrace()
        )
        XCTAssertEqual(SpeechPlan.route(card: card, displayEnabled: true), .systemVoice(text: "Hamlet is alone."))
        XCTAssertEqual(SpeechPlan.route(card: card, displayEnabled: false), .systemVoice(text: "Hamlet is alone."))

        var remote = card
        remote.audioURL = "https://cdn.example/a.mp3"
        guard case .remoteAudio(let url, let fallback) = SpeechPlan.route(card: remote, displayEnabled: false) else {
            return XCTFail("expected remote audio")
        }
        XCTAssertEqual(url.absoluteString, "https://cdn.example/a.mp3")
        XCTAssertEqual(fallback, "Hamlet is alone.")

        remote.audioURL = "http://cdn.example/a.mp3"
        XCTAssertEqual(SpeechPlan.route(card: remote, displayEnabled: true), .systemVoice(text: "Hamlet is alone."))
    }
}

final class AudioPrivacyAndConfigTests: XCTestCase {
    func testWavHeaderAndTrailingSilence() {
        let samples: [Int16] = [0, 4000, 4000, 0, 0, 0, 0, 0]
        let trimmed = AudioClip.trimTrailingSilence(pcm16: samples, sampleRate: 4, trailingSeconds: 0.5, threshold: 900)
        XCTAssertEqual(trimmed, [0, 4000, 4000, 0, 0])
        let silent = AudioClip.trimTrailingSilence(pcm16: [0, 0, 0], sampleRate: 4, trailingSeconds: 0.5, threshold: 900)
        XCTAssertEqual(silent, [0, 0, 0])

        let wav = AudioClip.wav(pcm16: [1, -2], sampleRate: 16_000)
        XCTAssertEqual(wav.prefix(4), Data("RIFF".utf8))
        XCTAssertEqual(wav.count, 44 + 4)
        XCTAssertEqual(wav[22], 1)
        XCTAssertEqual(wav[23], 0)
    }

    func testDiscardDropsTheFrameAndTheClip() {
        var capture = EphemeralCapture(frameJPEG: Data([1, 2, 3]), wav: Data([4]), text: "explain")
        XCTAssertTrue(capture.holdsMedia)
        capture.discard()
        XCTAssertFalse(capture.holdsMedia)
        XCTAssertNil(capture.text)
        XCTAssertEqual(capture.frameJPEG, Data())
    }

    func testBackendConfigIsOnlyAWebSocket() {
        XCTAssertNil(BackendConfig(string: "https://example.com/ws"))
        XCTAssertNil(BackendConfig(string: "wss://"))
        XCTAssertNil(BackendConfig(string: "not a url"))
        let config = BackendConfig(string: "  wss://metalab.modal.run/ws  ")
        XCTAssertEqual(config?.webSocketURL.absoluteString, "wss://metalab.modal.run/ws")
        XCTAssertFalse(BackendConfig.placeholder.contains("AIza"))
    }

    func testDeadlineResetsOnTrafficAndStillHasACap() {
        let deadline = Deadline(overallSeconds: 90, idleSeconds: 30)
        XCTAssertFalse(deadline.isTimedOut(elapsed: 10, sinceLastServerMessage: 10))
        XCTAssertTrue(deadline.isTimedOut(elapsed: 40, sinceLastServerMessage: 30))
        XCTAssertFalse(deadline.isTimedOut(elapsed: 80, sinceLastServerMessage: 5))
        XCTAssertTrue(deadline.isTimedOut(elapsed: 90, sinceLastServerMessage: 1))
    }
}
