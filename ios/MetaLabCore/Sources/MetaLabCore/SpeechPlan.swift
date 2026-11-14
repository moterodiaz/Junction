import Foundation

public enum SpeechRoute: Equatable, Sendable {
    /// `audio_url` was null, or was not an https URL. The phone speaks `speech_text`.
    case systemVoice(text: String)
    case remoteAudio(url: URL, fallbackText: String)
    case silent
}

public enum SpeechPlan {
    /// The answer is spoken whether or not the display is on.
    /// `displayEnabled` is accepted so callers cannot forget the rule; it does not change the route.
    public static func route(card: CardMessage, displayEnabled: Bool) -> SpeechRoute {
        _ = displayEnabled
        if let raw = card.audioURL, let url = URL(string: raw), url.scheme?.lowercased() == "https" {
            return .remoteAudio(url: url, fallbackText: card.speechText)
        }
        let text = card.speechText.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            return .silent
        }
        return .systemVoice(text: text)
    }
}
