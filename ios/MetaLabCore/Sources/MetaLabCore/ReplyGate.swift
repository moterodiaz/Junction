import Foundation

/// Where the phone is in one question.
public enum ClientPhase: Equatable, Sendable {
    case idle
    case capturing
    case waiting
    case speaking
}

/// Decides which socket events still matter for the request in flight.
///
/// The socket is opened while the phone is still `.capturing` and `send` has not returned,
/// so a fast reply or an immediate disconnect can arrive before the phase becomes `.waiting`.
public enum ReplyGate {
    public static func acceptsReply(phase: ClientPhase, fromSocket socket: Int, activeSocket: Int?) -> Bool {
        guard let activeSocket, socket == activeSocket else { return false }
        return phase != .idle
    }

    /// A disconnect while speaking is expected: the card is already in hand.
    public static func failsOnDisconnect(phase: ClientPhase, fromSocket socket: Int, activeSocket: Int?) -> Bool {
        guard let activeSocket, socket == activeSocket else { return false }
        return phase == .capturing || phase == .waiting
    }

    /// A card or error may have landed while `send` was suspended; it must not be pushed back to `.waiting`.
    public static func entersWaitingAfterSend(phase: ClientPhase, requestId: String, activeRequest: String?) -> Bool {
        phase == .capturing && activeRequest == requestId
    }
}
