import AppKit
import Foundation
import SwiftUI

enum VoiceLevelOverlayLayout {
    static let pillSize = CGSize(width: 190, height: 38)
    static let textWidth = CGFloat(420)
    static let textHeight = CGFloat(86)
    static let shadowRadius = CGFloat(13)
    static let shadowYOffset = CGFloat(6)
    static let horizontalPadding = shadowRadius
    static let verticalPadding = shadowRadius + abs(shadowYOffset)
    static let contentSpacing = CGFloat(8)
    static let compactPanelSize = NSSize(
        width: pillSize.width + (horizontalPadding * 2),
        height: pillSize.height + (verticalPadding * 2)
    )
    static let previewPanelSize = NSSize(
        width: textWidth + (horizontalPadding * 2),
        height: pillSize.height + textHeight + contentSpacing + (verticalPadding * 2)
    )
    static let bottomOffset = CGFloat(38)

    static func panelSize(showsPreviewSpace: Bool) -> NSSize {
        showsPreviewSpace ? previewPanelSize : compactPanelSize
    }
}

struct VoiceLevelOverlayView: View {
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var meter: VoiceLevelMeter
    @ObservedObject var preview: LiveTranscriptionPreview
    let showsPreviewSpace: Bool

    var body: some View {
        ZStack(alignment: .bottom) {
            VStack(spacing: VoiceLevelOverlayLayout.contentSpacing) {
                if showsPreviewSpace && !preview.text.isEmpty {
                    Text(preview.text)
                        .font(.system(size: 14, weight: .medium))
                        .lineLimit(3)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(textColor)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .frame(
                            width: VoiceLevelOverlayLayout.textWidth,
                            height: VoiceLevelOverlayLayout.textHeight
                        )
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(textBackgroundColor)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .stroke(borderColor, lineWidth: 1)
                        )
                        .shadow(
                            color: shadowColor,
                            radius: VoiceLevelOverlayLayout.shadowRadius,
                            y: VoiceLevelOverlayLayout.shadowYOffset
                        )
                }

                levelMeter
            }
            .padding(.horizontal, VoiceLevelOverlayLayout.horizontalPadding)
            .padding(.bottom, VoiceLevelOverlayLayout.verticalPadding)
        }
        .frame(
            width: VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: showsPreviewSpace).width,
            height: VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: showsPreviewSpace).height,
            alignment: .bottom
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(meter.captureState == .recording
            ? "Recording \(meter.recordingDuration)"
            : meter.captureState == .transcribing
                ? "Transcribing \(meter.transcribingDuration)"
                : meter.captureState.label))
        .accessibilityValue(Text(showsPreviewSpace ? preview.text : ""))
    }

    private var levelMeter: some View {
        HStack(spacing: 8) {
            if meter.captureState == .recording {
                Text(meter.recordingDuration)
                    .font(.system(size: 12, weight: .semibold))
                    .monospacedDigit()
                    .fixedSize()
                waveform
            } else {
                ProgressView()
                    .controlSize(.small)
                Text(meter.captureState.label)
                    .font(.system(size: 12, weight: .semibold))
                if meter.captureState == .transcribing {
                    Text(meter.transcribingDuration)
                        .font(.system(size: 12, weight: .semibold))
                        .monospacedDigit()
                        .fixedSize()
                }
            }
        }
        .foregroundStyle(statusColor)
        .padding(.horizontal, 14)
        .frame(width: VoiceLevelOverlayLayout.pillSize.width, height: VoiceLevelOverlayLayout.pillSize.height)
        .background(Capsule().fill(statusColor.opacity(isLightMode ? 0.10 : 0.14)))
        .background(Capsule().fill(backgroundColor))
        .overlay(Capsule().stroke(statusColor.opacity(0.55), lineWidth: 1))
        .shadow(
            color: shadowColor,
            radius: VoiceLevelOverlayLayout.shadowRadius,
            y: VoiceLevelOverlayLayout.shadowYOffset
        )
    }

    private var waveform: some View {
        HStack(alignment: .center, spacing: 2) {
            ForEach(Array(meter.amplitudes.enumerated()), id: \.offset) { _, amplitude in
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                statusColor.opacity(0.65),
                                statusColor
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(maxWidth: .infinity)
                    .frame(height: max(6, 30 * amplitude))
                    .animation(.easeOut(duration: 0.11), value: amplitude)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var isLightMode: Bool {
        colorScheme == .light
    }

    private var backgroundColor: Color {
        isLightMode ? Color.white.opacity(0.88) : Color.black.opacity(0.42)
    }

    private var textBackgroundColor: Color {
        isLightMode ? Color.white.opacity(0.94) : Color.black.opacity(0.58)
    }

    private var textColor: Color {
        isLightMode ? Color.black.opacity(0.86) : Color.white.opacity(0.92)
    }

    private var borderColor: Color {
        isLightMode ? Color.black.opacity(0.12) : Color.white.opacity(0.22)
    }

    private var shadowColor: Color {
        Color.black.opacity(isLightMode ? 0.16 : 0.24)
    }

    private var statusColor: Color {
        if meter.captureState == .transcribing {
            return isLightMode
                ? Color(red: 0.10, green: 0.32, blue: 0.70)
                : Color(red: 0.45, green: 0.72, blue: 1.0)
        }
        if meter.captureState == .recording {
            return isLightMode
                ? Color(red: 0.04, green: 0.40, blue: 0.18)
                : Color(red: 0.42, green: 0.91, blue: 0.58)
        }
        return isLightMode
            ? Color(red: 0.62, green: 0.34, blue: 0.0)
            : Color(red: 1.0, green: 0.74, blue: 0.25)
    }
}

final class VoiceLevelOverlayController {
    static let shared = VoiceLevelOverlayController()

    private var panel: NSPanel?
    private var showsPreviewSpace = false
    private var recordingShowsPreviewSpace = false
    private var isRecording = false
    private var isTranscribing = false

    private init() {}

    func show(showsPreviewSpace: Bool = false) {
        isRecording = true
        recordingShowsPreviewSpace = showsPreviewSpace
        let panel = panel ?? makePanel()
        self.panel = panel
        setPreviewSpace(showsPreviewSpace, for: panel)
        VoiceLevelMeter.shared.start()
        panel.orderFrontRegardless()
    }

    func hide() {
        isRecording = false
        isTranscribing = false
        VoiceLevelMeter.shared.stop()
        panel?.orderOut(nil)
    }

    func showTranscribing() {
        isTranscribing = true
        let panel = panel ?? makePanel()
        self.panel = panel
        VoiceLevelMeter.shared.beginTranscribing()
        setPreviewSpace(false, for: panel)
        panel.orderFrontRegardless()
    }

    func finishTranscribing() {
        guard isTranscribing else { return }
        isTranscribing = false
        if isRecording {
            if let panel {
                setPreviewSpace(recordingShowsPreviewSpace, for: panel)
            }
            VoiceLevelMeter.shared.resumeRecording()
        } else {
            hide()
        }
    }

    func endRecording() {
        isRecording = false
        if isTranscribing {
            VoiceLevelMeter.shared.beginTranscribing()
            if let panel {
                setPreviewSpace(false, for: panel)
            }
        } else {
            hide()
        }
    }

    private func makePanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(
                origin: .zero,
                size: VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: showsPreviewSpace)
            ),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        updatePanelContent(panel)
        return panel
    }

    private func setPreviewSpace(_ showsPreviewSpace: Bool, for panel: NSPanel) {
        if self.showsPreviewSpace != showsPreviewSpace {
            self.showsPreviewSpace = showsPreviewSpace
            updatePanelContent(panel)
        }
        panel.setContentSize(VoiceLevelOverlayLayout.panelSize(showsPreviewSpace: showsPreviewSpace))
        position(panel)
    }

    private func updatePanelContent(_ panel: NSPanel) {
        panel.contentView = NSHostingView(rootView: VoiceLevelOverlayView(
            meter: VoiceLevelMeter.shared,
            preview: LiveTranscriptionPreview.shared,
            showsPreviewSpace: showsPreviewSpace
        ))
    }

    private func position(_ panel: NSPanel) {
        guard let screen = NSScreen.main ?? NSScreen.screens.first else { return }
        let frame = screen.visibleFrame
        let y = frame.minY
            + VoiceLevelOverlayLayout.bottomOffset
            - VoiceLevelOverlayLayout.verticalPadding
        panel.setFrameOrigin(
            NSPoint(
                x: frame.midX - panel.frame.width / 2,
                y: y
            )
        )
    }
}

enum VoiceLevelLog {
    static let defaultLogPath = "~/.config/agent-cli/voice-levels.jsonl"
    static var defaultLogURL: URL {
        URL(fileURLWithPath: NSString(string: defaultLogPath).expandingTildeInPath)
    }

    private static let maximumFreshness: TimeInterval = 1.5
    private static let maximumTailBytes = 16 * 1024

    static func reset(_ url: URL = defaultLogURL) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try "".write(to: url, atomically: true, encoding: .utf8)
        } catch {
            try? FileManager.default.removeItem(at: url)
        }
    }

    static func latestLevel(
        from url: URL = defaultLogURL,
        now: Date = Date(),
        maxAge: TimeInterval = maximumFreshness
    ) -> CGFloat? {
        for line in recentLines(from: url) {
            guard let sample = parseLine(line) else { continue }
            let age = now.timeIntervalSince(sample.timestamp)
            guard age >= 0, age <= maxAge else { return nil }
            return sample.level
        }
        return nil
    }

    private static func recentLines(from url: URL) -> [String] {
        guard let file = try? FileHandle(forReadingFrom: url) else {
            return []
        }
        defer { try? file.close() }

        do {
            let fileSize = try file.seekToEnd()
            guard fileSize > 0 else { return [] }

            let bytesToRead = min(fileSize, UInt64(maximumTailBytes))
            try file.seek(toOffset: fileSize - bytesToRead)
            guard let data = try file.readToEnd(),
                  let text = String(data: data, encoding: .utf8) else {
                return []
            }
            return text
                .split(whereSeparator: { $0.isNewline })
                .reversed()
                .map(String.init)
        } catch {
            return []
        }
    }

    private static func parseLine(_ line: String) -> (timestamp: Date, level: CGFloat)? {
        let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedLine.isEmpty,
              let data = trimmedLine.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let timestampText = object["timestamp"] as? String,
              let timestamp = parseTimestamp(timestampText),
              let rawLevel = object["level"] as? Double else {
            return nil
        }

        return (timestamp, CGFloat(max(0, min(1, rawLevel))))
    }

    private static func parseTimestamp(_ text: String) -> Date? {
        if let date = iso8601WithFractionalSeconds.date(from: text) {
            return date
        }
        return iso8601.date(from: text)
    }

    private static let iso8601WithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

enum VoiceCaptureState {
    case idle
    case connecting
    case recording
    case waitingForAudio
    case transcribing

    var label: String {
        switch self {
        case .idle: return "Ready"
        case .connecting: return "Connecting…"
        case .recording: return "Recording"
        case .waitingForAudio: return "Waiting for audio…"
        case .transcribing: return "Transcribing…"
        }
    }
}

final class VoiceLevelMeter: ObservableObject {
    static let shared = VoiceLevelMeter()

    @Published private(set) var amplitudes = VoiceLevelMeter.idleAmplitudes
    @Published private(set) var captureState = VoiceCaptureState.idle
    @Published private(set) var recordingDuration = "00:00"
    @Published private(set) var transcribingDuration = "00:00"

    private static let barCount = 16
    private static let idleAmplitudes = Array(repeating: CGFloat(0.16), count: barCount)
    private static let idleLevel = CGFloat(0.16)
    private static let minimumDisplayAmplitude = CGFloat(0.12)
    private static let pollInterval: TimeInterval = 0.06
    private let levelLogURL: URL
    private let now: () -> Date
    private var timer: Timer?
    private var recordingStartedAt: Date?
    private var transcribingStartedAt: Date?
    private var phase = 0.0
    private var smoothedLevel = CGFloat(0.16)

    init(levelLogURL: URL = VoiceLevelLog.defaultLogURL, now: @escaping () -> Date = Date.init) {
        self.levelLogURL = levelLogURL
        self.now = now
    }

    func start() {
        guard timer == nil || captureState == .transcribing else { return }
        VoiceLevelLog.reset(levelLogURL)
        captureState = .connecting
        recordingStartedAt = nil
        recordingDuration = "00:00"
        transcribingStartedAt = nil
        transcribingDuration = "00:00"
        phase = 0
        smoothedLevel = Self.idleLevel
        amplitudes = Self.idleAmplitudes
        startPolling()
    }

    private func startPolling() {
        timer?.invalidate()
        let timer = Timer(timeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            self?.pollLevel()
        }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
        pollLevel()
    }

    func resumeRecording() {
        guard captureState == .transcribing else { return }
        transcribingStartedAt = nil
        captureState = recordingStartedAt == nil ? .connecting : .waitingForAudio
        startPolling()
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        captureState = .idle
        transcribingStartedAt = nil
        transcribingDuration = "00:00"
        recordingStartedAt = nil
        recordingDuration = "00:00"
        phase = 0
        smoothedLevel = Self.idleLevel
        amplitudes = Self.idleAmplitudes
    }

    func beginTranscribing() {
        guard captureState != .transcribing else { return }
        transcribingStartedAt = now()
        transcribingDuration = "00:00"
        captureState = .transcribing
        amplitudes = Self.idleAmplitudes
        startPolling()
    }

    func pollLevel() {
        guard timer != nil else { return }
        let now = now()
        if captureState == .transcribing {
            let elapsed = max(0, Int(now.timeIntervalSince(transcribingStartedAt ?? now)))
            transcribingDuration = String(format: "%02d:%02d", elapsed / 60, elapsed % 60)
            return
        }
        guard let level = VoiceLevelLog.latestLevel(from: levelLogURL, now: now) else {
            if captureState == .recording {
                captureState = .waitingForAudio
            }
            amplitudes = Self.idleAmplitudes
            return
        }
        captureState = .recording
        let startedAt = recordingStartedAt ?? now
        recordingStartedAt = startedAt
        let elapsedSeconds = max(0, Int(now.timeIntervalSince(startedAt)))
        recordingDuration = String(format: "%02d:%02d", elapsedSeconds / 60, elapsedSeconds % 60)
        updateDisplay(level: level)
    }

    private func updateDisplay(level: CGFloat) {
        phase += 0.22
        smoothedLevel = (smoothedLevel * 0.55) + (level * 0.45)
        let displayLevel = smoothedLevel

        amplitudes = Self.displayAmplitudes(level: displayLevel, phase: phase)
    }

    static func displayAmplitudes(level: CGFloat, phase: Double) -> [CGFloat] {
        (0..<Self.barCount).map { index in
            let wave = 0.74 + 0.26 * sin(phase + Double(index) * 0.74)
            return max(Self.minimumDisplayAmplitude, min(1, level * CGFloat(wave)))
        }
    }
}
