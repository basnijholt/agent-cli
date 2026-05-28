#if canImport(Testing)
import Testing
@testable import AgentCLI

@Suite
struct RecordingIndicatorControllerTests {
    @Test
    func recordingSoundsAreDisabledByDefault() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-default")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-default")
        let player = RecordingSoundPlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, soundPlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.end(for: .toggleTranscription)

        #expect(player.events == [])
    }

    @Test
    func recordingSoundsPlayStartAndFinishWhenEnabled() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-enabled")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-enabled")
        defaults.set(true, forKey: RecordingSoundSettings.enabledKey)
        let player = RecordingSoundPlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, soundPlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.end(for: .toggleTranscription)

        #expect(player.events == [.startedRecording, .finishedRecording])
    }

    @Test
    func finishSoundPlaysOnlyWhenAllRecordingCommandsHaveEnded() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-nested")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-nested")
        defaults.set(true, forKey: RecordingSoundSettings.enabledKey)
        let player = RecordingSoundPlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, soundPlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.begin(for: .voiceEdit)
        controller.end(for: .toggleTranscription)
        #expect(player.events == [.startedRecording])

        controller.end(for: .voiceEdit)
        #expect(player.events == [.startedRecording, .finishedRecording])
    }
}

private final class RecordingSoundPlayerSpy: RecordingSoundPlaying {
    private(set) var events: [RecordingSoundEvent] = []

    func play(_ event: RecordingSoundEvent) {
        events.append(event)
    }
}
#endif
