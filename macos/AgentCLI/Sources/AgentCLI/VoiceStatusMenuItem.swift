import AppKit
import SwiftUI

@MainActor
struct VoiceStatusMenuItem: NSViewRepresentable {
    let runner: AgentCommandRunner

    func makeCoordinator() -> Coordinator {
        Coordinator(runner: runner)
    }

    func makeNSView(context: Context) -> NSTextField {
        let textField = NSTextField(labelWithString: "")
        textField.lineBreakMode = .byTruncatingTail
        textField.maximumNumberOfLines = 1
        textField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        context.coordinator.attach(textField)
        return textField
    }

    func updateNSView(_ textField: NSTextField, context: Context) {
        context.coordinator.attach(textField)
    }

    @MainActor
    final class Coordinator {
        private let runner: AgentCommandRunner
        private weak var textField: NSTextField?
        private var timer: Timer?

        init(runner: AgentCommandRunner) {
            self.runner = runner
        }

        deinit {
            timer?.invalidate()
        }

        func attach(_ textField: NSTextField) {
            self.textField = textField
            refreshStatus()
            startTimer()
        }

        private func startTimer() {
            guard timer == nil else { return }
            let timer = Timer(timeInterval: 0.8, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    self?.refreshStatus()
                }
            }
            RunLoop.main.add(timer, forMode: .common)
            self.timer = timer
        }

        private func refreshStatus() {
            textField?.stringValue = "Voice: \(runner.menuStatusMessage)"
        }
    }
}
