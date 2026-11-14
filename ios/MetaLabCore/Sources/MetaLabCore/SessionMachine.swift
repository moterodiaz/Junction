import Foundation

public enum GlassesLink: String, Equatable, Sendable, Codable {
    case idle
    case starting
    case started
    case paused
    case stopping
    case stopped
}

public enum FailureKind: String, Equatable, Sendable, Codable {
    case permissionDenied
    case microphoneDenied
    case sessionPaused
    case sessionStopped
    case hingesClosed
    case bluetoothLost
    case backendTimeout
    case unreadablePage
    case speechFailed
    case modelTimeout
    case backend
}

public enum RecoveryAction: String, Equatable, Sendable, Codable {
    /// Ask again. Do not start a second session while the current one is only paused.
    case waitForResume
    /// A stopped session is terminal. The next attempt creates a new one.
    case startNewSession
    case requestPermission
    /// The iPhone microphone permission lives in the iPhone Settings app, not in Meta AI.
    case openSettings
    case retryInvoke
    case none
}

public struct Recovery: Equatable, Sendable {
    public var banner: String
    public var actionTitle: String
    public var action: RecoveryAction
    /// The phone keeps the last card through every failure. The lens shows the banner instead.
    public var keepsLastCard: Bool

    public init(banner: String, actionTitle: String, action: RecoveryAction, keepsLastCard: Bool = true) {
        self.banner = banner
        self.actionTitle = actionTitle
        self.action = action
        self.keepsLastCard = keepsLastCard
    }
}

public struct PhoneSession: Equatable, Sendable {
    public var link: GlassesLink
    public var permissionGranted: Bool
    public var registered: Bool
    public var lastCard: CardMessage?
    public var banner: String?
    public var actionTitle: String?
    public var action: RecoveryAction
    public var needsNewSession: Bool
    public var displayEnabled: Bool

    public init(
        link: GlassesLink = .idle,
        permissionGranted: Bool = false,
        registered: Bool = false,
        lastCard: CardMessage? = nil,
        banner: String? = nil,
        actionTitle: String? = nil,
        action: RecoveryAction = .none,
        needsNewSession: Bool = false,
        displayEnabled: Bool = true
    ) {
        self.link = link
        self.permissionGranted = permissionGranted
        self.registered = registered
        self.lastCard = lastCard
        self.banner = banner
        self.actionTitle = actionTitle
        self.action = action
        self.needsNewSession = needsNewSession
        self.displayEnabled = displayEnabled
    }

    public var canInvoke: Bool {
        registered && permissionGranted && link == .started && !needsNewSession
    }
}

public enum SessionSignal: Equatable, Sendable {
    case link(GlassesLink)
    case permission(Bool)
    case registration(Bool)
    case card(CardMessage)
    case failure(FailureKind, retryable: Bool)
    case displayEnabled(Bool)
}

public enum SessionMachine {
    public static func reduce(_ state: PhoneSession, _ signal: SessionSignal) -> PhoneSession {
        var next = state
        switch signal {
        case .link(let link):
            next.link = link
            switch link {
            case .paused:
                apply(FailurePolicy.recovery(for: .sessionPaused, retryable: false), to: &next)
            case .stopped:
                next.needsNewSession = true
                // A more specific failure (hinges, Bluetooth) already asked for a new session.
                if next.action != .startNewSession {
                    apply(FailurePolicy.recovery(for: .sessionStopped, retryable: false), to: &next)
                }
            case .started:
                next.needsNewSession = false
                if next.action == .waitForResume || next.action == .startNewSession {
                    clearBanner(&next)
                }
            case .idle, .starting, .stopping:
                break
            }
        case .permission(let granted):
            next.permissionGranted = granted
            if granted, next.action == .requestPermission {
                clearBanner(&next)
            } else if !granted {
                apply(FailurePolicy.recovery(for: .permissionDenied, retryable: false), to: &next)
            }
        case .registration(let registered):
            next.registered = registered
        case .card(let card):
            next.lastCard = card
            clearBanner(&next)
        case .failure(let kind, let retryable):
            apply(FailurePolicy.recovery(for: kind, retryable: retryable), to: &next)
            if kind == .sessionStopped || kind == .hingesClosed || kind == .bluetoothLost {
                next.needsNewSession = true
                if kind != .sessionPaused {
                    next.link = .stopped
                }
            }
        case .displayEnabled(let enabled):
            next.displayEnabled = enabled
        }
        return next
    }

    private static func apply(_ recovery: Recovery, to state: inout PhoneSession) {
        let kept = state.lastCard
        state.banner = recovery.banner
        state.actionTitle = recovery.actionTitle
        state.action = recovery.action
        if recovery.keepsLastCard {
            state.lastCard = kept
        }
    }

    private static func clearBanner(_ state: inout PhoneSession) {
        state.banner = nil
        state.actionTitle = nil
        state.action = .none
    }
}

public enum FailurePolicy {
    public static func kind(for code: ServerErrorCode) -> FailureKind {
        switch code {
        case .noTextFound: .unreadablePage
        case .sttFailed: .speechFailed
        case .modelTimeout: .modelTimeout
        case .internalError: .backend
        }
    }

    public static func recovery(for kind: FailureKind, retryable: Bool) -> Recovery {
        switch kind {
        case .permissionDenied:
            return Recovery(
                banner: "Camera permission was denied. Allow it in Meta AI, then come back.",
                actionTitle: "Allow camera",
                action: .requestPermission
            )
        case .microphoneDenied:
            return Recovery(
                banner: "Microphone access is off. Allow it for MetaLab in the iPhone Settings app.",
                actionTitle: "Open Settings",
                action: .openSettings
            )
        case .sessionPaused:
            return Recovery(
                banner: "Glasses paused. Wait — a new session is not needed yet.",
                actionTitle: "Waiting",
                action: .waitForResume
            )
        case .sessionStopped:
            return Recovery(
                banner: "Session stopped. Reconnect, then ask again.",
                actionTitle: "Reconnect",
                action: .startNewSession
            )
        case .hingesClosed:
            return Recovery(
                banner: "Glasses are folded. Open them and reconnect.",
                actionTitle: "Reconnect",
                action: .startNewSession
            )
        case .bluetoothLost:
            return Recovery(
                banner: "Bluetooth link lost. Reconnect, then ask again.",
                actionTitle: "Reconnect",
                action: .startNewSession
            )
        case .backendTimeout:
            return Recovery(
                banner: "The backend took too long. Nothing was kept from the page.",
                actionTitle: "Try again",
                action: .retryInvoke
            )
        case .unreadablePage:
            return Recovery(
                banner: "No readable text on that page. Point the glasses at the text and try again.",
                actionTitle: "Try again",
                action: .retryInvoke
            )
        case .speechFailed:
            return Recovery(
                banner: retryable
                    ? "Could not hear a command. Try “explain”, “draw”, or “who is this”."
                    : "Could not hear a command.",
                actionTitle: "Try again",
                action: .retryInvoke
            )
        case .modelTimeout:
            return Recovery(
                banner: "The model timed out. Try again.",
                actionTitle: "Try again",
                action: .retryInvoke
            )
        case .backend:
            return Recovery(
                banner: retryable
                    ? "Something went wrong. Try again."
                    : "Something went wrong.",
                actionTitle: retryable ? "Try again" : "OK",
                action: retryable ? .retryInvoke : .none
            )
        }
    }
}
