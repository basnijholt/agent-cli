import AppKit
import AVFoundation
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

final class VoiceLevelMeter: NSObject, ObservableObject {
    static let shared = VoiceLevelMeter()

    @Published private(set) var amplitudes = VoiceLevelMeter.idleAmplitudes

    private static let barCount = 16
    private static let idleAmplitudes = Array(repeating: CGFloat(0.16), count: barCount)
    private static let minimumDisplayAmplitude = CGFloat(0.12)
    private static let minimumInputDecibels: Float = -55
    private var engine: AVAudioEngine?
    private var phase = 0.0
    private var smoothedLevel = CGFloat(0.16)

    private override init() {}

    func start() {
        guard engine == nil else { return }

        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            startMetering()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        self?.startMetering()
                    } else {
                        self?.amplitudes = Self.idleAmplitudes
                    }
                }
            }
        default:
            amplitudes = Self.idleAmplitudes
        }
    }

    func stop() {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        phase = 0
        smoothedLevel = 0.16
        amplitudes = Self.idleAmplitudes
    }

    private func startMetering() {
        phase = 0
        smoothedLevel = 0.16
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            amplitudes = Self.idleAmplitudes
            return
        }

        do {
            input.installTap(onBus: 0, bufferSize: 1_024, format: format) { [weak self] buffer, _ in
                self?.process(buffer: buffer)
            }
            try engine.start()
            self.engine = engine
        } catch {
            input.removeTap(onBus: 0)
            amplitudes = Self.idleAmplitudes
        }
    }

    private func process(buffer: AVAudioPCMBuffer) {
        guard let samples = Self.samples(from: buffer) else { return }
        let level = Self.normalizedLevel(from: samples)

        DispatchQueue.main.async { [weak self] in
            guard let self, self.engine != nil else { return }
            self.updateDisplay(level: level)
        }
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

    static func normalizedLevel(from samples: [Float]) -> CGFloat {
        guard !samples.isEmpty else { return 0.08 }

        let meanSquare = samples.reduce(0.0) { partialResult, sample in
            let value = Double(sample)
            return partialResult + (value * value)
        } / Double(samples.count)
        guard meanSquare > 0 else { return 0.08 }

        let rootMeanSquare = sqrt(meanSquare)
        let decibels = Float(20 * log10(rootMeanSquare))
        return normalizedPower(decibels, minimumPower: minimumInputDecibels)
    }

    private static func normalizedPower(_ power: Float, minimumPower: Float) -> CGFloat {
        guard power > minimumPower else { return 0.08 }
        let linearLevel = CGFloat((power - minimumPower) / abs(minimumPower))
        return CGFloat(sqrt(Double(linearLevel)))
    }

    private static func samples(from buffer: AVAudioPCMBuffer) -> [Float]? {
        guard let channelData = buffer.floatChannelData else { return nil }
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return nil }

        let channelCount = Int(buffer.format.channelCount)
        guard channelCount > 0 else { return nil }

        if channelCount == 1 {
            return Array(UnsafeBufferPointer(start: channelData[0], count: frameLength))
        }

        if buffer.format.isInterleaved {
            return (0..<frameLength).map { frameIndex in
                var mixedSample = Float(0)
                let sampleIndex = frameIndex * channelCount
                for channelIndex in 0..<channelCount {
                    mixedSample += channelData[0][sampleIndex + channelIndex]
                }
                return mixedSample / Float(channelCount)
            }
        }

        return (0..<frameLength).map { frameIndex in
            var mixedSample = Float(0)
            for channelIndex in 0..<channelCount {
                mixedSample += channelData[channelIndex][frameIndex]
            }
            return mixedSample / Float(channelCount)
        }
    }
}
