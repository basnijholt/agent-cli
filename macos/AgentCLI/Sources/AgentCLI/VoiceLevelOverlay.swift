import AppKit
import AVFoundation
import Foundation
import SwiftUI

struct VoiceLevelOverlayView: View {
    @ObservedObject var meter: VoiceLevelMeter

    var body: some View {
        HStack(alignment: .center, spacing: 3.5) {
            ForEach(Array(meter.amplitudes.enumerated()), id: \.offset) { _, amplitude in
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.18, green: 0.82, blue: 0.92),
                                Color(red: 0.64, green: 0.96, blue: 0.58)
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(width: 3.5, height: max(5, 25 * amplitude))
                    .animation(.easeOut(duration: 0.11), value: amplitude)
            }
        }
        .frame(width: 147, height: 38)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.white.opacity(0.22), lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(0.24), radius: 13, y: 6)
        .accessibilityLabel(Text("Voice level"))
    }
}

final class VoiceLevelOverlayController {
    static let shared = VoiceLevelOverlayController()

    private let panelSize = NSSize(width: 154, height: 41)
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
        panel.setFrameOrigin(
            NSPoint(
                x: frame.midX - panelSize.width / 2,
                y: frame.minY + 38
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
    private var engine: AVAudioEngine?
    private var analyzer: VoiceSpectrumAnalyzer?
    private var smoothedAmplitudes = VoiceLevelMeter.idleAmplitudes

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
        analyzer = nil
        smoothedAmplitudes = Self.idleAmplitudes
        amplitudes = Self.idleAmplitudes
    }

    private func startMetering() {
        smoothedAmplitudes = Self.idleAmplitudes
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            amplitudes = Self.idleAmplitudes
            return
        }
        let analyzer = VoiceSpectrumAnalyzer(
            sampleRate: format.sampleRate,
            bandCount: Self.barCount
        )

        do {
            input.installTap(onBus: 0, bufferSize: 1_024, format: format) { [weak self] buffer, _ in
                self?.process(buffer: buffer)
            }
            try engine.start()
            self.analyzer = analyzer
            self.engine = engine
        } catch {
            input.removeTap(onBus: 0)
            amplitudes = Self.idleAmplitudes
        }
    }

    private func process(buffer: AVAudioPCMBuffer) {
        guard let analyzer, let samples = Self.samples(from: buffer) else { return }
        let rawAmplitudes = analyzer.amplitudes(from: samples)

        DispatchQueue.main.async { [weak self] in
            guard let self, self.engine != nil else { return }
            self.amplitudes = self.smoothedDisplayAmplitudes(from: rawAmplitudes)
        }
    }

    private func smoothedDisplayAmplitudes(from rawAmplitudes: [CGFloat]) -> [CGFloat] {
        smoothedAmplitudes = zip(smoothedAmplitudes, rawAmplitudes).map { previous, current in
            let smoothed = (previous * 0.62) + (current * 0.38)
            return max(Self.minimumDisplayAmplitude, min(1, smoothed))
        }
        return smoothedAmplitudes
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
