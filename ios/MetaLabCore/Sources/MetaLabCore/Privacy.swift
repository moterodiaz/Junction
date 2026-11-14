import Foundation

/// The frame and the clip live here until the card or the error comes back, then `discard()` zeroes them.
/// There is no save method. Exporting a sample frame is a separate, explicit developer action in the app.
public struct EphemeralCapture: Equatable, Sendable {
    public var frameJPEG: Data
    public var wav: Data?
    public var text: String?

    public init(frameJPEG: Data, wav: Data?, text: String?) {
        self.frameJPEG = frameJPEG
        self.wav = wav
        self.text = text
    }

    public var holdsMedia: Bool {
        !frameJPEG.isEmpty || wav != nil
    }

    public mutating func discard() {
        frameJPEG = Data()
        wav = nil
        text = nil
    }
}

/// WebSocket URL only. The Gemini API key is a backend secret and is never stored or sent by the phone.
public struct BackendConfig: Equatable, Sendable {
    public var webSocketURL: URL

    public init(webSocketURL: URL) {
        self.webSocketURL = webSocketURL
    }

    public init?(string: String) {
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              scheme == "ws" || scheme == "wss",
              let host = url.host, !host.isEmpty
        else {
            return nil
        }
        self.webSocketURL = url
    }

    public static let placeholder = "wss://your-modal-app.modal.run/ws"
}
