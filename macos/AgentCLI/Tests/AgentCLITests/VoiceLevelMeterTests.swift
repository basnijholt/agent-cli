#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

final class VoiceLevelMeterTests: XCTestCase {
    func testQuietInputProducesVisibleLevel() {
        let quietTone = Self.sineWave(amplitude: Float(pow(10.0, -35.0 / 20.0)))

        let level = VoiceLevelMeter.normalizedLevel(from: quietTone)

        XCTAssertGreaterThan(level, 0.5)
    }

    func testSilenceUsesIdleLevel() {
        let level = VoiceLevelMeter.normalizedLevel(from: Array(repeating: Float(0), count: 1_024))

        XCTAssertEqual(level, CGFloat(0.08))
    }

    func testDisplayAmplitudesUseSineWaveShape() {
        let amplitudes = VoiceLevelMeter.displayAmplitudes(level: 0.6, phase: 0.22)

        XCTAssertEqual(amplitudes.count, 16)
        XCTAssertGreaterThan((amplitudes.max() ?? 0) - (amplitudes.min() ?? 0), 0.1)
    }

    private static func sineWave(
        frequency: Double = 220,
        sampleRate: Double = 16_000,
        sampleCount: Int = 2_048,
        amplitude: Float = 1
    ) -> [Float] {
        (0..<sampleCount).map { index in
            amplitude * Float(sin(2 * Double.pi * frequency * Double(index) / sampleRate))
        }
    }
}
#endif
