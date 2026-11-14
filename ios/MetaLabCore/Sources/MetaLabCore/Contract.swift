import Foundation

/// Wire types for the draft in PRD section 7.
/// `contracts/` replaces this decoder when issue #24 lands. Field names stay identical.

public enum PipelineStage: String, Codable, Sendable, CaseIterable, Equatable {
    case transcribing
    case reading
    case thinking
    case drawing
}

public struct MediaPayload: Codable, Equatable, Sendable {
    public var mime: String
    public var b64: String

    public init(mime: String, b64: String) {
        self.mime = mime
        self.b64 = b64
    }
}

public struct InvokeMessage: Equatable, Sendable {
    public var type: String
    public var requestId: String
    public var sessionId: String
    public var frame: MediaPayload
    public var audio: MediaPayload?
    public var text: String?

    public init(
        requestId: String,
        sessionId: String,
        frame: MediaPayload,
        audio: MediaPayload?,
        text: String?
    ) {
        self.type = "invoke"
        self.requestId = requestId
        self.sessionId = sessionId
        self.frame = frame
        self.audio = audio
        self.text = text
    }
}

public struct StatusMessage: Codable, Equatable, Sendable {
    public var type: String
    public var requestId: String
    public var stage: PipelineStage

    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case stage
    }

    public init(requestId: String, stage: PipelineStage) {
        self.type = "status"
        self.requestId = requestId
        self.stage = stage
    }
}

public struct BookLocation: Codable, Equatable, Sendable {
    public var title: String
    public var author: String
    public var location: String

    public init(title: String, author: String, location: String) {
        self.title = title
        self.author = author
        self.location = location
    }
}

public struct SourceCitation: Codable, Equatable, Sendable {
    public var title: String
    public var url: String

    public init(title: String, url: String) {
        self.title = title
        self.url = url
    }
}

/// Model ids the backend actually ran. Empty strings mean that step has not been wired yet.
/// Reasoning and image generation fill in once the backend has a Gemini API key.
public struct ModelTrace: Codable, Equatable, Sendable {
    public var read: String
    public var reason: String
    public var image: String

    public init(read: String = "", reason: String = "", image: String = "") {
        self.read = read
        self.reason = reason
        self.image = image
    }
}

public struct CardMessage: Equatable, Sendable {
    public var type: String
    public var requestId: String
    public var title: String
    public var caption: String
    public var imageURL: String?
    public var speechText: String
    public var audioURL: String?
    public var book: BookLocation?
    public var sources: [SourceCitation]
    public var models: ModelTrace

    public init(
        requestId: String,
        title: String,
        caption: String,
        imageURL: String?,
        speechText: String,
        audioURL: String?,
        book: BookLocation?,
        sources: [SourceCitation],
        models: ModelTrace
    ) {
        self.type = "card"
        self.requestId = requestId
        self.title = title
        self.caption = caption
        self.imageURL = imageURL
        self.speechText = speechText
        self.audioURL = audioURL
        self.book = book
        self.sources = sources
        self.models = models
    }
}

public enum ServerErrorCode: String, Codable, Sendable, Equatable, CaseIterable {
    case noTextFound = "no_text_found"
    case sttFailed = "stt_failed"
    case modelTimeout = "model_timeout"
    case internalError = "internal"
}

public struct ErrorMessage: Equatable, Sendable {
    public var type: String
    public var requestId: String
    public var code: ServerErrorCode
    public var message: String
    public var retryable: Bool
    /// The code string from the server, kept when it is not one of the four known codes.
    public var rawCode: String

    public init(
        requestId: String,
        code: ServerErrorCode,
        message: String,
        retryable: Bool,
        rawCode: String? = nil
    ) {
        self.type = "error"
        self.requestId = requestId
        self.code = code
        self.message = message
        self.retryable = retryable
        self.rawCode = rawCode ?? code.rawValue
    }
}

public enum ServerEvent: Equatable, Sendable {
    case status(StatusMessage)
    case card(CardMessage)
    case error(ErrorMessage)
}

public enum ContractError: Error, Equatable, Sendable {
    case missingFrame
    case missingCommand
    case badJSON
    case wrongType(String)
    case missingField(String)
}

public enum Contract {
    public static let jpegMIME = "image/jpeg"
    public static let wavMIME = "audio/wav"

    public static func makeInvoke(
        requestId: String,
        sessionId: String,
        jpegBase64: String,
        wavBase64: String?,
        text: String?
    ) throws -> InvokeMessage {
        let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines)
        let command = (trimmed?.isEmpty == false) ? trimmed : nil
        if jpegBase64.isEmpty {
            throw ContractError.missingFrame
        }
        if command == nil && (wavBase64?.isEmpty != false) {
            throw ContractError.missingCommand
        }
        let audio = wavBase64.flatMap { value -> MediaPayload? in
            value.isEmpty ? nil : MediaPayload(mime: wavMIME, b64: value)
        }
        return InvokeMessage(
            requestId: requestId,
            sessionId: sessionId,
            frame: MediaPayload(mime: jpegMIME, b64: jpegBase64),
            audio: command == nil ? audio : nil,
            text: command
        )
    }

    public static func encode(_ message: InvokeMessage) throws -> Data {
        try JSONEncoder.wire.encode(message)
    }

    public static func decode(_ data: Data) throws -> ServerEvent {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String
        else {
            throw ContractError.badJSON
        }
        switch type {
        case "status":
            return .status(try JSONDecoder.wire.decode(StatusMessage.self, from: data))
        case "card":
            return .card(try JSONDecoder.wire.decode(CardMessage.self, from: data))
        case "error":
            return .error(try JSONDecoder.wire.decode(ErrorMessage.self, from: data))
        default:
            throw ContractError.wrongType(type)
        }
    }
}

extension InvokeMessage: Codable {
    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case sessionId = "session_id"
        case frame
        case audio
        case text
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(requestId, forKey: .requestId)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(frame, forKey: .frame)
        if let audio {
            try container.encode(audio, forKey: .audio)
        } else {
            try container.encodeNil(forKey: .audio)
        }
        if let text {
            try container.encode(text, forKey: .text)
        } else {
            try container.encodeNil(forKey: .text)
        }
    }
}

extension CardMessage: Codable {
    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case title
        case caption
        case imageURL = "image_url"
        case speechText = "speech_text"
        case audioURL = "audio_url"
        case book
        case sources
        case models
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decodeIfPresent(String.self, forKey: .type) ?? "card"
        requestId = try container.decode(String.self, forKey: .requestId)
        title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
        caption = try container.decodeIfPresent(String.self, forKey: .caption) ?? ""
        imageURL = try container.decodeIfPresent(String.self, forKey: .imageURL)
        speechText = try container.decodeIfPresent(String.self, forKey: .speechText) ?? ""
        audioURL = try container.decodeIfPresent(String.self, forKey: .audioURL)
        book = try container.decodeIfPresent(BookLocation.self, forKey: .book)
        sources = try container.decodeIfPresent([SourceCitation].self, forKey: .sources) ?? []
        models = try container.decodeIfPresent(ModelTrace.self, forKey: .models) ?? ModelTrace()
    }
}

extension ErrorMessage: Codable {
    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case code
        case message
        case retryable
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decodeIfPresent(String.self, forKey: .type) ?? "error"
        requestId = try container.decode(String.self, forKey: .requestId)
        let raw = try container.decode(String.self, forKey: .code)
        rawCode = raw
        code = ServerErrorCode(rawValue: raw) ?? .internalError
        message = try container.decodeIfPresent(String.self, forKey: .message) ?? ""
        retryable = try container.decodeIfPresent(Bool.self, forKey: .retryable) ?? false
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(requestId, forKey: .requestId)
        try container.encode(rawCode, forKey: .code)
        try container.encode(message, forKey: .message)
        try container.encode(retryable, forKey: .retryable)
    }
}

extension JSONEncoder {
    static var wire: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

extension JSONDecoder {
    static var wire: JSONDecoder {
        JSONDecoder()
    }
}
