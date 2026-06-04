import AppKit
import Foundation
import SwiftUI

enum VoiceLevelOverlayLayout {
    static let pillSize = CGSize(width: 147, height: 38)
    static let shadowRadius = CGFloat(13)
    static let shadowYOffset = CGFloat(6)
    static let horizontalPadding = shadowRadius
    static let verticalPadding = shadowRadius + abs(shadowYOffset)
    static let panelSize = NSSize(
        width: pillSize.width + (horizontalPadding * 2),
        height: pillSize.height + (verticalPadding * 2)
    )
    static let bottomOffset = CGFloat(38)
}

struct VoiceLevelOverlayView: View {
    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject var meter: VoiceLevelMeter

    var body: some View {
        HStack(alignment: .center, spacing: 3.5) {
            ForEach(Array(meter.amplitudes.enumerated()), id: \.offset) { _, amplitude in
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                barGradientStart,
                                barGradientEnd
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(width: 3.5, height: max(5, 25 * amplitude))
                    .animation(.easeOut(duration: 0.11), value: amplitude)
            }
        }
        .frame(width: VoiceLevelOverlayLayout.pillSize.width, height: VoiceLevelOverlayLayout.pillSize.height)
        .background(
            Capsule()
                .fill(backgroundColor)
        )
        .overlay(
            Capsule()
                .stroke(borderColor, lineWidth: 1)
        )
        .shadow(
            color: shadowColor,
            radius: VoiceLevelOverlayLayout.shadowRadius,
            y: VoiceLevelOverlayLayout.shadowYOffset
        )
        .padding(.horizontal, VoiceLevelOverlayLayout.horizontalPadding)
        .padding(.vertical, VoiceLevelOverlayLayout.verticalPadding)
        .accessibilityLabel(Text("Voice level"))
    }

    private var isLightMode: Bool {
        colorScheme == .light
    }

    private var backgroundColor: Color {
        isLightMode ? Color.white.opacity(0.88) : Color.black.opacity(0.42)
    }

    private var borderColor: Color {
        isLightMode ? Color.black.opacity(0.12) : Color.white.opacity(0.22)
    }

    private var shadowColor: Color {
        Color.black.opacity(isLightMode ? 0.16 : 0.24)
    }

    private var barGradientStart: Color {
        isLightMode ? Color(red: 0.04, green: 0.45, blue: 0.95) : Color(red: 0.18, green: 0.82, blue: 0.92)
    }

    private var barGradientEnd: Color {
        isLightMode ? Color(red: 0.07, green: 0.72, blue: 0.68) : Color(red: 0.64, green: 0.96, blue: 0.58)
    }
}

final class VoiceLevelOverlayController {
    static let shared = VoiceLevelOverlayController()

    private let panelSize = VoiceLevelOverlayLayout.panelSize
    private var panel: NSPanel?

    private init() {}

    func show() {
        let panel = panel ?? makePanel()
        self.panel = panel
        position(panel)
        VoiceLevelMeter.shared.start()
        panel.orderFrontRegardless()
    }

    func hide() {
        VoiceLevelMeter.shared.stop()
        panel?.orderOut(nil)
    }

    private func makePanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
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
        panel.contentView = NSHostingView(rootView: VoiceLevelOverlayView(meter: VoiceLevelMeter.shared))
        return panel
    }

    private func position(_ panel: NSPanel) {
        guard let screen = NSScreen.main ?? NSScreen.screens.first else { return }
        let frame = screen.visibleFrame
        let y = frame.minY
            + VoiceLevelOverlayLayout.bottomOffset
            - VoiceLevelOverlayLayout.verticalPadding
        panel.setFrameOrigin(
            NSPoint(
                x: frame.midX - panelSize.width / 2,
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

final class VoiceLevelMeter: ObservableObject {
    static let shared = VoiceLevelMeter()

    @Published private(set) var amplitudes = VoiceLevelMeter.idleAmplitudes

    private static let barCount = 16
    private static let idleAmplitudes = Array(repeating: CGFloat(0.16), count: barCount)
    private static let idleLevel = CGFloat(0.16)
    private static let minimumDisplayAmplitude = CGFloat(0.12)
    private static let pollInterval: TimeInterval = 0.06
    private let levelLogURL: URL
    private let now: () -> Date
    private var timer: Timer?
    private var phase = 0.0
    private var smoothedLevel = CGFloat(0.16)

    init(levelLogURL: URL = VoiceLevelLog.defaultLogURL, now: @escaping () -> Date = Date.init) {
        self.levelLogURL = levelLogURL
        self.now = now
    }

    func start() {
        guard timer == nil else { return }
        VoiceLevelLog.reset(levelLogURL)
        phase = 0
        smoothedLevel = Self.idleLevel
        amplitudes = Self.idleAmplitudes

        let timer = Timer(timeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            self?.pollLevel()
        }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
        pollLevel()
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        phase = 0
        smoothedLevel = Self.idleLevel
        amplitudes = Self.idleAmplitudes
    }

    private func pollLevel() {
        let level = VoiceLevelLog.latestLevel(from: levelLogURL, now: now()) ?? Self.idleLevel
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
