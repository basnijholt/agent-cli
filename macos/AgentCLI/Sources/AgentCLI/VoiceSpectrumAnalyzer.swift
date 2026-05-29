import CoreGraphics
import Foundation

final class VoiceSpectrumAnalyzer {
    private let sampleRate: Double
    private let bandCount: Int
    private let centerFrequencies: [Double]

    init(sampleRate: Double, bandCount: Int) {
        self.sampleRate = sampleRate
        self.bandCount = bandCount

        let lowFrequency = 80.0
        let highFrequency = min(7_600.0, max(lowFrequency, sampleRate * 0.46))
        let denominator = max(1, bandCount - 1)
        self.centerFrequencies = (0..<bandCount).map { index in
            let fraction = Double(index) / Double(denominator)
            return lowFrequency * pow(highFrequency / lowFrequency, fraction)
        }
    }

    func amplitudes(from samples: [Float]) -> [CGFloat] {
        guard !samples.isEmpty else {
            return Array(repeating: 0, count: bandCount)
        }

        let sampleCount = samples.count
        let windowedSamples = samples.enumerated().map { index, sample in
            Float(Self.hannWindowValue(index: index, sampleCount: sampleCount)) * sample
        }
        let normalization = max(1, Self.hannWindowSum(sampleCount: sampleCount) / 2)

        return centerFrequencies.map { frequency in
            let magnitude = Self.magnitude(
                frequency: frequency,
                sampleRate: sampleRate,
                samples: windowedSamples
            ) / normalization
            return CGFloat(min(1, sqrt(magnitude) * 1.35))
        }
    }

    private static func magnitude(
        frequency: Double,
        sampleRate: Double,
        samples: [Float]
    ) -> Double {
        let radiansPerSample = 2 * Double.pi * frequency / sampleRate
        var real = 0.0
        var imaginary = 0.0

        for (index, sample) in samples.enumerated() {
            let angle = radiansPerSample * Double(index)
            let value = Double(sample)
            real += value * cos(angle)
            imaginary -= value * sin(angle)
        }

        return sqrt((real * real) + (imaginary * imaginary))
    }

    private static func hannWindowValue(index: Int, sampleCount: Int) -> Double {
        guard sampleCount > 1 else { return 1 }
        return 0.5 - (0.5 * cos(2 * Double.pi * Double(index) / Double(sampleCount - 1)))
    }

    private static func hannWindowSum(sampleCount: Int) -> Double {
        guard sampleCount > 1 else { return 1 }
        return Double(sampleCount - 1) / 2
    }
}
