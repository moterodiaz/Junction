import Foundation

public enum AudioClip {
    /// PCM16 mono WAV, entirely in memory. The invoke path never writes this to disk.
    public static func wav(pcm16: [Int16], sampleRate: Int) -> Data {
        let dataBytes = pcm16.count * 2
        var bytes = Data()
        bytes.reserveCapacity(44 + dataBytes)
        func append(_ string: String) { bytes.append(contentsOf: string.utf8) }
        func append32(_ value: UInt32) { bytes.append(contentsOf: withUnsafeBytes(of: value.littleEndian) { Array($0) }) }
        func append16(_ value: UInt16) { bytes.append(contentsOf: withUnsafeBytes(of: value.littleEndian) { Array($0) }) }

        append("RIFF")
        append32(UInt32(36 + dataBytes))
        append("WAVE")
        append("fmt ")
        append32(16)
        append16(1)
        append16(1)
        append32(UInt32(sampleRate))
        append32(UInt32(sampleRate * 2))
        append16(2)
        append16(16)
        append("data")
        append32(UInt32(dataBytes))
        for sample in pcm16 {
            append16(UInt16(bitPattern: sample))
        }
        return bytes
    }

    /// Drop the quiet tail so a short command is not padded out to the maximum.
    /// A fully silent buffer is returned unchanged: the backend then answers `stt_failed`.
    public static func trimTrailingSilence(
        pcm16: [Int16],
        sampleRate: Int,
        trailingSeconds: Double,
        threshold: Int16 = 900
    ) -> [Int16] {
        guard sampleRate > 0, !pcm16.isEmpty else { return pcm16 }
        let lastLoud = pcm16.lastIndex { abs(Int($0)) >= Int(threshold) }
        guard let lastLoud else { return pcm16 }
        let pad = Int((trailingSeconds * Double(sampleRate)).rounded(.up))
        let end = min(pcm16.count, lastLoud + 1 + pad)
        let minimum = min(pcm16.count, sampleRate / 4)
        if end < minimum { return Array(pcm16.prefix(minimum)) }
        return Array(pcm16.prefix(end))
    }
}
