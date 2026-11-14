import Foundation

/// Order of one invocation. Capture finishes, and the camera is stopped, before any lens layout.
/// Meta's known issue is "do not combine capture with display". Plan A is this sequence.
/// Plan B is `displayEnabled == false`: the answer still arrives by voice.
public enum CaptureStep: String, Equatable, Sendable, Codable, CaseIterable {
    case settleHFP
    case recordAudio
    case startCamera
    case takeOneFrame
    case stopCamera
    case showProgress
    case sendInvoke
    case speak
}

public enum PageResolution: String, Equatable, Sendable, Codable {
    /// 720×1280. Preferred for a book page. Bluetooth compression is the open risk.
    case high
    /// 504×896.
    case medium
    /// 360×640.
    case low

    public var pixelSize: (width: Int, height: Int) {
        switch self {
        case .high: (720, 1280)
        case .medium: (504, 896)
        case .low: (360, 640)
        }
    }
}

public struct CaptureSettings: Equatable, Sendable {
    public var maxRecordSeconds: Double
    public var trailingSilenceSeconds: Double
    public var sampleRate: Int
    /// Valid DAT rates are 2, 7, 15, 24, 30. Two frames per second keeps the page sharper.
    public var frameRate: Int
    public var resolution: PageResolution
    public var displayEnabled: Bool
    /// Standalone `capturePhoto()` is beta. Off until a hardware test says the stream frame is unreadable.
    public var useStandalonePhoto: Bool

    public init(
        maxRecordSeconds: Double = 4,
        trailingSilenceSeconds: Double = 0.7,
        sampleRate: Int = 16_000,
        frameRate: Int = 2,
        resolution: PageResolution = .high,
        displayEnabled: Bool = true,
        useStandalonePhoto: Bool = false
    ) {
        self.maxRecordSeconds = maxRecordSeconds
        self.trailingSilenceSeconds = trailingSilenceSeconds
        self.sampleRate = sampleRate
        self.frameRate = frameRate
        self.resolution = resolution
        self.displayEnabled = displayEnabled
        self.useStandalonePhoto = useStandalonePhoto
    }

    public static let demo = CaptureSettings()
}

public enum CapturePlan {
    public static func steps(settings: CaptureSettings, typedCommand: String?) -> [CaptureStep] {
        let typed = typedCommand?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        var steps: [CaptureStep] = []
        if !typed {
            steps.append(.settleHFP)
            steps.append(.recordAudio)
        }
        steps.append(contentsOf: [.startCamera, .takeOneFrame, .stopCamera])
        if settings.displayEnabled {
            steps.append(.showProgress)
        }
        steps.append(.sendInvoke)
        steps.append(.speak)
        return steps
    }

    /// The camera step is strictly before the first lens update.
    public static func cameraStopsBeforeDisplay(_ steps: [CaptureStep]) -> Bool {
        guard let stop = steps.firstIndex(of: .stopCamera) else { return false }
        guard let show = steps.firstIndex(of: .showProgress) else { return true }
        return stop < show
    }

    /// Speech is last, and it is present whether or not the lens is on.
    public static func speaksEvenIfDisplayIsOff(_ steps: [CaptureStep]) -> Bool {
        steps.last == .speak
    }
}
