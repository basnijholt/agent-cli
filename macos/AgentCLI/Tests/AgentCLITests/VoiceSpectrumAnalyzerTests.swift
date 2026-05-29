#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

final class VoiceSpectrumAnalyzerTests: XCTestCase {
    func testLowAndHighTonesPeakInDifferentFrequencyBands() {
        let sampleRate = 16_000.0
        let analyzer = VoiceSpectrumAnalyzer(sampleRate: sampleRate, bandCount: 16)

        let lowTone = Self.sineWave(frequency: 220, sampleRate: sampleRate)
        let highTone = Self.sineWave(frequency: 3_200, sampleRate: sampleRate)

        let lowPeakIndex = analyzer.amplitudes(from: lowTone).maxIndex()
        let highPeakIndex = analyzer.amplitudes(from: highTone).maxIndex()

        XCTAssertNotNil(lowPeakIndex)
        XCTAssertNotNil(highPeakIndex)
        XCTAssertLessThan(lowPeakIndex!, 5)
        XCTAssertGreaterThan(highPeakIndex!, 9)
    }

    func testSilenceProducesNoFrequencyEnergy() {
        let analyzer = VoiceSpectrumAnalyzer(sampleRate: 16_000, bandCount: 16)

        let amplitudes = analyzer.amplitudes(from: Array(repeating: Float(0), count: 1_024))

        XCTAssertEqual(amplitudes.count, 16)
        XCTAssertTrue(amplitudes.allSatisfy { $0 == 0 })
    }

    private static func sineWave(
        frequency: Double,
        sampleRate: Double,
        sampleCount: Int = 2_048
    ) -> [Float] {
        (0..<sampleCount).map { index in
            Float(sin(2 * Double.pi * frequency * Double(index) / sampleRate))
        }
    }
}

private extension Array where Element == CGFloat {
    func maxIndex() -> Int? {
        guard let maxValue = self.max() else { return nil }
        return firstIndex(of: maxValue)
    }
}
#endif
