#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class RecordingIndicatorControllerTests: XCTestCase {
    func testRecordingSoundsAreDisabledByDefault() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-default")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-default")
        let player = RecordingCuePlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, audioCuePlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.end(for: .toggleTranscription)

        XCTAssertEqual(player.events, [])
    }

    func testRecordingSoundsPlayStartAndFinishWhenEnabled() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-enabled")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-enabled")
        defaults.set(true, forKey: RecordingSoundSettings.enabledKey)
        let player = RecordingCuePlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, audioCuePlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.end(for: .toggleTranscription)

        XCTAssertEqual(player.events, [.startedRecording, .finishedRecording])
    }

    func testFinishSoundPlaysOnlyWhenAllRecordingCommandsHaveEnded() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.recording-sounds-nested")!
        defaults.removePersistentDomain(forName: "AgentCLITests.recording-sounds-nested")
        defaults.set(true, forKey: RecordingSoundSettings.enabledKey)
        let player = RecordingCuePlayerSpy()
        let controller = RecordingIndicatorController(defaults: defaults, audioCuePlayer: player)

        controller.begin(for: .toggleTranscription)
        controller.begin(for: .voiceEdit)
        controller.end(for: .toggleTranscription)
        XCTAssertEqual(player.events, [.startedRecording])

        controller.end(for: .voiceEdit)
        XCTAssertEqual(player.events, [.startedRecording, .finishedRecording])
    }
}

private final class RecordingCuePlayerSpy: RecordingCuePlaying {
    private(set) var events: [RecordingSoundEvent] = []

    func play(_ event: RecordingSoundEvent) {
        events.append(event)
    }
}
#endif
