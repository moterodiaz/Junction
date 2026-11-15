import Foundation

/// Serial, latest-wins delivery to a slow sink such as the glasses display.
///
/// At most one write runs at a time. While one is in flight, newer submissions replace any
/// pending item, so a superseded item is never written. Callers never wait on the sink.
/// A write that takes longer than `writeTimeout` is left to finish on its own and the next
/// pending item goes out, so one stalled write cannot block every later one.
@MainActor
public final class LatestWinsWriter<Item: Sendable> {
    public private(set) var generation = 0
    public var isIdle: Bool { !draining }

    private var pending: (item: Item, generation: Int)?
    private var draining = false
    private let writeTimeout: Duration?
    private let write: @MainActor @Sendable (Item) async -> Void

    public init(writeTimeout: Duration? = nil, write: @escaping @MainActor @Sendable (Item) async -> Void) {
        self.writeTimeout = writeTimeout
        self.write = write
    }

    @discardableResult
    public func submit(_ item: Item) -> Int {
        generation += 1
        pending = (item, generation)
        if !draining {
            draining = true
            Task { await self.drain() }
        }
        return generation
    }

    /// Drops anything not yet written. A write already in flight cannot be recalled.
    public func cancelPending() {
        generation += 1
        pending = nil
    }

    private func drain() async {
        while let next = pending {
            pending = nil
            guard next.generation == generation else { continue }
            await perform(next.item)
        }
        draining = false
    }

    private func perform(_ item: Item) async {
        guard let writeTimeout else {
            await write(item)
            return
        }
        let done = CaptureGate<Bool>()
        let write = self.write
        Task { @MainActor in
            await write(item)
            done.succeed(true)
        }
        _ = try? await done.value(timeout: writeTimeout, timeoutError: WriteTimedOut())
    }

    private struct WriteTimedOut: Error {}
}
