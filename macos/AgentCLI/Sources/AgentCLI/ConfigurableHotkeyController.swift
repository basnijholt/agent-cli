import Foundation
import KeyboardShortcuts

final class ConfigurableHotkeyController {
    static let shared = ConfigurableHotkeyController()

    private var registered = false

    private init() {}

    func registerDefaultHotkeys(runner: AgentCommandRunner) {
        guard !registered else { return }

        KeyboardShortcuts.onKeyUp(for: .toggleTranscription) {
            Task { @MainActor in runner.run(.toggleTranscription) }
        }
        KeyboardShortcuts.onKeyDown(for: .holdToTranscribe) {
            Task { @MainActor in runner.beginHoldToTranscribe() }
        }
        KeyboardShortcuts.onKeyUp(for: .holdToTranscribe) {
            Task { @MainActor in runner.endHoldToTranscribe() }
        }
        KeyboardShortcuts.onKeyUp(for: .autocorrect) {
            Task { @MainActor in runner.run(.autocorrect) }
        }
        KeyboardShortcuts.onKeyUp(for: .voiceEdit) {
            Task { @MainActor in runner.run(.voiceEdit) }
        }

        registered = true
    }
}
