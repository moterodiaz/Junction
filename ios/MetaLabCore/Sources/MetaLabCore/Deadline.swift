import Foundation

public struct Deadline: Equatable, Sendable {
    public var overallSeconds: Double
    public var idleSeconds: Double

    public init(overallSeconds: Double = 90, idleSeconds: Double = 30) {
        self.overallSeconds = overallSeconds
        self.idleSeconds = idleSeconds
    }

    public static let demo = Deadline()

    /// Image generation is slow. Any server message resets the idle clock.
    /// The overall cap still fires so a stuck socket cannot hang the glasses.
    public func isTimedOut(elapsed: Double, sinceLastServerMessage: Double) -> Bool {
        elapsed >= overallSeconds || sinceLastServerMessage >= idleSeconds
    }
}
