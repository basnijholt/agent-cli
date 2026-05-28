import Foundation
import KeyboardShortcuts

final class ConfigurableHotkeyController {
    static let shared = ConfigurableHotkeyController()

    private var registered = false

    private init() {}

    func registerDefaultHotkeys(runner: AgentCommandRunner) {
        guard !registered else { return }

        KeyboardShortcuts.onKeyUp(for: .toggleTranscription) {
            runner.run(.toggleTranscription)
        }
        KeyboardShortcuts.onKeyDown(for: .holdToTranscribe) {
            runner.beginHoldToTranscribe()
        }
        KeyboardShortcuts.onKeyUp(for: .holdToTranscribe) {
            runner.endHoldToTranscribe()
        }
        KeyboardShortcuts.onKeyUp(for: .autocorrect) {
            runner.run(.autocorrect)
        }
        KeyboardShortcuts.onKeyUp(for: .voiceEdit) {
            runner.run(.voiceEdit)
        }

        registered = true
    }
}
