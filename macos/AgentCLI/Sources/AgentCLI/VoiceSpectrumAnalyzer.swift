import CoreGraphics
import Foundation

final class VoiceSpectrumAnalyzer {
    private static let minimumDisplayDecibels = -60.0
    private static let maximumDisplayDecibels = -18.0

    private let sampleRate: Double
    private let bandCount: Int
    private let centerFrequencies: [Double]
    private let frequencyBands: [(lower: Double, upper: Double)]

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
        self.frequencyBands = Self.frequencyBands(
            centerFrequencies: centerFrequencies,
            lowFrequency: lowFrequency,
            highFrequency: highFrequency
        )
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

        let frequencyResolution = sampleRate / Double(sampleCount)
        let maximumBin = max(1, sampleCount / 2)

        return frequencyBands.enumerated().map { index, band in
            let magnitude = Self.bandMagnitude(
                band: band,
                centerFrequency: centerFrequencies[index],
                frequencyResolution: frequencyResolution,
                maximumBin: maximumBin,
                sampleRate: sampleRate,
                samples: windowedSamples
            ) / normalization
            return CGFloat(Self.normalizedDisplayAmplitude(forMagnitude: magnitude))
        }
    }

    private static func frequencyBands(
        centerFrequencies: [Double],
        lowFrequency: Double,
        highFrequency: Double
    ) -> [(lower: Double, upper: Double)] {
        centerFrequencies.enumerated().map { index, centerFrequency in
            let lower = index == 0
                ? lowFrequency
                : sqrt(centerFrequencies[index - 1] * centerFrequency)
            let upper = index == centerFrequencies.count - 1
                ? highFrequency
                : sqrt(centerFrequency * centerFrequencies[index + 1])
            return (lower, upper)
        }
    }

    private static func bandMagnitude(
        band: (lower: Double, upper: Double),
        centerFrequency: Double,
        frequencyResolution: Double,
        maximumBin: Int,
        sampleRate: Double,
        samples: [Float]
    ) -> Double {
        let lowerBin = max(1, Int(ceil(band.lower / frequencyResolution)))
        let upperBin = min(maximumBin, Int(floor(band.upper / frequencyResolution)))

        if lowerBin <= upperBin {
            var maximumMagnitude = 0.0
            for bin in lowerBin...upperBin {
                maximumMagnitude = max(
                    maximumMagnitude,
                    magnitude(
                        frequency: Double(bin) * frequencyResolution,
                        sampleRate: sampleRate,
                        samples: samples
                    )
                )
            }
            return maximumMagnitude
        }

        let nearestCenterBin = min(maximumBin, max(1, Int((centerFrequency / frequencyResolution).rounded())))
        return magnitude(
            frequency: Double(nearestCenterBin) * frequencyResolution,
            sampleRate: sampleRate,
            samples: samples
        )
    }

    private static func normalizedDisplayAmplitude(forMagnitude magnitude: Double) -> Double {
        guard magnitude > 0 else { return 0 }

        let decibels = 20 * log10(max(magnitude, Double.leastNonzeroMagnitude))
        let normalized = (decibels - minimumDisplayDecibels) / (maximumDisplayDecibels - minimumDisplayDecibels)
        return min(1, max(0, normalized))
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
