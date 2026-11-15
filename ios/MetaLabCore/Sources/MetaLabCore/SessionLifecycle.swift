import Foundation

/// The phone's side of one book session (contracts/LIFECYCLE.md, "Expiry and application retention").
///
/// The deadline is the last invocation the phone sent plus the contract's 900 seconds, on a
/// monotonic clock that keeps counting while the phone sleeps. The phone sends before the server
/// accepts, so this deadline never runs past the server's: it is a conservative local retention
/// bound, not proof that the server expired or cleaned up anything.
public struct ClientSession: Equatable, Sendable {
    public static let retention: Duration = .seconds(900)

    public private(set) var id: String
    /// Bumped on every end, reset or expiry; work tagged with an older generation is stale.
    public private(set) var generation: Int
    public private(set) var deadline: ContinuousClock.Instant

    /// Creation anchors an empty session.
    public init(id: String, now: ContinuousClock.Instant) {
        self.id = id
        generation = 0
        deadline = now + Self.retention
    }

    public func isExpired(at now: ContinuousClock.Instant) -> Bool {
        now >= deadline
    }

    public func owns(generation other: Int) -> Bool {
        generation == other
    }

    /// Only an invocation the phone actually sends moves the deadline; replies, reconnects and
    /// failures do not. An expired session is never refreshed: this returns false and the caller
    /// resets first.
    @discardableResult
    public mutating func recordInvocation(at now: ContinuousClock.Instant) -> Bool {
        guard !isExpired(at: now) else { return false }
        deadline = now + Self.retention
        return true
    }

    /// End, reset or expiry. A deleted session id is never reused, so `newId` must be fresh.
    @discardableResult
    public mutating func reset(to newId: String, at now: ContinuousClock.Instant) -> Bool {
        guard newId != id, !newId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        id = newId
        generation += 1
        deadline = now + Self.retention
        return true
    }
}

extension PhoneSession {
    /// Drops what the ended session produced: the last card and any banner about its requests.
    /// The glasses link, permission, registration, display toggle and glasses-recovery banners
    /// belong to the phone, not to the book session, and stay.
    public func endingBookSession() -> PhoneSession {
        var next = self
        next.lastCard = nil
        if next.action == .retryInvoke || next.action == .none {
            next.banner = nil
            next.actionTitle = nil
            next.action = .none
        }
        return next
    }
}

/// `metalab.v2` subprotocol negotiation, as the client sees the handshake.
public enum ProtocolNegotiation {
    public static let v2 = "metalab.v2"
    /// The phone offers nothing yet: no backend selects v2, and lifecycle controls are allowed only
    /// after a successful upgrade that selected exactly `metalab.v2`.
    public static let clientOffers: [String] = []

    public struct Outcome: Equatable, Sendable {
        /// The socket may carry legacy messages.
        public var usable: Bool
        /// Lifecycle controls (`cancel`, `session_end`) may be sent and lifecycle replies accepted.
        public var lifecycleControls: Bool

        public init(usable: Bool, lifecycleControls: Bool) {
            self.usable = usable
            self.lifecycleControls = lifecycleControls
        }
    }

    /// A selection the client did not offer, or any selection other than `metalab.v2`, makes the
    /// socket unusable. Offering alone never negotiates.
    public static func evaluate(offered: [String], selected: String?, upgraded: Bool) -> Outcome {
        guard upgraded else { return Outcome(usable: false, lifecycleControls: false) }
        let chosen = (selected?.isEmpty == false) ? selected : nil
        if let chosen, chosen != v2 || !offered.contains(chosen) {
            return Outcome(usable: false, lifecycleControls: false)
        }
        return Outcome(usable: true, lifecycleControls: chosen == v2)
    }
}

public enum LifecycleErrorCode: String, Equatable, Sendable, CaseIterable {
    case unknownRequest = "unknown_request"
    case sessionUnavailable = "session_unavailable"
    case sessionMismatch = "session_mismatch"
    case duplicateRequest = "duplicate_request"
}

/// Server-to-client messages of `ws-lifecycle.schema.json`. Kept apart from `ServerEvent` so the
/// legacy decoder never accepts them.
public enum LifecycleEvent: Equatable, Sendable {
    case cancelled(requestId: String, sessionId: String)
    /// Sent only after cleanup completed (`cleanup: "complete"`).
    case sessionEnded(requestId: String, sessionId: String)
    case lifecycleError(requestId: String, sessionId: String, code: LifecycleErrorCode)
}

/// Client-to-server lifecycle controls.
public enum LifecycleControl: Equatable, Sendable {
    /// Targets one invocation by its existing request id.
    case cancel(requestId: String, sessionId: String)
    /// `requestId` is a fresh end-control id, distinct from every invocation id.
    case sessionEnd(requestId: String, sessionId: String)
}

public enum LifecycleContractError: Error, Equatable, Sendable {
    case notNegotiated
    case badJSON
    case wrongType(String)
    case wrongDirection(String)
    case invalidField(String)
    case unexpectedField(String)
}

public enum LifecycleContract {
    private static let serverTypes: Set<String> = ["cancelled", "session_ended", "lifecycle_error"]
    private static let clientTypes: Set<String> = ["cancel", "session_end"]

    /// Strict: exact fields, nonblank ids. Throws `notNegotiated` on a legacy connection, where a
    /// lifecycle message is never valid.
    public static func decode(_ data: Data, negotiated: Bool) throws -> LifecycleEvent {
        guard negotiated else { throw LifecycleContractError.notNegotiated }
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String
        else { throw LifecycleContractError.badJSON }
        if clientTypes.contains(type) { throw LifecycleContractError.wrongDirection(type) }
        guard serverTypes.contains(type) else { throw LifecycleContractError.wrongType(type) }

        var expected: Set<String> = ["type", "request_id", "session_id"]
        if type == "session_ended" { expected.insert("cleanup") }
        if type == "lifecycle_error" { expected.insert("code") }
        if let extra = Set(object.keys).subtracting(expected).sorted().first {
            throw LifecycleContractError.unexpectedField(extra)
        }
        let requestId = try id(object, "request_id")
        let sessionId = try id(object, "session_id")
        switch type {
        case "cancelled":
            return .cancelled(requestId: requestId, sessionId: sessionId)
        case "session_ended":
            guard object["cleanup"] as? String == "complete" else {
                throw LifecycleContractError.invalidField("cleanup")
            }
            return .sessionEnded(requestId: requestId, sessionId: sessionId)
        default:
            guard let raw = object["code"] as? String, let code = LifecycleErrorCode(rawValue: raw) else {
                throw LifecycleContractError.invalidField("code")
            }
            return .lifecycleError(requestId: requestId, sessionId: sessionId, code: code)
        }
    }

    public static func encode(_ control: LifecycleControl, negotiated: Bool) throws -> Data {
        guard negotiated else { throw LifecycleContractError.notNegotiated }
        let (type, requestId, sessionId): (String, String, String)
        switch control {
        case .cancel(let request, let session): (type, requestId, sessionId) = ("cancel", request, session)
        case .sessionEnd(let request, let session): (type, requestId, sessionId) = ("session_end", request, session)
        }
        guard isID(requestId) else { throw LifecycleContractError.invalidField("request_id") }
        guard isID(sessionId) else { throw LifecycleContractError.invalidField("session_id") }
        let object = ["type": type, "request_id": requestId, "session_id": sessionId]
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
    }

    private static func id(_ object: [String: Any], _ key: String) throws -> String {
        guard let value = object[key] as? String, isID(value) else {
            throw LifecycleContractError.invalidField(key)
        }
        return value
    }

    private static func isID(_ value: String) -> Bool {
        value.contains { !$0.isWhitespace }
    }
}
