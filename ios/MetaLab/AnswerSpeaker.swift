import AVFoundation
import MetaLabCore

/// Speaks the answer on the glasses speakers when the HFP route is up, and on the phone speaker otherwise.
/// A null `audio_url` uses the system voice. Playback failure falls back to `speech_text`.
@MainActor
final class AnswerSpeaker {
    private let synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?

    func speak(_ route: SpeechRoute) async {
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
                await speakText(fallbackText)
            }
        }
    }

    func stop() {
        player?.stop()
        player = nil
        synthesizer.stopSpeaking(at: .immediate)
    }

    private func speakText(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        try? configureRoute()
        let utterance = AVSpeechUtterance(string: trimmed)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        utterance.prefersAssistiveTechnologySettings = true
        synthesizer.speak(utterance)
        let estimate = Double(trimmed.split(separator: " ").count) * 0.45 + 0.8
        try? await Task.sleep(for: .seconds(min(estimate, 30)))
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
