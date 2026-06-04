#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

final class VoiceLevelMeterTests: XCTestCase {
    func testDisplayAmplitudesUseSineWaveShape() {
        let amplitudes = VoiceLevelMeter.displayAmplitudes(level: 0.6, phase: 0.22)

        XCTAssertEqual(amplitudes.count, 16)
        XCTAssertGreaterThan((amplitudes.max() ?? 0) - (amplitudes.min() ?? 0), 0.1)
    }

    func testVoiceLevelLogReadsMostRecentFreshLevel() throws {
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
        defer { try? FileManager.default.removeItem(at: logURL) }
        try """
        {"timestamp":"2026-06-04T12:00:00Z","level":0.21}
        {"timestamp":"2026-06-04T12:00:01Z","level":0.73}
        """.write(to: logURL, atomically: true, encoding: .utf8)

        let now = try XCTUnwrap(Self.iso8601.date(from: "2026-06-04T12:00:01Z"))
        let level = try XCTUnwrap(VoiceLevelLog.latestLevel(from: logURL, now: now))

        XCTAssertEqual(level, CGFloat(0.73), accuracy: 0.0001)
    }

    func testVoiceLevelLogIgnoresStaleLevel() throws {
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
        defer { try? FileManager.default.removeItem(at: logURL) }
        try #"{"timestamp":"2026-06-04T12:00:00Z","level":0.91}"#
            .write(to: logURL, atomically: true, encoding: .utf8)
        let now = try XCTUnwrap(Self.iso8601.date(from: "2026-06-04T12:00:05Z"))

        XCTAssertNil(VoiceLevelLog.latestLevel(from: logURL, now: now, maxAge: 1.0))
    }

    func testVoiceLevelLogScansTailAndSkipsInvalidTrailingLine() throws {
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
        defer { try? FileManager.default.removeItem(at: logURL) }
        let staleLines = Array(
            repeating: #"{"timestamp":"2026-06-04T11:00:00Z","level":0.12}"#,
            count: 2_000
        ).joined(separator: "\n")
        try """
        \(staleLines)
        {"timestamp":"2026-06-04T12:00:01Z","level":0.64}
        not-json
        """.write(to: logURL, atomically: true, encoding: .utf8)
        let now = try XCTUnwrap(Self.iso8601.date(from: "2026-06-04T12:00:01Z"))

        let level = try XCTUnwrap(VoiceLevelLog.latestLevel(from: logURL, now: now))

        XCTAssertEqual(level, CGFloat(0.64), accuracy: 0.0001)
    }

    func testOverlayPanelLeavesRoomForShadowBlur() {
        let panelSize = VoiceLevelOverlayLayout.panelSize
        let pillSize = VoiceLevelOverlayLayout.pillSize
        let shadowRadius = VoiceLevelOverlayLayout.shadowRadius

        XCTAssertGreaterThanOrEqual(
            (panelSize.width - pillSize.width) / 2,
            shadowRadius,
            "The transparent panel needs enough horizontal margin to avoid clipping the capsule shadow."
        )
        XCTAssertGreaterThanOrEqual(
            (panelSize.height - pillSize.height) / 2,
            shadowRadius + abs(VoiceLevelOverlayLayout.shadowYOffset),
            "The transparent panel needs enough vertical margin to avoid clipping the offset capsule shadow."
        )
    }

    private static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
#endif
