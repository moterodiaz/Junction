import Foundation

/// A one-shot result fed by listener callbacks, with cleanup that runs exactly once.
///
/// Callbacks may succeed or fail it before `value` is awaited; the first outcome wins and later
/// ones are ignored. Cleanups registered with `onFinish` run as soon as an outcome is set, or
/// immediately when registered after that, so listeners never outlive the capture.
public final class CaptureGate<Value: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Value, Error>?
    private var outcome: Result<Value, Error>?
    private var cleanups: [@Sendable () -> Void] = []

    public init() {}

    public var isFinished: Bool {
        lock.lock()
        defer { lock.unlock() }
        return outcome != nil
    }

    public func onFinish(_ cleanup: @escaping @Sendable () -> Void) {
        lock.lock()
        if outcome == nil {
            cleanups.append(cleanup)
            lock.unlock()
            return
        }
        lock.unlock()
        cleanup()
    }

    @discardableResult
    public func succeed(_ value: Value) -> Bool {
        finish(.success(value))
    }

    @discardableResult
    public func fail(_ error: any Error) -> Bool {
        finish(.failure(error))
    }

    /// Await at most once. Task cancellation ends the wait with `CancellationError` right away.
    public func value(timeout: Duration, timeoutError: any Error & Sendable) async throws -> Value {
        let timer = Task { [self] in
            try? await Task.sleep(for: timeout)
            guard !Task.isCancelled else { return }
            fail(timeoutError)
        }
        onFinish { timer.cancel() }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Value, Error>) in
                arm(continuation)
            }
        } onCancel: { [self] in
            fail(CancellationError())
        }
    }

    private func arm(_ waiting: CheckedContinuation<Value, Error>) {
        lock.lock()
        if let outcome {
            lock.unlock()
            waiting.resume(with: outcome)
            return
        }
        continuation = waiting
        lock.unlock()
    }

    private func finish(_ result: Result<Value, Error>) -> Bool {
        lock.lock()
        guard outcome == nil else {
            lock.unlock()
            return false
        }
        outcome = result
        let waiting = continuation
        continuation = nil
        let pending = cleanups
        cleanups = []
        lock.unlock()
        waiting?.resume(with: result)
        pending.forEach { $0() }
        return true
    }
}
