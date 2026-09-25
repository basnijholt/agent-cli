#if canImport(XCTest)
import Foundation
import AppKit
import SwiftUI
import XCTest
@testable import AgentCLI

final class VoiceLevelMeterTests: XCTestCase {
    func testTranscribingCompactsPreviewAndFailedStopRestoresIt() throws {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.show(showsPreviewSpace: true)
        let panel = try XCTUnwrap(NSApplication.shared.windows.first {
            $0.contentView is NSHostingView<VoiceLevelOverlayView>
        })
        XCTAssertEqual(panel.frame.width, 446)
        overlay.showTranscribing()
        XCTAssertEqual(panel.frame.width, 248)
        overlay.finishTranscribing()
        XCTAssertEqual(panel.frame.width, 446)
    }

    func testTranscriptionTimerStartsAtReleaseAndResetsForNextRequest() {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        var now = Date()
        let meter = VoiceLevelMeter(levelLogURL: logURL, now: { now })
        defer {
            meter.stop()
            try? FileManager.default.removeItem(at: logURL)
        }
        meter.start()
        now = now.addingTimeInterval(20)
        meter.beginTranscribing()
        XCTAssertEqual(meter.transcribingDuration, "00:00")
        now = now.addingTimeInterval(65)
        meter.pollLevel()
        XCTAssertEqual(meter.transcribingDuration, "01:05")
        meter.beginTranscribing()
        XCTAssertEqual(meter.transcribingDuration, "01:05", "Repeated transitions must not reset elapsed time.")
        meter.stop()
        meter.beginTranscribing()
        XCTAssertEqual(meter.transcribingDuration, "00:00")
    }

    func testEndingRecordingKeepsPendingTranscriptionVisible() {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.show()
        overlay.showTranscribing()
        overlay.endRecording()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .transcribing)
        overlay.finishTranscribing()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .idle)
    }

    func testFailedStopRestoresOngoingRecording() {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.show()
        overlay.showTranscribing()
        overlay.finishTranscribing()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .connecting)
        overlay.endRecording()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .idle)
    }

    func testFinishingTranscriptionDoesNotDismissANewRecording() {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.showTranscribing()
        overlay.finishTranscribing()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .idle)

        overlay.showTranscribing()
        overlay.show()
        overlay.finishTranscribing()
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .connecting)
    }

    func testTranscribingStopsAudioPollingAndAllowsNextRecording() throws {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let meter = VoiceLevelMeter(levelLogURL: logURL)
        defer {
            meter.stop()
            try? FileManager.default.removeItem(at: logURL)
        }
        meter.start()
        meter.beginTranscribing()
        try "{\"timestamp\":\"\(Self.iso8601.string(from: Date()))\",\"level\":0.9}"
            .write(to: logURL, atomically: true, encoding: .utf8)
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .transcribing)
        meter.start()
        XCTAssertEqual(meter.captureState, .connecting)
        meter.stop()
        XCTAssertEqual(meter.captureState, .idle)
    }

    func testRecordingTimerExcludesStartupAndResetsBetweenRecordings() throws {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        var now = try XCTUnwrap(Self.iso8601.date(from: "2026-06-04T12:00:00Z"))
        let meter = VoiceLevelMeter(levelLogURL: logURL, now: { now })
        defer {
            meter.stop()
            try? FileManager.default.removeItem(at: logURL)
        }
        meter.start()
        now = now.addingTimeInterval(10)
        meter.pollLevel()
        XCTAssertEqual(meter.recordingDuration, "00:00")

        func publishAudio() throws {
            try "{\"timestamp\":\"\(Self.iso8601.string(from: now))\",\"level\":0}"
                .write(to: logURL, atomically: true, encoding: .utf8)
            meter.pollLevel()
        }
        try publishAudio()
        XCTAssertEqual(meter.recordingDuration, "00:00")
        now = now.addingTimeInterval(9)
        try publishAudio()
        XCTAssertEqual(meter.recordingDuration, "00:09")
        now = now.addingTimeInterval(56)
        try publishAudio()
        XCTAssertEqual(meter.recordingDuration, "01:05")
        now = now.addingTimeInterval(3600)
        try publishAudio()
        XCTAssertEqual(meter.recordingDuration, "61:05")

        meter.stop()
        XCTAssertEqual(meter.recordingDuration, "00:00")
        meter.start()
        try publishAudio()
        XCTAssertEqual(meter.recordingDuration, "00:00")
    }

    func testRecordingReadinessFollowsFreshAudioIncludingSilence() throws {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        var now = try XCTUnwrap(Self.iso8601.date(from: "2026-06-04T12:00:00Z"))
        let meter = VoiceLevelMeter(levelLogURL: logURL, now: { now })
        defer {
            meter.stop()
            try? FileManager.default.removeItem(at: logURL)
        }

        // A previous recording must not make a new request look ready.
        try #"{"timestamp":"2026-06-04T12:00:00Z","level":0.9}"#
            .write(to: logURL, atomically: true, encoding: .utf8)
        meter.start()
        XCTAssertEqual(meter.captureState, .connecting)

        try #"{"timestamp":"2026-06-04T12:00:00Z","level":0}"#
            .write(to: logURL, atomically: true, encoding: .utf8)
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .recording, "Silent audio still proves capture is running.")

        now = now.addingTimeInterval(2)
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .waitingForAudio)

        try #"{"timestamp":"2026-06-04T12:00:02Z","level":0.6}"#
            .write(to: logURL, atomically: true, encoding: .utf8)
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .recording)

        meter.stop()
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .idle, "Late polling must not revive a released overlay.")
        meter.start()
        XCTAssertEqual(meter.captureState, .connecting)
    }

    func testConnectingDoesNotAnimateFakeMicrophoneActivity() throws {
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let meter = VoiceLevelMeter(levelLogURL: logURL)
        defer {
            meter.stop()
            try? FileManager.default.removeItem(at: logURL)
        }
        meter.start()
        let initialAmplitudes = meter.amplitudes
        meter.pollLevel()
        XCTAssertEqual(meter.captureState, .connecting)
        XCTAssertEqual(meter.amplitudes, initialAmplitudes)
        meter.stop()
        XCTAssertEqual(meter.captureState, .idle)
    }

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
        let panelSize = VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: false)
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

    func testOverlayPanelOnlyExpandsForPreviewSpace() {
        let compactSize = VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: false)
        let previewSize = VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: true)

        XCTAssertEqual(
            compactSize.width,
            VoiceLevelOverlayLayout.pillSize.width + (VoiceLevelOverlayLayout.horizontalPadding * 2)
        )
        XCTAssertGreaterThan(previewSize.width, compactSize.width)
        XCTAssertGreaterThan(previewSize.height, compactSize.height)
    }

    private static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
#endif
