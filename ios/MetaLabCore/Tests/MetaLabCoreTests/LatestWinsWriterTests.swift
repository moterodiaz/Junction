import XCTest
@testable import MetaLabCore

@MainActor
final class LatestWinsWriterTests: XCTestCase {
    func testAStalePushIsSkippedOnceANewerOneIsIssued() async {
        let sink = FakeSink()
        sink.hold = true
        let writer = LatestWinsWriter<String> { [sink] item in await sink.write(item) }
        writer.submit("Reading")
        await until { sink.started == ["Reading"] }
        writer.submit("Thinking")
        writer.submit("Card")
        sink.hold = false
        sink.releaseAll()
        await until { writer.isIdle }
        XCTAssertEqual(sink.started, ["Reading", "Card"])
        XCTAssertEqual(sink.maxConcurrent, 1)
    }

    func testCancelPendingDropsWhatIsNotYetWritten() async {
        let sink = FakeSink()
        sink.hold = true
        let writer = LatestWinsWriter<String> { [sink] item in await sink.write(item) }
        writer.submit("Card")
        await until { sink.started == ["Card"] }
        writer.submit("Error")
        writer.cancelPending()
        sink.hold = false
        sink.releaseAll()
        await until { writer.isIdle }
        XCTAssertEqual(sink.started, ["Card"])
    }

    func testWritesStaySerialAndEachSubmissionAdvancesTheGeneration() async {
        let sink = FakeSink()
        let writer = LatestWinsWriter<String> { [sink] item in await sink.write(item) }
        XCTAssertEqual(writer.submit("a"), 1)
        await until { writer.isIdle }
        XCTAssertEqual(writer.submit("b"), 2)
        await until { writer.isIdle }
        XCTAssertEqual(sink.started, ["a", "b"])
        XCTAssertEqual(sink.maxConcurrent, 1)
    }

    func testAStalledWriteDoesNotBlockLaterOnesPastTheTimeout() async {
        let sink = FakeSink()
        sink.hold = true
        let writer = LatestWinsWriter<String>(writeTimeout: .milliseconds(100)) { [sink] item in
            await sink.write(item)
        }
        writer.submit("Thinking")
        await until { sink.started == ["Thinking"] }
        sink.hold = false
        writer.submit("Card")
        await until { sink.started.contains("Card") }
        XCTAssertEqual(sink.started, ["Thinking", "Card"])
        sink.releaseAll()
    }

    private func until(_ condition: @MainActor () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = ContinuousClock.now + .seconds(3)
        while !condition() {
            if ContinuousClock.now > deadline {
                XCTFail("condition not met in time", file: file, line: line)
                return
            }
            try? await Task.sleep(for: .milliseconds(5))
        }
    }
}

@MainActor
private final class FakeSink {
    var hold = false
    private(set) var started: [String] = []
    private(set) var maxConcurrent = 0
    private var running = 0
    private var held: [CheckedContinuation<Void, Never>] = []

    func write(_ item: String) async {
        started.append(item)
        running += 1
        maxConcurrent = max(maxConcurrent, running)
        if hold {
            await withCheckedContinuation { held.append($0) }
        } else {
            await Task.yield()
        }
        running -= 1
    }

    func releaseAll() {
        let waiting = held
        held = []
        waiting.forEach { $0.resume() }
    }
}
