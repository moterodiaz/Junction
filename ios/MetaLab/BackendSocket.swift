import Foundation
import os

/// One WebSocket for one question. The payload is the invoke message and nothing else:
/// no API key, no frame after the send completes.
final class BackendSocket: NSObject, URLSessionWebSocketDelegate, @unchecked Sendable {
    var onText: (@Sendable (String) -> Void)?
    var onDisconnect: (@Sendable () -> Void)?

    private struct State {
        var session: URLSession?
        var task: URLSessionWebSocketTask?
        var generation = 0
    }

    private let state = OSAllocatedUnfairLock(initialState: State())

    func connect(url: URL) {
        disconnect()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = true
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: url)
        let token = state.withLock { value -> Int in
            value.generation += 1
            value.session = session
            value.task = task
            return value.generation
        }
        task.resume()
        receive(on: task, token: token)
    }

    func send(_ data: Data) async throws {
        let task = state.withLock { $0.task }
        guard let task else { throw URLError(.notConnectedToInternet) }
        try await task.send(.data(data))
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

    private func receive(on task: URLSessionWebSocketTask, token: Int) {
        task.receive { [weak self] result in
            guard let self else { return }
            let current = self.state.withLock { $0.generation }
            guard token == current else { return }
            switch result {
            case .success(.string(let text)):
                self.onText?(text)
                self.receive(on: task, token: token)
            case .success(.data(let data)):
                if let text = String(data: data, encoding: .utf8) {
                    self.onText?(text)
                }
                self.receive(on: task, token: token)
            case .failure:
                self.onDisconnect?()
            @unknown default:
                self.receive(on: task, token: token)
            }
        }
    }
}
