import Foundation

final class RecordingIndicatorController {
    private var recordingCommandCount = 0
    private var activeRecordingCommands: [String: Int] = [:]

    var isRecording: Bool {
        recordingCommandCount > 0
    }

    func isRecordingCommand(_ command: AgentCommand) -> Bool {
        activeRecordingCommands[command.identifier, default: 0] > 0
    }

    func begin(for command: AgentCommand) {
        activeRecordingCommands[command.identifier, default: 0] += 1
        recordingCommandCount += 1
        VoiceLevelOverlayController.shared.show()
    }

    func end(for command: AgentCommand) {
        let activeCommandCount = max(0, activeRecordingCommands[command.identifier, default: 0] - 1)
        if activeCommandCount > 0 {
            activeRecordingCommands[command.identifier] = activeCommandCount
        } else {
            activeRecordingCommands.removeValue(forKey: command.identifier)
        }
        recordingCommandCount = max(0, recordingCommandCount - 1)
        if !isRecording {
            VoiceLevelOverlayController.shared.hide()
        }
    }
}
