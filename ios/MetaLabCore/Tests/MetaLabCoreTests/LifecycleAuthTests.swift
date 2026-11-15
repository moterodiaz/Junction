import Foundation
import XCTest
@testable import MetaLabCore

/// Session lifecycle and optional handshake auth (contracts/LIFECYCLE.md), driven by the shared
/// fixtures in `contracts/`.
final class LifecycleAuthTests: XCTestCase {
    // MARK: Lifecycle messages

    func testValidLifecycleFixturesDecodeOnlyInTheServerDirectionAndOnlyOnV2() throws {
        let names = try jsonNames(in: "fixtures/lifecycle/valid")
        XCTAssertEqual(names.count, 5)
        var decoded = Set<String>()
        for name in names {
            let data = try contract("fixtures/lifecycle/valid/\(name)")
            let type = try XCTUnwrap(jsonObject(data)["type"] as? String)
            XCTAssertThrowsError(try LifecycleContract.decode(data, negotiated: false), name) { error in
                XCTAssertEqual(error as? LifecycleContractError, .notNegotiated)
            }
            XCTAssertThrowsError(try Contract.decode(data), "the legacy decoder never accepts \(name)")
            if type == "cancel" || type == "session_end" {
                XCTAssertThrowsError(try LifecycleContract.decode(data, negotiated: true), name) { error in
                    XCTAssertEqual(error as? LifecycleContractError, .wrongDirection(type))
                }
            } else {
                _ = try LifecycleContract.decode(data, negotiated: true)
                decoded.insert(type)
            }
        }
        XCTAssertEqual(decoded, ["cancelled", "session_ended", "lifecycle_error"])
        XCTAssertEqual(
            try LifecycleContract.decode(contract("fixtures/lifecycle/valid/session-ended.json"), negotiated: true),
            .sessionEnded(requestId: "end-a", sessionId: "session-a")
        )
        XCTAssertEqual(
            try LifecycleContract.decode(contract("fixtures/lifecycle/valid/lifecycle-error.json"), negotiated: true),
            .lifecycleError(requestId: "req-a", sessionId: "session-a", code: .sessionUnavailable)
        )
    }

    func testEveryInvalidLifecycleFixtureIsRejected() throws {
        let names = try jsonNames(in: "fixtures/lifecycle/invalid")
        XCTAssertFalse(names.isEmpty)
        for name in names {
            let data = try contract("fixtures/lifecycle/invalid/\(name)")
            XCTAssertThrowsError(try LifecycleContract.decode(data, negotiated: true), name)
        }
    }

    func testControlsEncodeExactlyLikeTheFixturesAndNeedV2() throws {
        let cancel = LifecycleControl.cancel(requestId: "req-a", sessionId: "session-a")
        let end = LifecycleControl.sessionEnd(requestId: "end-a", sessionId: "session-a")
        XCTAssertEqual(
            try jsonObject(LifecycleContract.encode(cancel, negotiated: true)) as NSDictionary,
            try jsonObject(contract("fixtures/lifecycle/valid/cancel.json")) as NSDictionary
        )
        XCTAssertEqual(
            try jsonObject(LifecycleContract.encode(end, negotiated: true)) as NSDictionary,
            try jsonObject(contract("fixtures/lifecycle/valid/session-end.json")) as NSDictionary
        )
        XCTAssertThrowsError(try LifecycleContract.encode(cancel, negotiated: false)) { error in
            XCTAssertEqual(error as? LifecycleContractError, .notNegotiated)
        }
        XCTAssertThrowsError(
            try LifecycleContract.encode(.cancel(requestId: "   ", sessionId: "session-a"), negotiated: true)
        )
        XCTAssertThrowsError(
            try LifecycleContract.encode(.sessionEnd(requestId: "end-a", sessionId: ""), negotiated: true)
        )
    }

    // MARK: Negotiation

    func testNegotiationMatchesTheHandshakeTableWhereTheServerAccepts() throws {
        let cases = try XCTUnwrap(jsonObject(contract("auth-scenarios.json"))["cases"] as? [[String: Any]])
        var checked = 0
        for scenario in cases where serverWouldAccept(scenario) {
            let offered = scenario["offered"] as? [String] ?? []
            let selected = scenario["selected"] as? String
            let upgraded = scenario["handshake_ok"] as? Bool ?? true
            let outcome = ProtocolNegotiation.evaluate(offered: offered, selected: selected, upgraded: upgraded)
            let name = scenario["name"] as? String ?? "?"
            XCTAssertEqual(outcome.usable, scenario["upgrade"] as? Bool, name)
            XCTAssertEqual(outcome.lifecycleControls, scenario["controls"] as? Bool ?? false, name)
            checked += 1
        }
        XCTAssertGreaterThanOrEqual(checked, 8)
    }

    func testThePhoneOffersNoSubprotocolSoItStaysLegacy() {
        XCTAssertEqual(ProtocolNegotiation.clientOffers, [])
        let outcome = ProtocolNegotiation.evaluate(offered: ProtocolNegotiation.clientOffers, selected: nil, upgraded: true)
        XCTAssertEqual(outcome, .init(usable: true, lifecycleControls: false))
        let empty = ProtocolNegotiation.evaluate(offered: [], selected: "", upgraded: true)
        XCTAssertEqual(empty, .init(usable: true, lifecycleControls: false))
        let pushed = ProtocolNegotiation.evaluate(offered: [], selected: ProtocolNegotiation.v2, upgraded: true)
        XCTAssertFalse(pushed.usable, "an unsolicited selection makes the socket unusable")
    }

    // MARK: Handshake auth

    func testNoCredentialMeansTheLegacyAuthOffHandshake() throws {
        let config = try XCTUnwrap(BackendConfig(string: "wss://metalab.modal.run/ws"))
        let plan = HandshakePlan(config: config, credential: nil)
        XCTAssertEqual(plan.authorization, HandshakeAuthorization.none)
        XCTAssertNil(plan.urlRequest.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(plan.urlRequest.url, config.webSocketURL)
        XCTAssertEqual(plan.offeredSubprotocols, [])
    }

    func testCredentialTravelsOnlyInTheAuthorizationHeaderOverWSS() throws {
        let secret = "abc.DEF-123_~+/="
        let config = try XCTUnwrap(BackendConfig(string: "wss://metalab.modal.run/ws"))
        let credential = try XCTUnwrap(HandshakeCredential("  \(secret)\n"))
        let plan = HandshakePlan(config: config, credential: credential)
        XCTAssertEqual(plan.authorization, .bearer)
        XCTAssertEqual(plan.urlRequest.value(forHTTPHeaderField: "Authorization"), "Bearer \(secret)")
        XCTAssertEqual(plan.urlRequest.url, config.webSocketURL)
        XCTAssertFalse(plan.urlRequest.url?.absoluteString.contains(secret) ?? true)
        XCTAssertNil(plan.urlRequest.value(forHTTPHeaderField: "Sec-WebSocket-Protocol"))
        XCTAssertNil(plan.urlRequest.httpBody)
        // An invoke is unchanged by auth: the credential never enters JSON.
        let invoke = try Contract.makeInvoke(requestId: "r", sessionId: "s", jpegBase64: "AAAA", wavBase64: nil, text: "explain")
        XCTAssertFalse(String(decoding: try Contract.encode(invoke), as: UTF8.self).contains(secret))
    }

    func testCredentialIsNeverSentOverPlainWS() throws {
        let config = try XCTUnwrap(BackendConfig(string: "ws://192.168.1.2:8000/ws"))
        let plan = HandshakePlan(config: config, credential: HandshakeCredential("token"))
        XCTAssertEqual(plan.authorization, .withheldInsecure)
        XCTAssertNil(plan.urlRequest.value(forHTTPHeaderField: "Authorization"))
    }

    func testCredentialRejectsUnusableValuesAndIsRedacted() throws {
        for raw in [nil, "", "   ", "two words", "tab\tinside", "caf\u{E9}", "line\u{7F}"] as [String?] {
            XCTAssertNil(HandshakeCredential(raw), String(describing: raw))
        }
        let credential = try XCTUnwrap(HandshakeCredential("s3cret-value"))
        for rendered in [
            String(describing: credential), String(reflecting: credential), "\(credential)",
            String(describing: Mirror(reflecting: credential).children.map { $0.value }),
        ] {
            XCTAssertFalse(rendered.contains("s3cret"), rendered)
        }
    }

    func testCredentialComesFromConfigurationAndIsNeverWritten() throws {
        let suite = "metalab.tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertNil(HandshakeCredential(defaults: defaults))
        defaults.set("from-config", forKey: HandshakeCredential.defaultsKey)
        XCTAssertEqual(HandshakeCredential(defaults: defaults), HandshakeCredential("from-config"))
    }

    func testHandshakeRefusalsMapToVisibleFailures() throws {
        XCTAssertNil(HandshakeRefusal(httpStatus: nil))
        XCTAssertNil(HandshakeRefusal(httpStatus: 101))
        XCTAssertNil(HandshakeRefusal(httpStatus: 200))
        let unauthorized = try XCTUnwrap(HandshakeRefusal(httpStatus: 401))
        XCTAssertFalse(unauthorized.retryable)
        XCTAssertTrue(unauthorized.banner.contains("access token"))
        let busy = try XCTUnwrap(HandshakeRefusal(httpStatus: 503))
        XCTAssertTrue(busy.retryable)
        XCTAssertFalse(try XCTUnwrap(HandshakeRefusal(httpStatus: 403)).retryable)
    }

    // MARK: Session retention

    func testRetentionIsTheContractsFifteenMinutesOnAMonotonicClock() {
        XCTAssertEqual(ClientSession.retention, .seconds(15 * 60))
        let start = ContinuousClock.now
        let session = ClientSession(id: "a", now: start)
        XCTAssertFalse(session.isExpired(at: start + .seconds(899)))
        XCTAssertTrue(session.isExpired(at: start + .seconds(900)), "expired at now >= deadline")
    }

    func testOnlyASentInvocationRefreshesAndAnExpiredSessionIsNotRevived() {
        let start = ContinuousClock.now
        var session = ClientSession(id: "a", now: start)
        XCTAssertTrue(session.recordInvocation(at: start + .seconds(800)))
        XCTAssertFalse(session.isExpired(at: start + .seconds(1_699)))
        XCTAssertTrue(session.isExpired(at: start + .seconds(1_700)))
        XCTAssertFalse(session.recordInvocation(at: start + .seconds(1_700)), "the boundary cannot refresh")
        XCTAssertTrue(session.isExpired(at: start + .seconds(1_700)))
        XCTAssertEqual(session.id, "a")
    }

    func testResetGivesAFreshIdAndMakesOlderWorkStale() {
        let start = ContinuousClock.now
        var session = ClientSession(id: "a", now: start)
        let before = session.generation
        XCTAssertFalse(session.reset(to: "a", at: start), "a deleted id is never reused")
        XCTAssertFalse(session.reset(to: "  ", at: start))
        XCTAssertTrue(session.owns(generation: before))
        XCTAssertTrue(session.reset(to: "b", at: start + .seconds(2_000)))
        XCTAssertEqual(session.id, "b")
        XCTAssertFalse(session.owns(generation: before))
        XCTAssertFalse(session.isExpired(at: start + .seconds(2_899)))
        XCTAssertTrue(session.isExpired(at: start + .seconds(2_900)))
    }

    func testEndingTheSessionClearsItsCardButKeepsTheGlassesState() {
        let card = CardMessage(
            requestId: "r", title: "T", caption: "C", imageURL: nil, speechText: "S",
            audioURL: nil, book: nil, sources: [], models: ModelTrace()
        )
        var phone = PhoneSession(link: .started, permissionGranted: true, registered: true, displayEnabled: false)
        phone = SessionMachine.reduce(phone, .card(card))
        phone = SessionMachine.reduce(phone, .failure(.modelTimeout, retryable: true))
        let ended = phone.endingBookSession()
        XCTAssertNil(ended.lastCard)
        XCTAssertNil(ended.banner)
        XCTAssertEqual(ended.action, .none)
        XCTAssertTrue(ended.canInvoke)
        XCTAssertFalse(ended.displayEnabled)

        let folded = SessionMachine.reduce(phone, .failure(.hingesClosed, retryable: false)).endingBookSession()
        XCTAssertNil(folded.lastCard)
        XCTAssertEqual(folded.action, .startNewSession, "a glasses recovery outlives the book session")
        XCTAssertTrue(folded.needsNewSession)
    }

    // MARK: Helpers

    /// Mirrors only the server-side gates of `handshake()` in contracts/test_lifecycle.py, so the
    /// remaining expectations are the client's subprotocol decisions.
    private func serverWouldAccept(_ scenario: [String: Any]) -> Bool {
        guard scenario["enabled"] as? Bool == true else { return true }
        let gates = ["ios_verified", "rollout_agreed", "tls"].allSatisfy { scenario[$0] as? Bool == true }
        let ready = ["verifier_ready", "configured"].allSatisfy { scenario[$0] as? Bool ?? true }
        return gates && ready && scenario["credential"] as? String == "valid"
    }

    private var contractsRoot: URL {
        // Tests/MetaLabCoreTests/ -> MetaLabCore -> ios -> repository root.
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("contracts", isDirectory: true)
    }

    private func jsonNames(in folder: String) throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: contractsRoot.appendingPathComponent(folder).path)
            .filter { $0.hasSuffix(".json") }
            .sorted()
    }

    private func contract(_ path: String) throws -> Data {
        try Data(contentsOf: contractsRoot.appendingPathComponent(path))
    }

    private func jsonObject(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}
