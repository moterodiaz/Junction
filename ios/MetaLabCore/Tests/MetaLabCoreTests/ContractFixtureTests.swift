import Foundation
import XCTest
@testable import MetaLabCore

/// Decodes the shared server-message fixtures in `contracts/fixtures/` and checks which replies
/// the phone accepts for the request it is waiting on.
final class ContractFixtureTests: XCTestCase {
    func testEveryValidServerFixtureDecodesAsItsType() throws {
        let names = try fixtureNames(in: "valid").filter { !$0.hasPrefix("invoke") }
        XCTAssertFalse(names.isEmpty)
        for name in names {
            let data = try fixture("valid", name)
            let event = try Contract.decode(data)
            let type = try XCTUnwrap(jsonObject(data)["type"] as? String)
            switch event {
            case .status: XCTAssertEqual(type, "status", name)
            case .card: XCTAssertEqual(type, "card", name)
            case .error: XCTAssertEqual(type, "error", name)
            }
        }
    }

    func testNullRequestIdErrorDecodesAndRoundTrips() throws {
        guard case .error(let error) = try Contract.decode(fixture("valid", "error-null-request-id.json")) else {
            return XCTFail("expected an error event")
        }
        XCTAssertNil(error.requestId)
        XCTAssertEqual(error.code, .internalError)
        XCTAssertFalse(error.retryable)
        let encoded = try jsonObject(JSONEncoder().encode(error))
        XCTAssertTrue(encoded.keys.contains("request_id"))
        XCTAssertTrue(encoded["request_id"] is NSNull)
    }

    func testMalformedServerMessagesAreRejected() throws {
        for name in ["status-invalid-stage.json", "error-non-boolean-retryable.json", "unknown-message-type.json"] {
            XCTAssertThrowsError(try Contract.decode(fixture("invalid", name)), name)
        }
        XCTAssertThrowsError(try Contract.decode(Data("not json".utf8)))
        XCTAssertThrowsError(try Contract.decode(Data(#"{"request_id":"r"}"#.utf8)))
    }

    func testLenientDecodingKeepsUnknownErrorCodesAndMissingBook() throws {
        guard case .error(let error) = try Contract.decode(fixture("invalid", "error-invalid-code.json")) else {
            return XCTFail("expected an error event")
        }
        XCTAssertEqual(error.code, .internalError)
        XCTAssertEqual(error.rawCode, "bad_gateway")
        guard case .card(let card) = try Contract.decode(fixture("invalid", "card-missing-book.json")) else {
            return XCTFail("expected a card event")
        }
        XCTAssertNil(card.book)
    }

    func testOnlyRepliesForTheActiveRequestAreAccepted() {
        let status = ServerEvent.status(StatusMessage(requestId: "new", stage: .reading))
        let stale = ServerEvent.card(card(requestId: "old"))
        let current = ServerEvent.card(card(requestId: "new"))
        let staleError = ServerEvent.error(ErrorMessage(requestId: "old", code: .modelTimeout, message: "m", retryable: true))
        let unparsed = ServerEvent.error(ErrorMessage(requestId: nil, code: .internalError, message: "m", retryable: false))

        XCTAssertTrue(ResponseFilter.belongs(status, to: "new"))
        XCTAssertTrue(ResponseFilter.belongs(current, to: "new"))
        XCTAssertFalse(ResponseFilter.belongs(stale, to: "new"))
        XCTAssertFalse(ResponseFilter.belongs(staleError, to: "new"))
        XCTAssertTrue(ResponseFilter.belongs(unparsed, to: "new"))
        for event in [status, current, unparsed] {
            XCTAssertFalse(ResponseFilter.belongs(event, to: nil), "nothing is accepted while idle")
        }
    }

    func testRepeatedInvocationsOnlyAcceptTheNewestRequest() {
        var active: String? = "first"
        let firstCard = ServerEvent.card(card(requestId: "first"))
        XCTAssertTrue(ResponseFilter.belongs(firstCard, to: active))
        active = "second"
        XCTAssertFalse(ResponseFilter.belongs(firstCard, to: active))
        XCTAssertTrue(ResponseFilter.belongs(.card(card(requestId: "second")), to: active))
        active = nil
        XCTAssertFalse(ResponseFilter.belongs(.card(card(requestId: "second")), to: active))
    }

    func testRepliesFromAnOlderSocketAreDropped() {
        let nullError = ServerEvent.error(ErrorMessage(requestId: nil, code: .internalError, message: "m", retryable: false))
        // The previous socket (1) queued a null-id error; the new request runs on socket 2.
        XCTAssertFalse(ResponseFilter.accepts(nullError, fromSocket: 1, activeSocket: 2, activeRequest: "second"))
        XCTAssertFalse(ResponseFilter.accepts(nullError, fromSocket: 1, activeSocket: nil, activeRequest: nil))
        XCTAssertFalse(ResponseFilter.accepts(.card(card(requestId: "second")), fromSocket: 1, activeSocket: 2, activeRequest: "second"))
        // A null-id error from the current socket still works.
        XCTAssertTrue(ResponseFilter.accepts(nullError, fromSocket: 2, activeSocket: 2, activeRequest: "second"))
    }

    private func card(requestId: String) -> CardMessage {
        CardMessage(
            requestId: requestId, title: "T", caption: "C", imageURL: nil, speechText: "S",
            audioURL: nil, book: nil, sources: [], models: ModelTrace()
        )
    }

    private var fixturesRoot: URL {
        // Tests/MetaLabCoreTests/ -> MetaLabCore -> ios -> repository root.
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("contracts/fixtures", isDirectory: true)
    }

    private func fixtureNames(in folder: String) throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: fixturesRoot.appendingPathComponent(folder).path)
            .filter { $0.hasSuffix(".json") }
            .sorted()
    }

    private func fixture(_ folder: String, _ name: String) throws -> Data {
        try Data(contentsOf: fixturesRoot.appendingPathComponent(folder).appendingPathComponent(name))
    }

    private func jsonObject(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}
