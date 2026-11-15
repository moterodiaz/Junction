import XCTest
@testable import MetaLabCore

final class ReplyGateTests: XCTestCase {
    func testAFastReplyWhileTheSendIsStillInFlightIsKept() {
        XCTAssertTrue(ReplyGate.acceptsReply(phase: .capturing, fromSocket: 3, activeSocket: 3))
        XCTAssertTrue(ReplyGate.acceptsReply(phase: .waiting, fromSocket: 3, activeSocket: 3))
        XCTAssertTrue(ReplyGate.acceptsReply(phase: .speaking, fromSocket: 3, activeSocket: 3))
    }

    func testRepliesFromAnotherSocketOrWhenIdleAreDropped() {
        XCTAssertFalse(ReplyGate.acceptsReply(phase: .capturing, fromSocket: 2, activeSocket: 3))
        XCTAssertFalse(ReplyGate.acceptsReply(phase: .capturing, fromSocket: 3, activeSocket: nil))
        XCTAssertFalse(ReplyGate.acceptsReply(phase: .idle, fromSocket: 3, activeSocket: 3))
    }

    func testADisconnectBeforeTheSendReturnsFailsTheRequest() {
        XCTAssertTrue(ReplyGate.failsOnDisconnect(phase: .capturing, fromSocket: 3, activeSocket: 3))
        XCTAssertTrue(ReplyGate.failsOnDisconnect(phase: .waiting, fromSocket: 3, activeSocket: 3))
        XCTAssertFalse(ReplyGate.failsOnDisconnect(phase: .speaking, fromSocket: 3, activeSocket: 3))
        XCTAssertFalse(ReplyGate.failsOnDisconnect(phase: .idle, fromSocket: 3, activeSocket: 3))
        XCTAssertFalse(ReplyGate.failsOnDisconnect(phase: .capturing, fromSocket: 2, activeSocket: 3))
        XCTAssertFalse(ReplyGate.failsOnDisconnect(phase: .capturing, fromSocket: 3, activeSocket: nil))
    }

    func testACardThatBeatTheSendIsNotPushedBackToWaiting() {
        XCTAssertTrue(ReplyGate.entersWaitingAfterSend(phase: .capturing, requestId: "r1", activeRequest: "r1"))
        XCTAssertFalse(ReplyGate.entersWaitingAfterSend(phase: .speaking, requestId: "r1", activeRequest: "r1"))
        XCTAssertFalse(ReplyGate.entersWaitingAfterSend(phase: .idle, requestId: "r1", activeRequest: nil))
        XCTAssertFalse(ReplyGate.entersWaitingAfterSend(phase: .capturing, requestId: "r1", activeRequest: "r2"))
    }
}

final class SpeechTurnGateTests: XCTestCase {
    func testAStaleCancelCannotEndTheNextUtterance() {
        var turns = SpeechTurnGate<Int>()
        turns.begin(1)
        XCTAssertEqual(turns.abandon(), 1)
        turns.begin(2)
        XCTAssertFalse(turns.end(1), "late didCancel for the stopped utterance")
        XCTAssertEqual(turns.current, 2)
        XCTAssertTrue(turns.end(2))
        XCTAssertNil(turns.current)
    }

    func testAnUtteranceEndsOnlyOnce() {
        var turns = SpeechTurnGate<Int>()
        turns.begin(7)
        XCTAssertTrue(turns.end(7))
        XCTAssertFalse(turns.end(7))
    }
}

final class CaptureGateTests: XCTestCase {
    func testFirstOutcomeWinsAndCleanupRunsOnce() async throws {
        let gate = CaptureGate<Int>()
        let count = Counter()
        gate.onFinish { count.bump() }
        XCTAssertTrue(gate.succeed(1))
        XCTAssertFalse(gate.succeed(2))
        XCTAssertFalse(gate.fail(URLError(.timedOut)))
        let value = try await gate.value(timeout: .seconds(5), timeoutError: URLError(.timedOut))
        XCTAssertEqual(value, 1)
        XCTAssertEqual(count.value, 1)
    }

    func testCleanupAddedAfterTheOutcomeRunsImmediately() {
        let gate = CaptureGate<Int>()
        gate.fail(URLError(.cancelled))
        let count = Counter()
        gate.onFinish { count.bump() }
        XCTAssertEqual(count.value, 1)
    }

    func testAResultDeliveredWhileWaitingResumesTheWaiter() async throws {
        let gate = CaptureGate<String>()
        let removed = Counter()
        gate.onFinish { removed.bump() }
        Task {
            try? await Task.sleep(for: .milliseconds(50))
            gate.succeed("jpeg")
        }
        let value = try await gate.value(timeout: .seconds(5), timeoutError: URLError(.timedOut))
        XCTAssertEqual(value, "jpeg")
        XCTAssertEqual(removed.value, 1)
    }

    func testTimeoutFailsAndRunsCleanup() async {
        let gate = CaptureGate<Int>()
        let removed = Counter()
        gate.onFinish { removed.bump() }
        do {
            _ = try await gate.value(timeout: .milliseconds(50), timeoutError: URLError(.timedOut))
            XCTFail("expected a timeout")
        } catch let error as URLError {
            XCTAssertEqual(error.code, .timedOut)
        } catch {
            XCTFail("unexpected \(error)")
        }
        XCTAssertEqual(removed.value, 1)
    }

    func testCancellingTheTaskEndsTheWaitWithoutTheTimeout() async {
        let gate = CaptureGate<Int>()
        let removed = Counter()
        gate.onFinish { removed.bump() }
        let started = ContinuousClock.now
        let waiter = Task {
            try await gate.value(timeout: .seconds(20), timeoutError: URLError(.timedOut))
        }
        try? await Task.sleep(for: .milliseconds(50))
        waiter.cancel()
        let result = await waiter.result
        XCTAssertLessThan(ContinuousClock.now - started, .seconds(5))
        switch result {
        case .success:
            XCTFail("expected cancellation")
        case .failure(let error):
            XCTAssertTrue(error is CancellationError, "got \(error)")
        }
        XCTAssertEqual(removed.value, 1)
        XCTAssertTrue(gate.isFinished)
    }

    func testCancelledBeforeAwaitingStillThrows() async {
        let gate = CaptureGate<Int>()
        let started = ContinuousClock.now
        let waiter = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await gate.value(timeout: .seconds(20), timeoutError: URLError(.timedOut))
        }
        let result = await waiter.result
        XCTAssertLessThan(ContinuousClock.now - started, .seconds(1))
        switch result {
        case .success:
            XCTFail("expected cancellation")
        case .failure(let error):
            XCTAssertTrue(error is CancellationError, "got \(error)")
        }
    }

    func testSuccessStopsTheTimeoutTimer() async throws {
        let gate = CaptureGate<Int>()
        gate.succeed(5)
        let value = try await gate.value(timeout: .milliseconds(50), timeoutError: URLError(.timedOut))
        XCTAssertEqual(value, 5)
        try await Task.sleep(for: .milliseconds(250))
        XCTAssertEqual(gate.ignoredOutcomeCount, 0, "the timeout timer fired after the capture finished")
    }

    @MainActor
    func testUsableFromTheMainActorLikeTheGlassesBridge() async throws {
        let gate = CaptureGate<Data>()
        Task { @MainActor in gate.succeed(Data([1, 2])) }
        let data = try await gate.value(timeout: .seconds(5), timeoutError: URLError(.timedOut))
        XCTAssertEqual(data, Data([1, 2]))
    }
}

private final class Counter: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return count
    }

    func bump() {
        lock.lock()
        count += 1
        lock.unlock()
    }
}
