import Foundation
import MWDATCore
import MetaLabCore

/// Phone state for one book. The Gemini key never enters this type.
/// The backend, once it has that key, fills `models.reason` and `models.image` on the card.
@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var session = PhoneSession()
    @Published private(set) var lens: LensContent = .status(
        headline: "MetaLab",
        detail: "Connect the glasses, then ask about the page."
    )
    @Published private(set) var phase: Phase = .idle
    @Published var backendURL: String {
        didSet { UserDefaults.standard.set(backendURL, forKey: Keys.backend) }
    }
    @Published var typedCommand: String = ""
    @Published var keepSampleFrames: Bool = false
    @Published var useStandalonePhoto: Bool = false
    @Published private(set) var sampleFrameURL: URL?
    @Published private(set) var configureError: String?

    enum Phase: Equatable {
        case idle
        case capturing
        case waiting
        case speaking
    }

    private let glasses: GlassesBridge?
    private let socket = BackendSocket()
    private let speaker = AnswerSpeaker()
    private var bookSessionId: String
    private var activeRequest: String?
    private var captureTask: Task<Void, Never>?
    private var waitTask: Task<Void, Never>?
    private var presentTask: Task<Void, Never>?
    private var lastServerMessage = Date()
    private var startedWaiting = Date()

    init() {
        let stored = UserDefaults.standard.string(forKey: Keys.backend)
        backendURL = (stored?.isEmpty == false) ? stored! : BackendConfig.placeholder
        if let existing = UserDefaults.standard.string(forKey: Keys.book) {
            bookSessionId = existing
        } else {
            bookSessionId = UUID().uuidString
            UserDefaults.standard.set(bookSessionId, forKey: Keys.book)
        }
        do {
            try Wearables.configure()
            let bridge = GlassesBridge()
            glasses = bridge
            bind(bridge)
            bridge.start()
        } catch let error as WearablesError {
            glasses = nil
            configureError = Self.configureMessage(error)
        } catch {
            glasses = nil
            configureError = error.localizedDescription
        }
    }

    var blockedReason: String? {
        if session.banner != nil, !session.canInvoke { return session.banner }
        if !session.registered { return "Register MetaLab in the Meta AI app." }
        if !session.permissionGranted { return "Allow the camera once, in Meta AI." }
        if session.link == .paused { return "Glasses paused." }
        if session.needsNewSession || session.link == .stopped { return "Reconnect the glasses." }
        if session.link != .started { return "Waiting for the glasses." }
        if BackendConfig(string: backendURL) == nil { return "Set the backend WebSocket URL." }
        return nil
    }

    func setDisplayEnabled(_ enabled: Bool) {
        session = SessionMachine.reduce(session, .displayEnabled(enabled))
        if !enabled { glasses?.clearDisplay() }
    }

    func register() async { await glasses?.register() }
    func allowCamera() async { await glasses?.requestCameraPermission() }
    func reconnect() async { await glasses?.reconnect() }

    func handle(url: URL) async { await glasses?.handle(url: url) }

    func newBook() {
        // Invalidate any request in flight so its answer cannot restore the old book's card.
        cancelWork()
        glasses?.stopCamera()
        activeRequest = nil
        phase = .idle
        bookSessionId = UUID().uuidString
        UserDefaults.standard.set(bookSessionId, forKey: Keys.book)
        session.lastCard = nil
    }

    func invoke() {
        guard session.canInvoke, phase == .idle, BackendConfig(string: backendURL) != nil else { return }
        phase = .capturing
        let settings = CaptureSettings(
            displayEnabled: session.displayEnabled,
            useStandalonePhoto: useStandalonePhoto
        )
        let command = typedCommand
        let steps = CapturePlan.steps(settings: settings, typedCommand: command)
        captureTask = Task { await run(steps: steps, settings: settings, typedCommand: command) }
    }

    private func bind(_ glasses: GlassesBridge) {
        glasses.onRegistration = { [weak self] registered in
            self?.session = SessionMachine.reduce(self?.session ?? PhoneSession(), .registration(registered))
        }
        glasses.onPermission = { [weak self] granted in
            guard let self else { return }
            self.session = SessionMachine.reduce(self.session, .permission(granted))
        }
        glasses.onLink = { [weak self] link in
            guard let self else { return }
            self.session = SessionMachine.reduce(self.session, .link(link))
        }
        glasses.onFailure = { [weak self] kind in
            guard let self else { return }
            self.fail(kind, retryable: false)
        }
        glasses.onInvocation = { [weak self] in
            self?.invoke()
        }
        socket.onText = { [weak self] text in
            Task { @MainActor in
                self?.receive(text)
            }
        }
        socket.onDisconnect = { [weak self] in
            Task { @MainActor in
                guard let self, self.phase == .waiting else { return }
                self.fail(.backendTimeout, retryable: true)
            }
        }
    }

    private func run(steps: [CaptureStep], settings: CaptureSettings, typedCommand: String) async {
        var frame = Data()
        var wav: Data?
        do {
            for step in steps {
                try Task.checkCancellation()
                switch step {
                case .settleHFP:
                    try await glasses?.settleHFP()
                case .recordAudio:
                    publish(LensCopy.content(for: .transcribing))
                    wav = try await glasses?.recordWav(
                        maxSeconds: settings.maxRecordSeconds,
                        trailingSilence: settings.trailingSilenceSeconds,
                        sampleRate: settings.sampleRate
                    )
                case .startCamera:
                    break
                case .takeOneFrame:
                    publish(LensCopy.content(for: .reading))
                    frame = try await glasses?.captureFrame(settings: settings) ?? Data()
                    exportSampleIfAsked(frame)
                case .stopCamera:
                    glasses?.stopCamera()
                case .showProgress:
                    await show(LensCopy.content(for: .reading))
                case .sendInvoke:
                    try await send(frame: frame, wav: wav, text: typedCommand)
                    frame = Data()
                    wav = nil
                case .speak:
                    break
                }
            }
        } catch is CancellationError {
            // A newer request may own the camera now; whoever cancelled already stopped it.
            return
        } catch let problem as GlassesProblem {
            if Task.isCancelled { return }
            glasses?.stopCamera()
            fail(kind(problem), retryable: true)
        } catch {
            if Task.isCancelled { return }
            glasses?.stopCamera()
            fail(.backend, retryable: true)
        }
    }

    private func send(frame: Data, wav: Data?, text: String) async throws {
        guard let config = BackendConfig(string: backendURL) else {
            fail(.backend, retryable: false)
            return
        }
        try Task.checkCancellation()
        let requestId = UUID().uuidString
        activeRequest = requestId
        let message = try Contract.makeInvoke(
            requestId: requestId,
            sessionId: bookSessionId,
            jpegBase64: frame.base64EncodedString(),
            wavBase64: wav?.base64EncodedString(),
            text: text
        )
        let body = try Contract.encode(message)
        // The deadline covers connecting too, so an offline phone cannot stay in "Capturing".
        startedWaiting = Date()
        lastServerMessage = Date()
        armDeadline(for: requestId)
        socket.disconnect()
        socket.connect(url: config.webSocketURL)
        try await socket.send(body)
        guard activeRequest == requestId else { return }
        phase = .waiting
        startedWaiting = Date()
        lastServerMessage = Date()
    }

    private func receive(_ text: String) {
        guard phase == .waiting || phase == .speaking, let data = text.data(using: .utf8) else { return }
        guard let event = try? Contract.decode(data) else { return }
        switch event {
        case .status(let status):
            guard status.requestId == activeRequest else { return }
            lastServerMessage = Date()
            Task { await show(LensCopy.content(for: status.stage)) }
        case .card(let card):
            guard card.requestId == activeRequest else { return }
            lastServerMessage = Date()
            waitTask?.cancel()
            session = SessionMachine.reduce(session, .card(card))
            phase = .speaking
            let requestId = card.requestId
            presentTask?.cancel()
            presentTask = Task { [weak self] in
                guard let self else { return }
                await self.show(LensCopy.content(for: card))
                guard !Task.isCancelled, self.activeRequest == requestId else { return }
                await self.speaker.speak(SpeechPlan.route(card: card, displayEnabled: self.session.displayEnabled))
                guard !Task.isCancelled, self.activeRequest == requestId, self.phase == .speaking else { return }
                self.phase = .idle
            }
        case .error(let error):
            guard error.requestId == activeRequest else { return }
            waitTask?.cancel()
            let kind = FailurePolicy.kind(for: error.code)
            fail(kind, retryable: error.retryable, message: error.message)
        }
    }

    private func armDeadline(for requestId: String) {
        waitTask?.cancel()
        waitTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(500))
                guard let self, self.activeRequest == requestId,
                      self.phase == .waiting || self.phase == .capturing else { return }
                let elapsed = Date().timeIntervalSince(self.startedWaiting)
                let idle = Date().timeIntervalSince(self.lastServerMessage)
                if Deadline.demo.isTimedOut(elapsed: elapsed, sinceLastServerMessage: idle) {
                    self.fail(.backendTimeout, retryable: true)
                    return
                }
            }
        }
    }

    private func show(_ content: LensContent) async {
        lens = content
        guard session.displayEnabled else { return }
        do {
            try await glasses?.show(content)
        } catch {
            // Plan B: the phone still shows the card and the answer is spoken.
        }
    }

    private func publish(_ content: LensContent) {
        lens = content
    }

    private func fail(_ kind: FailureKind, retryable: Bool, message: String? = nil) {
        cancelWork()
        activeRequest = nil
        phase = .idle
        session = SessionMachine.reduce(session, .failure(kind, retryable: retryable))
        if let message, !message.isEmpty {
            session.banner = message
        }
        let content = LensCopy.content(for: kind)
        lens = content
        if session.displayEnabled {
            Task { try? await glasses?.show(content) }
        }
    }

    /// Stops every task and sound belonging to the current request.
    private func cancelWork() {
        captureTask?.cancel()
        waitTask?.cancel()
        presentTask?.cancel()
        speaker.stop()
        socket.disconnect()
    }

    private func kind(_ problem: GlassesProblem) -> FailureKind {
        switch problem {
        case .permissionDenied: .permissionDenied
        case .microphoneDenied: .microphoneDenied
        case .hingesClosed: .hingesClosed
        case .bluetoothLost: .bluetoothLost
        case .timeout, .notReady: .backendTimeout
        }
    }

    private func exportSampleIfAsked(_ jpeg: Data) {
        guard keepSampleFrames else {
            sampleFrameURL = nil
            return
        }
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("sample-frames", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let url = folder.appendingPathComponent("frame-\(Int(Date().timeIntervalSince1970)).jpg")
            try jpeg.write(to: url, options: .atomic)
            sampleFrameURL = url
        } catch {
            sampleFrameURL = nil
        }
    }

    private static func configureMessage(_ error: WearablesError) -> String {
        switch error {
        case .alreadyConfigured:
            return "Meta AI was configured twice."
        case .missingInfoDictionary, .missingBundleIdentifier, .missingAppName, .missingAppVersion, .missingBuildNumber:
            return "The app is missing a Wearables setting. \(error.description)"
        case .configurationError:
            return "Wearables rejected the app settings. \(error.description)"
        case .internalError:
            return "Meta AI isn't available on this device. Use a phone with the Meta AI app installed."
        @unknown default:
            return error.description
        }
    }

    private enum Keys {
        static let backend = "metalab.backendURL"
        static let book = "metalab.bookSessionId"
        static let configure = "metalab.configureError"
    }
}
