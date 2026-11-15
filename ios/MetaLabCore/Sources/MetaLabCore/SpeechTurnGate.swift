import Foundation

/// Tracks which utterance currently owns the speech continuation.
///
/// Speech-engine callbacks arrive asynchronously, so a cancel or finish for an utterance
/// that was already stopped can land after the next one has started.
public struct SpeechTurnGate<ID: Hashable & Sendable>: Sendable {
    public private(set) var current: ID?

    public init() {}

    public mutating func begin(_ id: ID) {
        current = id
    }

    /// True only when `id` is the utterance in progress; that turn then ends.
    public mutating func end(_ id: ID) -> Bool {
        guard current == id else { return false }
        current = nil
        return true
    }

    /// Ends the turn without waiting for the engine's callback, which will then be stale.
    @discardableResult
    public mutating func abandon() -> ID? {
        let previous = current
        current = nil
        return previous
    }
}
