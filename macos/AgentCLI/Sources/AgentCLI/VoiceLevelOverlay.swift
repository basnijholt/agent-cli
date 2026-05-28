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
    private let minimumPower: Float = -55
    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private var phase = 0.0
    private var smoothedLevel = CGFloat(0.16)

    private override init() {}

    func start() {
        guard recorder == nil else { return }

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
        timer?.invalidate()
        timer = nil
        recorder?.stop()
        recorder = nil
        smoothedLevel = 0.16
        amplitudes = Self.idleAmplitudes
    }

    private func startMetering() {
        smoothedLevel = 0.16
        let url = URL(fileURLWithPath: "/dev/null")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatAppleLossless),
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.min.rawValue
        ]

        do {
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.isMeteringEnabled = true
            guard recorder.record() else {
                amplitudes = Self.idleAmplitudes
                return
            }
            self.recorder = recorder
            timer = Timer.scheduledTimer(withTimeInterval: 0.06, repeats: true) { [weak self] _ in
                self?.updateMeter()
            }
        } catch {
            amplitudes = Self.idleAmplitudes
        }
    }

    private func updateMeter() {
        guard let recorder else { return }
        recorder.updateMeters()

        let power = recorder.averagePower(forChannel: 0)
        let normalized = Self.normalizedPower(power, minimumPower: minimumPower)
        phase += 0.22
        smoothedLevel = (smoothedLevel * 0.55) + (normalized * 0.45)
        let displayLevel = smoothedLevel

        amplitudes = (0..<Self.barCount).map { index in
            let wave = 0.74 + 0.26 * sin(phase + Double(index) * 0.74)
            return max(0.12, min(1, displayLevel * CGFloat(wave)))
        }
    }

    private static func normalizedPower(_ power: Float, minimumPower: Float) -> CGFloat {
        guard power > minimumPower else { return 0.08 }
        return CGFloat((power - minimumPower) / abs(minimumPower))
    }
}
