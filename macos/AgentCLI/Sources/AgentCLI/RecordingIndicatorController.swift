import Foundation

final class RecordingIndicatorController {
    private var recordingCommandCount = 0
    private var activeRecordingCommands: [String: Int] = [:]
    private let defaults: UserDefaults
    private let audioCuePlayer: RecordingCuePlaying

    init(
        defaults: UserDefaults = .standard,
        audioCuePlayer: RecordingCuePlaying = NativeRecordingCuePlayer.shared
    ) {
        self.defaults = defaults
        self.audioCuePlayer = audioCuePlayer
    }

    var isRecording: Bool {
        recordingCommandCount > 0
    }

    func isRecordingCommand(_ command: AgentCommand) -> Bool {
        activeRecordingCommands[command.identifier, default: 0] > 0
    }

    func begin(for command: AgentCommand) {
        let wasRecording = isRecording
        activeRecordingCommands[command.identifier, default: 0] += 1
        recordingCommandCount += 1
        if !wasRecording {
            play(.startedRecording)
        }
        let showsLivePreview = command.supportsLivePreviewOverlay
            && TranscriptionSettings.isLivePreviewOverlayEnabled(defaults: defaults)
        if showsLivePreview {
            LiveTranscriptionPreview.shared.start()
        }
        VoiceLevelOverlayController.shared.show(showsPreviewSpace: showsLivePreview)
    }

    func end(for command: AgentCommand) {
        let wasRecording = isRecording
        let activeCommandCount = max(0, activeRecordingCommands[command.identifier, default: 0] - 1)
        if activeCommandCount > 0 {
            activeRecordingCommands[command.identifier] = activeCommandCount
        } else {
            activeRecordingCommands.removeValue(forKey: command.identifier)
        }
        recordingCommandCount = max(0, recordingCommandCount - 1)
        if wasRecording && !isRecording {
            play(.finishedRecording)
            VoiceLevelOverlayController.shared.hide()
        }
        if command.supportsLivePreviewOverlay {
            LiveTranscriptionPreview.shared.stop()
        }
    }

    private func play(_ event: RecordingSoundEvent) {
        guard RecordingSoundSettings.isEnabled(defaults: defaults) else { return }
        audioCuePlayer.play(event)
    }
}
