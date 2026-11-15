import Foundation
import XCTest
@testable import MetaLabCore

final class EndpointDetectorTests: XCTestCase {
    private let rate = 16_000

    func testSilenceOnlyRunsToTheCap() throws {
        let quiet = noise(seconds: 7, rms: 30)
        let (detector, stop) = feed(quiet)
        XCTAssertEqual(try XCTUnwrap(stop), 6, accuracy: 0.1)
        XCTAssertFalse(detector.heardSpeech)

        let (_, digital) = feed([Int16](repeating: 0, count: 7 * rate))
        XCTAssertEqual(try XCTUnwrap(digital), 6, accuracy: 0.1)
    }

    func testSpeechThenSilenceStopsEarly() throws {
        let signal = noise(seconds: 0.5, rms: 30) + tone(seconds: 1.5, amplitude: 4000) + noise(seconds: 3, rms: 30)
        let (detector, stop) = feed(signal)
        // Speech ends at 2.0 s, then 0.7 s of trailing silence.
        XCTAssertEqual(try XCTUnwrap(stop), 2.7, accuracy: 0.1)
        XCTAssertTrue(detector.heardSpeech)
    }

    func testChunkSizeDoesNotChangeWhenItStops() throws {
        let signal = noise(seconds: 0.5, rms: 30) + tone(seconds: 1.5, amplitude: 4000) + noise(seconds: 3, rms: 30)
        let (_, stop) = feed(signal, chunk: 7)
        XCTAssertEqual(try XCTUnwrap(stop), 2.7, accuracy: 0.001)
    }

    func testAShortClickIsNotSpeech() throws {
        let signal = noise(seconds: 0.5, rms: 30) + tone(seconds: 0.03, amplitude: 20_000) + noise(seconds: 6, rms: 30)
        let (detector, stop) = feed(signal)
        XCTAssertFalse(detector.heardSpeech)
        // No early stop: it still runs to the cap.
        XCTAssertEqual(try XCTUnwrap(stop), 6, accuracy: 0.1)
    }

    func testANoisyFloorIsNotSpeechButLoudSpeechStillEnds() throws {
        // Steady noise above the absolute minimum must not count as speech.
        let (idle, idleStop) = feed(noise(seconds: 7, rms: 600))
        XCTAssertFalse(idle.heardSpeech)
        XCTAssertEqual(try XCTUnwrap(idleStop), 6, accuracy: 0.1)

        let signal = noise(seconds: 0.5, rms: 600) + tone(seconds: 1.5, amplitude: 6000) + noise(seconds: 3, rms: 600)
        let (detector, stop) = feed(signal)
        XCTAssertTrue(detector.heardSpeech)
        XCTAssertEqual(try XCTUnwrap(stop), 2.7, accuracy: 0.1)
    }

    func testTheCapWinsWhenSpeechNeverStops() throws {
        let signal = noise(seconds: 0.5, rms: 30) + tone(seconds: 8, amplitude: 4000)
        let (detector, stop) = feed(signal)
        XCTAssertTrue(detector.heardSpeech)
        XCTAssertEqual(try XCTUnwrap(stop), 6, accuracy: 0.1)
    }

    /// Feeds the signal in tap-sized chunks. Returns the detector and the seconds fed when it finished.
    private func feed(_ signal: [Int16], chunk: Int = 1024) -> (EndpointDetector, Double?) {
        var detector = EndpointDetector(sampleRate: rate, maxSeconds: 6, trailingSilenceSeconds: 0.7)
        var start = 0
        while start < signal.count {
            let end = min(start + chunk, signal.count)
            if detector.feed(Array(signal[start..<end])) {
                return (detector, Double(end) / Double(rate))
            }
            start = end
        }
        return (detector, nil)
    }

    private func tone(seconds: Double, amplitude: Double) -> [Int16] {
        let count = Int(seconds * Double(rate))
        var samples: [Int16] = []
        samples.reserveCapacity(count)
        for index in 0..<count {
            let phase = 2 * Double.pi * 220 * Double(index) / Double(rate)
            samples.append(Int16(amplitude * sin(phase)))
        }
        return samples
    }

    /// Repeatable pseudo-random noise with the given RMS.
    private func noise(seconds: Double, rms: Double) -> [Int16] {
        let count = Int(seconds * Double(rate))
        let peak = rms * 3.0.squareRoot()
        var state: UInt32 = 12_345
        var samples: [Int16] = []
        samples.reserveCapacity(count)
        for _ in 0..<count {
            state = state &* 1_664_525 &+ 1_013_904_223
            let unit = Double(state >> 8) / 16_777_216
            samples.append(Int16((unit * 2 - 1) * peak))
        }
        return samples
    }
}
