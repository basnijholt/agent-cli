import SwiftUI

/// Preparation is separate from recording: a released shortcut must never imply
/// audio was captured while the runtime or model was still being set up.
struct VoicePreparationOverlayView: View {
    let phase: BootstrapPhase
    let startedAt: Date
    let showDetails: () -> Void
    let dismiss: () -> Void
    var minimize: () -> Void = {}

    static let panelSize = CGSize(width: 420, height: 208)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                if phase.isPreparing {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: phase == .failed ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                        .foregroundStyle(phase == .failed ? Color.orange : Color.green)
                }
                Text(title).font(.headline)
                Spacer()
                if phase.isPreparing {
                    TimelineView(.periodic(from: startedAt, by: 1)) { context in
                        let elapsed = max(0, Int(context.date.timeIntervalSince(startedAt)))
                        Text(String(format: "%02d:%02d", elapsed / 60, elapsed % 60))
                            .monospacedDigit().foregroundStyle(.secondary)
                    }
                }
                Button(action: minimize) {
                    Image(systemName: "minus").frame(width: 18, height: 18)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Minimize to menu bar")
                .help("Minimize to menu bar. Restore with Show Voice Setup…")
            }
            Text(detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            HStack {
                Label("Not recording", systemImage: "mic.slash")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Details…", action: showDetails)
                Button("Dismiss", action: dismiss)
            }
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(.primary.opacity(0.12)))
        .padding(14)
        .frame(width: Self.panelSize.width, height: Self.panelSize.height)
    }

    private var title: String {
        switch phase {
        case .checkingRuntime: return "Checking voice setup"
        case .installingRuntime: return "Installing voice tools"
        case .installingVoiceService: return "Setting up speech recognition"
        case .waitingForVoiceService: return "Starting voice service"
        case .warmingWhisperModel: return "Preparing speech model"
        case .idle: return "Ready to record"
        case .failed: return "Voice setup failed"
        }
    }

    private var detail: String {
        switch phase {
        case .checkingRuntime:
            return "Checking the tools needed for recording. Wait until setup finishes before speaking."
        case .installingRuntime:
            return "Downloading and installing the app's voice tools. First setup needs internet and can take several minutes."
        case .installingVoiceService:
            return "Installing speech recognition dependencies. First setup needs internet and can take several minutes."
        case .waitingForVoiceService:
            return "Waiting for the local speech service to become available. Open Details if setup does not finish."
        case .warmingWhisperModel:
            return "Downloading the speech model if needed, then loading it. First use can take several minutes."
        case .idle:
            return "Use your recording shortcut again when you're ready to speak. Hold-to-transcribe records only while you hold the key."
        case .failed:
            return "Open Details to view the last error and voice service controls, then try recording again."
        }
    }
}
