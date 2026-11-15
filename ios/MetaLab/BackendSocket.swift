import Foundation
import MetaLabCore
import os

/// One WebSocket for one question. The payload is the invoke message and nothing else:
/// no API key, no frame after the send completes. The optional handshake credential travels only
/// in the `Authorization` header that `HandshakePlan` builds, and is never logged.
final class BackendSocket: NSObject, URLSessionWebSocketDelegate, @unchecked Sendable {
    /// Each callback carries the token `connect` returned, so a caller can drop replies from an older socket.
    var onText: (@Sendable (String, Int) -> Void)?
    /// The refusal is set when the server answered the handshake with an HTTP error status (401 with auth on).
    var onDisconnect: (@Sendable (Int, HandshakeRefusal?) -> Void)?

    private struct State {
        var session: URLSession?
        var task: URLSessionWebSocketTask?
        var generation = 0
    }

    private let state = OSAllocatedUnfairLock(initialState: State())

    @discardableResult
    func connect(plan: HandshakePlan) -> Int {
        disconnect()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = true
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: plan.urlRequest)
        let token = state.withLock { value -> Int in
            value.generation += 1
            value.session = session
            value.task = task
            return value.generation
        }
        task.resume()
        receive(on: task, token: token)
        return token
    }

    func send(_ data: Data) async throws {
        let task = state.withLock { $0.task }
        guard let task else { throw URLError(.notConnectedToInternet) }
        do {
            try await task.send(.data(data))
        } catch {
            throw Self.refusal(of: task) ?? error
        }
    }

    func disconnect() {
        let previous = state.withLock { value -> (URLSessionWebSocketTask?, URLSession?) in
            value.generation += 1
            let task = value.task
            let session = value.session
            value.task = nil
            value.session = nil
            return (task, session)
        }
        previous.0?.cancel(with: .goingAway, reason: nil)
        previous.1?.invalidateAndCancel()
    }

    /// A subprotocol the phone did not offer makes the socket unusable (contracts/LIFECYCLE.md);
    /// closing it surfaces as a disconnect on the receive loop.
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        let outcome = ProtocolNegotiation.evaluate(
            offered: ProtocolNegotiation.clientOffers, selected: `protocol`, upgraded: true
        )
        guard !outcome.usable else { return }
        webSocketTask.cancel(with: .protocolError, reason: nil)
    }

    private static func refusal(of task: URLSessionWebSocketTask) -> HandshakeRefusal? {
        HandshakeRefusal(httpStatus: (task.response as? HTTPURLResponse)?.statusCode)
    }

    private func receive(on task: URLSessionWebSocketTask, token: Int) {
        task.receive { [weak self] result in
            guard let self else { return }
            let current = self.state.withLock { $0.generation }
            guard token == current else { return }
            switch result {
            case .success(.string(let text)):
                self.onText?(text, token)
                self.receive(on: task, token: token)
            case .success(.data(let data)):
                if let text = String(data: data, encoding: .utf8) {
                    self.onText?(text, token)
                }
                self.receive(on: task, token: token)
            case .failure:
                self.onDisconnect?(token, Self.refusal(of: task))
            @unknown default:
                self.receive(on: task, token: token)
            }
        }
    }
}
