#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class StopRecordingTests: XCTestCase {
    @MainActor
    func testMenuNamesAndStopsClipboardRecording() async {
        let fixture = RecordingCommandFixture()
        let runner = makeRunner(fixture)
        defer { fixture.finish(); VoiceLevelOverlayController.shared.hide() }
        XCTAssertFalse(runner.canStopRecording)

        XCTAssertTrue(runner.run(.toggleTranscription))
        await fulfillment(of: [fixture.started], timeout: 2)
        XCTAssertTrue(runner.menuStatusMessage.hasPrefix("Record to Clipboard — Recording"), runner.menuStatusMessage)
        XCTAssertTrue(runner.canStopRecording)

        runner.stopRecording()
        XCTAssertTrue(runner.menuStatusMessage.hasPrefix("Record to Clipboard — Transcribing"), runner.menuStatusMessage)
        XCTAssertFalse(runner.canStopRecording, "A requested stop must not be offered again.")
        await fulfillment(of: [fixture.stopped], timeout: 2)
        await waitUntilFinished(runner)
        XCTAssertEqual(fixture.commandCount, 2, "One recording start and one stop.")
        XCTAssertFalse(runner.isRecording)
        XCTAssertEqual(fixture.pastedTranscripts, [], "Clipboard recordings must not paste into the focused field.")
    }

    @MainActor
    func testMenuStopsHoldToTranscribeLikeReleasingTheKey() async {
        let fixture = RecordingCommandFixture()
        let runner = makeRunner(fixture)
        defer { fixture.finish(); VoiceLevelOverlayController.shared.hide() }

        XCTAssertTrue(runner.beginHoldToTranscribe())
        await fulfillment(of: [fixture.started], timeout: 2)
        XCTAssertTrue(runner.menuStatusMessage.hasPrefix("Hold to Transcribe — Recording"), runner.menuStatusMessage)
        XCTAssertTrue(runner.canStopRecording)

        runner.stopRecording()
        XCTAssertTrue(runner.menuStatusMessage.hasPrefix("Hold to Transcribe — Transcribing"), runner.menuStatusMessage)
        XCTAssertFalse(runner.canStopRecording, "A requested stop must not be offered again.")
        runner.endHoldToTranscribe() // Releasing the key afterwards must not stop twice.
        await fulfillment(of: [fixture.stopped], timeout: 2)
        await waitUntilFinished(runner)
        XCTAssertEqual(fixture.commandCount, 2, "One recording start and one stop.")
        XCTAssertEqual(fixture.pastedTranscripts, ["Fixture transcript"], "A stopped hold still inserts its transcript.")
    }

    @MainActor
    func testLatchedHoldIsNamedAsClipboardRecording() async {
        let fixture = RecordingCommandFixture()
        let runner = makeRunner(fixture)
        defer { fixture.finish(); VoiceLevelOverlayController.shared.hide() }

        XCTAssertTrue(runner.beginHoldToTranscribe())
        await fulfillment(of: [fixture.started], timeout: 2)
        XCTAssertTrue(runner.latchHoldToTranscribe())
        XCTAssertTrue(runner.menuStatusMessage.hasPrefix("Record to Clipboard — Recording"), runner.menuStatusMessage)

        runner.stopRecording()
        await fulfillment(of: [fixture.stopped], timeout: 2)
        await waitUntilFinished(runner)
        XCTAssertEqual(fixture.commandCount, 2, "One recording start and one stop.")
        XCTAssertEqual(fixture.pastedTranscripts, [])
    }

    @MainActor
    private func makeRunner(_ fixture: RecordingCommandFixture) -> AgentCommandRunner {
        AgentCommandRunner(
            pasteController: fixture,
            bootstrap: { _, _, _ in CommandResult(exitCode: 0, output: "") },
            recordingPermissionCheck: { true },
            sendNotification: { _ in },
            runCommand: fixture.run
        )
    }

    @MainActor
    private func waitUntilFinished(_ runner: AgentCommandRunner) async {
        let deadline = Date().addingTimeInterval(2)
        while runner.isRunning && Date() < deadline {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertFalse(runner.isRunning, "Recording should finish after it is stopped.")
    }
}
#endif
