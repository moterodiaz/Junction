import AVFoundation
import MetaLabCore

/// Speaks the answer on the glasses speakers when the HFP route is up, and on the phone speaker otherwise.
/// A null `audio_url` uses the system voice. Playback failure falls back to `speech_text`.
@MainActor
final class AnswerSpeaker: NSObject, AVSpeechSynthesizerDelegate {
    private let synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?
    private var earconPlayer: AVAudioPlayer?
    private var speechDone: CheckedContinuation<Void, Never>?
    private var turns = SpeechTurnGate<ObjectIdentifier>()
    private var speaking: AVSpeechUtterance?
    /// Stopped utterances stay alive until their delegate callback arrives, so a new utterance
    /// cannot reuse the address and be mistaken for the stopped one.
    private var retired: [ObjectIdentifier: AVSpeechUtterance] = [:]
    var earconsEnabled: Bool = true

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    /// Plays a subtle, non-blocking client-side status earcon/chime cue for a server pipeline stage.
    /// Safe no-op in headless/simulator environments and never interrupts active speech synthesis.
    func playEarcon(for stage: PipelineStage) {
        guard earconsEnabled else { return }
        guard !(player?.isPlaying ?? false), !synthesizer.isSpeaking else { return }
        guard let data = Self.earconAudioData(for: stage) else { return }
        do {
            stopEarcon()
            try? configureRoute()
            let player = try AVAudioPlayer(data: data)
            player.volume = 0.35
            self.earconPlayer = player
            player.prepareToPlay()
            player.play()
        } catch {
            // Safe no-op in simulator or headless test environments
        }
    }

    func stopEarcon() {
        earconPlayer?.stop()
        earconPlayer = nil
    }

    func speak(_ route: SpeechRoute) async {
        stopEarcon()
        switch route {
        case .silent:
            return
        case .systemVoice(let text):
            await speakText(text)
        case .remoteAudio(let url, let fallbackText):
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                    throw URLError(.badServerResponse)
                }
                try Task.checkCancellation()
                try configureRoute()
                let player = try AVAudioPlayer(data: data)
                self.player = player
                player.prepareToPlay()
                if !player.play() {
                    await speakText(fallbackText)
                } else {
                    let duration = player.duration
                    try? await Task.sleep(for: .seconds(duration + 0.2))
                }
            } catch {
                if Task.isCancelled { return }
                await speakText(fallbackText)
            }
        }
    }

    func stop() {
        stopEarcon()
        player?.stop()
        player = nil
        synthesizer.stopSpeaking(at: .immediate)
        retireCurrentUtterance()
        finishSpeech()
    }

    private static let earconCache: [PipelineStage: Data] = {
        var cache: [PipelineStage: Data] = [:]
        for stage in PipelineStage.allCases {
            if let data = makeChime(for: stage) {
                cache[stage] = data
            }
        }
        return cache
    }()

    static func earconAudioData(for stage: PipelineStage) -> Data? {
        earconCache[stage]
    }

    private static func makeChime(for stage: PipelineStage) -> Data? {
        let sampleRate = 24000
        let duration: Double = 0.08
        let sampleCount = Int(Double(sampleRate) * duration)

        let frequency: Double
        switch stage {
        case .transcribing:
            frequency = 523.25 // C5
        case .reading:
            frequency = 659.25 // E5
        case .thinking:
            frequency = 783.99 // G5
        case .drawing:
            frequency = 1046.50 // C6
        }

        let maxAmp: Double = 4000.0
        let attack = Int(Double(sampleCount) * 0.15)
        let decayStart = Int(Double(sampleCount) * 0.50)

        var samples = [Int16]()
        samples.reserveCapacity(sampleCount)

        for i in 0..<sampleCount {
            let t = Double(i) / Double(sampleRate)
            let waveform = sin(2.0 * .pi * frequency * t) + 0.3 * sin(4.0 * .pi * frequency * t)
            let envelope: Double
            if i < attack {
                envelope = Double(i) / Double(attack)
            } else if i > decayStart {
                envelope = max(0.0, 1.0 - Double(i - decayStart) / Double(sampleCount - decayStart))
            } else {
                envelope = 1.0
            }
            let sampleVal = waveform * maxAmp * envelope
            let clamped = max(Double(Int16.min), min(Double(Int16.max), sampleVal))
            samples.append(Int16(clamped))
        }

        return AudioClip.wav(pcm16: samples, sampleRate: sampleRate)
    }

    private func finishSpeech() {
        let waiting = speechDone
        speechDone = nil
        waiting?.resume()
    }

    private func retireCurrentUtterance() {
        guard let previous = speaking else { return }
        speaking = nil
        turns.abandon()
        retired[ObjectIdentifier(previous)] = previous
    }

    private func utteranceEnded(_ id: ObjectIdentifier) {
        retired[id] = nil
        guard turns.end(id) else { return }
        speaking = nil
        finishSpeech()
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        let id = ObjectIdentifier(utterance)
        Task { @MainActor in self.utteranceEnded(id) }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        let id = ObjectIdentifier(utterance)
        Task { @MainActor in self.utteranceEnded(id) }
    }

    private func speakText(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !Task.isCancelled else { return }
        try? configureRoute()
        let utterance = AVSpeechUtterance(string: trimmed)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        utterance.prefersAssistiveTechnologySettings = true
        retireCurrentUtterance()
        finishSpeech()
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            speechDone = continuation
            speaking = utterance
            turns.begin(ObjectIdentifier(utterance))
            synthesizer.speak(utterance)
        }
    }

    private func configureRoute() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP, .defaultToSpeaker])
        try session.setActive(true)
        if let hfp = session.availableInputs?.first(where: { $0.portType == .bluetoothHFP }) {
            try session.setPreferredInput(hfp)
        }
    }
}
