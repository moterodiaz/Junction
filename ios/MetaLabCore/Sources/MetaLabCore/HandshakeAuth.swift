import Foundation

/// Bearer credential for the optional `/ws` handshake auth (contracts/LIFECYCLE.md, "Optional auth
/// handoff"). Auth is off on the server by default, so a missing credential is the normal case.
/// The value never appears in a description, a debugger dump or a log line.
public struct HandshakeCredential: Equatable, Sendable, CustomStringConvertible, CustomDebugStringConvertible,
    CustomReflectable {
    public static let defaultsKey = "metalab.wsAuthToken"

    fileprivate let value: String

    /// Nil when empty, or when the value cannot travel in an HTTP header as one token
    /// (inner whitespace, control characters, non-ASCII).
    public init?(_ raw: String?) {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty,
              trimmed.unicodeScalars.allSatisfy({ $0.value > 0x20 && $0.value < 0x7F })
        else { return nil }
        value = trimmed
    }

    /// Read-only: the app never writes this key. Supply it as a launch argument
    /// (`-metalab.wsAuthToken <value>`), which lives only in the volatile argument domain, so no
    /// credential is stored on the phone or committed to the repository.
    public init?(defaults: UserDefaults) {
        self.init(defaults.string(forKey: Self.defaultsKey))
    }

    public var description: String { "HandshakeCredential(redacted)" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: KeyValuePairs<String, Any>()) }
}

/// What the handshake does with the configured credential.
public enum HandshakeAuthorization: Equatable, Sendable {
    /// No credential configured: the legacy, auth-off handshake.
    case none
    /// `Authorization: Bearer <credential>` on a `wss://` handshake.
    case bearer
    /// A credential is configured but the URL is `ws://`. It is never sent in clear; an auth-off
    /// server still accepts the handshake, an auth-on server refuses it (it requires WSS anyway).
    case withheldInsecure
}

/// The request that opens one `/ws` socket. The URL is used as configured; the credential travels
/// only in the `Authorization` header, never in the URL, a subprotocol value or a JSON message.
public struct HandshakePlan: Sendable {
    public let url: URL
    public let authorization: HandshakeAuthorization
    private let headerValue: String?

    public init(config: BackendConfig, credential: HandshakeCredential?) {
        url = config.webSocketURL
        guard let credential else {
            authorization = .none
            headerValue = nil
            return
        }
        if url.scheme?.lowercased() == "wss" {
            authorization = .bearer
            headerValue = "Bearer \(credential.value)"
        } else {
            authorization = .withheldInsecure
            headerValue = nil
        }
    }

    /// Subprotocols offered at the handshake. Empty: the phone stays on legacy messages until the
    /// runtime can honor every `metalab.v2` rule.
    public var offeredSubprotocols: [String] { ProtocolNegotiation.clientOffers }

    public var urlRequest: URLRequest {
        var request = URLRequest(url: url)
        if let headerValue {
            request.setValue(headerValue, forHTTPHeaderField: "Authorization")
        }
        return request
    }
}

/// The server refused the handshake with a bare HTTP status (401 when auth is on and the
/// credential is missing or wrong, 503 at the connection cap). No application frame follows.
public struct HandshakeRefusal: Error, Equatable, Sendable {
    public let httpStatus: Int

    /// Nil when there is no HTTP status or the status is not a refusal.
    public init?(httpStatus: Int?) {
        guard let httpStatus, httpStatus >= 400, httpStatus < 600 else { return nil }
        self.httpStatus = httpStatus
    }

    public var retryable: Bool { httpStatus >= 500 }

    public var banner: String {
        switch httpStatus {
        case 401, 403:
            return "The backend refused this phone. Check the backend access token."
        case 500...:
            return "The backend is busy. Try again in a moment."
        default:
            return "The backend refused the connection."
        }
    }
}
