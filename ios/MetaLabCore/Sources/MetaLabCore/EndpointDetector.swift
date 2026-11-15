import Foundation

/// Decides when to stop recording a short spoken command. Feed it PCM16 mono chunks of any size.
/// It is done when the wearer has spoken and then gone quiet, or when the hard cap is reached.
/// The speech level adapts to the room: it must beat a multiple of the noise floor measured at the start.
public struct EndpointDetector: Sendable {
    /// True once speech was heard and then trailed off, or the cap passed.
    public private(set) var isDone = false
    /// True once the level stayed above the threshold long enough. A click or a tap does not count.
    public private(set) var heardSpeech = false

    private static let framesPerSecond = 50
    /// The first 0.3 s sets the noise floor. The quietest frame is used, so early speech does not inflate it.
    private static let calibrationFrames = 15
    /// 0.16 s of unbroken loudness counts as speech.
    private static let minimumSpeechFrames = 8
    private static let floorMultiple = 3.0
    /// RMS on the 16-bit scale. Speech must beat this even in a silent room.
    private static let minimumLevel = 400.0

    private let frameSize: Int
    private let capFrames: Int
    private let silenceFrames: Int
    private var pending: [Int16] = []
    private var frames = 0
    private var noiseFloor = Double.infinity
    private var loudRun = 0
    private var quietRun = 0

    public init(sampleRate: Int, maxSeconds: Double, trailingSilenceSeconds: Double = 0.7) {
        let perSecond = Double(Self.framesPerSecond)
        frameSize = max(1, sampleRate / Self.framesPerSecond)
        capFrames = max(1, Int((maxSeconds * perSecond).rounded()))
        silenceFrames = max(1, Int((trailingSilenceSeconds * perSecond).rounded()))
    }

    /// Returns `isDone`. Once done, later chunks are ignored.
    @discardableResult
    public mutating func feed(_ chunk: [Int16]) -> Bool {
        guard !isDone else { return true }
        pending.append(contentsOf: chunk)
        var start = 0
        while !isDone, start + frameSize <= pending.count {
            let level = Self.rms(pending[start..<(start + frameSize)])
            start += frameSize
            advance(level: level)
        }
        pending.removeFirst(start)
        return isDone
    }

    private mutating func advance(level: Double) {
        frames += 1
        if frames <= Self.calibrationFrames {
            noiseFloor = min(noiseFloor, level)
        } else if level >= max(Self.minimumLevel, noiseFloor * Self.floorMultiple) {
            loudRun += 1
            quietRun = 0
            if loudRun >= Self.minimumSpeechFrames { heardSpeech = true }
        } else {
            loudRun = 0
            if heardSpeech { quietRun += 1 }
        }
        isDone = frames >= capFrames || quietRun >= silenceFrames
    }

    private static func rms(_ frame: ArraySlice<Int16>) -> Double {
        let sum = frame.reduce(0.0) { total, sample in total + Double(sample) * Double(sample) }
        return (sum / Double(frame.count)).squareRoot()
    }
}
