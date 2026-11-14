import AVFoundation
import Foundation
import MWDATCamera
import MWDATCore
import MWDATDisplay
import MetaLabCore
import UIKit

enum GlassesProblem: Error {
    case notReady
    case permissionDenied
    case hingesClosed
    case bluetoothLost
    case timeout
}

/// DAT session, one-shot capture, then display. Capture and display are never active together.
@MainActor
final class GlassesBridge {
    var onLink: ((GlassesLink) -> Void)?
    var onFailure: ((FailureKind) -> Void)?
    var onRegistration: ((Bool) -> Void)?
    var onPermission: ((Bool) -> Void)?
    var onInvocation: (() -> Void)?

    private let wearables: any WearablesInterface
    private var session: DeviceSession?
    private var camera: MWDATCamera.Camera?
    private var display: MWDATDisplay.Display?
    private var voice: VoiceInvocationsStream?
    private var voiceDevice: DeviceIdentifier?
    private let tokens = ListenerTokenBag()
    private var observeTask: Task<Void, Never>?
    private var deviceTask: Task<Void, Never>?
    private var sessionTask: Task<Void, Never>?

    init(wearables: any WearablesInterface = Wearables.shared) {
        self.wearables = wearables
    }

    func start() {
        observeTask?.cancel()
        observeTask = Task { [weak self] in
            guard let self else { return }
            for await state in self.wearables.registrationStateStream() {
                let registered = state == .registered
                self.onRegistration?(registered)
                if registered {
                    await self.refreshPermission()
                }
            }
        }
        deviceTask?.cancel()
        deviceTask = Task { [weak self] in
            guard let self else { return }
            for await identifiers in self.wearables.devicesStream() {
                if identifiers.isEmpty {
                    self.onFailure?(.bluetoothLost)
                } else if let first = identifiers.first {
                    self.startVoice(on: first)
                }
            }
        }
    }

    func register() async {
        do {
            try await wearables.startRegistration()
        } catch {
            onFailure?(.permissionDenied)
        }
    }

    func refreshPermission() async {
        do {
            let status = try await wearables.checkPermissionStatus(.camera)
            if status == .granted {
                onPermission?(true)
                await ensureSession()
            }
        } catch {
            return
        }
    }

    func requestCameraPermission() async {
        do {
            let status = try await wearables.requestPermission(.camera)
            onPermission?(status == .granted)
            if status == .granted {
                await ensureSession()
            }
        } catch {
            onPermission?(false)
        }
    }

    func handle(url: URL) async {
        guard
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
            components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true
        else {
            return
        }
        do {
            _ = try await wearables.handleUrl(url)
        } catch {
            onFailure?(.permissionDenied)
        }
    }

    /// A stopped session cannot be restarted. Reconnect creates a new one and keeps the phone's last card.
    func reconnect() async {
        session?.stop()
        session = nil
        camera = nil
        display = nil
        await ensureSession()
    }

    func ensureSession() async {
        if let session, session.state != .stopped {
            if session.state == .idle {
                do { try session.start() } catch { map(error) }
            }
            return
        }
        let selector = AutoDeviceSelector(wearables: wearables) { device in
            device.supportsDisplay()
        }
        do {
            let created = try wearables.createSession(deviceSelector: selector)
            session = created
            sessionTask?.cancel()
            sessionTask = Task { [weak self] in
                for await state in created.stateStream() {
                    self?.onLink?(Self.link(state))
                    if state == .started {
                        self?.watchDevice(created.device)
                    }
                }
            }
            created.errorPublisher.listen { [weak self] error in
                Task { @MainActor in
                    self?.map(error)
                }
            }.store(in: tokens)
            try created.start()
        } catch {
            map(error)
        }
    }

    func settleHFP() async throws {
        let audio = AVAudioSession.sharedInstance()
        try audio.setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP])
        try audio.setActive(true)
        if let hfp = audio.availableInputs?.first(where: { $0.portType == .bluetoothHFP }) {
            try audio.setPreferredInput(hfp)
        }
        try await Task.sleep(for: .milliseconds(300))
    }

    func recordWav(maxSeconds: Double, trailingSilence: Double, sampleRate: Int) async throws -> Data {
        let allowed = await AVAudioApplication.requestRecordPermission()
        guard allowed else { throw GlassesProblem.permissionDenied }
        try await settleHFP()

        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard
            let target = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: Double(sampleRate),
                channels: 1,
                interleaved: true
            ),
            let converter = AVAudioConverter(from: inputFormat, to: target)
        else {
            throw GlassesProblem.notReady
        }

        let box = SampleBox()
        input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { buffer, _ in
            let ratio = target.sampleRate / max(inputFormat.sampleRate, 1)
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
            guard let converted = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: max(capacity, 32)) else { return }
            var conversionError: NSError?
            var consumed = false
            converter.convert(to: converted, error: &conversionError) { _, status in
                if consumed {
                    status.pointee = .noDataNow
                    return nil
                }
                consumed = true
                status.pointee = .haveData
                return buffer
            }
            guard conversionError == nil, let channel = converted.int16ChannelData else { return }
            let count = Int(converted.frameLength)
            box.append(Array(UnsafeBufferPointer(start: channel[0], count: count)))
        }
        engine.prepare()
        try engine.start()
        try await Task.sleep(for: .seconds(maxSeconds))
        engine.stop()
        input.removeTap(onBus: 0)
        let trimmed = AudioClip.trimTrailingSilence(
            pcm16: box.samples,
            sampleRate: sampleRate,
            trailingSeconds: trailingSilence
        )
        return AudioClip.wav(pcm16: trimmed, sampleRate: sampleRate)
    }

    func captureFrame(settings: CaptureSettings) async throws -> Data {
        guard let session, session.state == .started else { throw GlassesProblem.notReady }
        stopCamera()
        let resolution: StreamingResolution
        switch settings.resolution {
        case .high: resolution = .high
        case .medium: resolution = .medium
        case .low: resolution = .low
        }
        let config = StreamConfiguration(
            videoCodec: .raw,
            resolution: resolution,
            frameRate: UInt(max(2, settings.frameRate))
        )
        guard let camera = try session.addCamera(config: config) else {
            throw GlassesProblem.notReady
        }
        self.camera = camera
        if settings.useStandalonePhoto {
            return try await captureStandalone(camera.photo)
        }
        return try await captureFirstFrame(camera.stream)
    }

    func stopCamera() {
        camera?.stop()
        camera = nil
    }

    func show(_ content: LensContent) async throws {
        guard let session, session.state == .started else { throw GlassesProblem.notReady }
        // The camera must already be stopped. Adding a display while it is attached is the known failure.
        stopCamera()
        if display == nil {
            let created = try session.addDisplay()
            display = created
            await waitUntilStarted(created)
        }
        guard let display else { throw GlassesProblem.notReady }
        try await display.send(LensLayout.make(content))
    }

    private func captureFirstFrame(_ stream: MWDATCamera.Stream) async throws -> Data {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            let gate = ResumeGate()
            stream.errorPublisher.listen { error in
                Task { @MainActor in
                    guard gate.claim() else { return }
                    continuation.resume(throwing: Self.problem(from: error))
                }
            }.store(in: tokens)
            stream.videoFramePublisher.listen { frame in
                Task { @MainActor in
                    guard let image = frame.makeUIImage(), let jpeg = image.jpegData(compressionQuality: 0.85) else {
                        return
                    }
                    guard gate.claim() else { return }
                    continuation.resume(returning: jpeg)
                }
            }.store(in: tokens)
            stream.start()
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(8))
                guard gate.claim() else { return }
                continuation.resume(throwing: GlassesProblem.timeout)
            }
        }
    }

    private func captureStandalone(_ photo: MWDATCamera.Photo) async throws -> Data {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            let gate = ResumeGate()
            photo.errorPublisher.listen { error in
                Task { @MainActor in
                    guard gate.claim() else { return }
                    continuation.resume(throwing: Self.problem(from: error))
                }
            }.store(in: tokens)
            photo.photoDataPublisher.listen { capture in
                Task { @MainActor in
                    guard gate.claim() else { return }
                    continuation.resume(returning: capture.imageData)
                }
            }.store(in: tokens)
            photo.statePublisher.listen { state in
                if state == .started {
                    photo.capturePhoto(resolution: .full, quality: .high)
                }
            }.store(in: tokens)
            photo.start()
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(20))
                guard gate.claim() else { return }
                continuation.resume(throwing: GlassesProblem.timeout)
            }
        }
    }

    private func waitUntilStarted(_ display: MWDATDisplay.Display) async {
        if display.state == .started { return }
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            let gate = ResumeGate()
            display.statePublisher.listen { state in
                Task { @MainActor in
                    guard state == .started || state == .stopped else { return }
                    guard gate.claim() else { return }
                    continuation.resume()
                }
            }.store(in: tokens)
            display.start()
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(5))
                guard gate.claim() else { return }
                continuation.resume()
            }
        }
    }

    private func watchDevice(_ device: Device?) {
        guard let device else { return }
        device.addDeviceStateListener { [weak self] state in
            Task { @MainActor in
                if state.hingeState == .closed {
                    self?.onFailure?(.hingesClosed)
                } else if state.linkState == .disconnected {
                    self?.onFailure?(.bluetoothLost)
                }
            }
        }.store(in: tokens)
    }

    private func startVoice(on identifier: DeviceIdentifier) {
        guard voiceDevice != identifier else { return }
        voiceDevice = identifier
        do {
            if voice == nil {
                let stream = try VoiceInvocationsStream(wearables: wearables)
                stream.invocationsPublisher.listen { [weak self] invocation in
                    Task { @MainActor in
                        guard let launch = invocation as? LaunchApp else { return }
                        _ = await launch.responseHandle.sendSuccess(actionOutput: nil)
                        self?.onInvocation?()
                    }
                }.store(in: tokens)
                stream.errorPublisher.listen { _ in }.store(in: tokens)
                voice = stream
            }
            try voice?.start(deviceIdentifier: identifier)
        } catch {
            voiceDevice = nil
        }
    }

    private func map(_ error: DeviceSessionError) {
        switch error {
        case .datAppOnTheGlassesUpdateRequired:
            Task { try? await wearables.openDATGlassesAppUpdate() }
            onFailure?(.sessionStopped)
        case .noEligibleDevice:
            onFailure?(.bluetoothLost)
        default:
            onFailure?(.sessionStopped)
        }
    }

    private static func link(_ state: DeviceSessionState) -> GlassesLink {
        switch state {
        case .idle: .idle
        case .starting: .starting
        case .started: .started
        case .paused: .paused
        case .stopping: .stopping
        case .stopped: .stopped
        }
    }

    private static func problem(from error: StreamError) -> GlassesProblem {
        switch error {
        case .permissionDenied: .permissionDenied
        case .hingesClosed: .hingesClosed
        case .deviceNotConnected, .deviceNotFound: .bluetoothLost
        default: .timeout
        }
    }

    private static func problem(from error: PhotoError) -> GlassesProblem {
        switch error {
        case .permissionDenied: .permissionDenied
        case .deviceDisconnected: .bluetoothLost
        default: .timeout
        }
    }
}

private final class SampleBox: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Int16] = []

    var samples: [Int16] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func append(_ chunk: [Int16]) {
        lock.lock()
        storage.append(contentsOf: chunk)
        lock.unlock()
    }
}

private final class ResumeGate: @unchecked Sendable {
    private let lock = NSLock()
    private var claimed = false

    func claim() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if claimed { return false }
        claimed = true
        return true
    }
}
