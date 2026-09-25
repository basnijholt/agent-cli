#if canImport(XCTest)
import AppKit
import SwiftUI
import XCTest
@testable import AgentCLI

final class RecordingPreparationTests: XCTestCase {
    @MainActor
    func testReleasingHoldDuringSetupNeverLaunchesRecordingOrStop() async {
        let setup = PreparationGate(phase: .warmingWhisperModel)
        let runner = makeRunner(setup: setup)
        defer { VoiceLevelOverlayController.shared.hide() }

        XCTAssertTrue(runner.beginHoldToTranscribe())
        await fulfillment(of: [setup.started], timeout: 2)
        runner.endHoldToTranscribe()
        XCTAssertFalse(runner.isRecording)
        XCTAssertNotEqual(VoiceLevelMeter.shared.captureState, .transcribing)

        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertEqual(setup.callCount, 1, "A canceled start must not queue --stop setup.")
        XCTAssertEqual(setup.requirements, [.transcriptionModel],
                       "A cold recording request must prepare the model before recording.")
        XCTAssertFalse(runner.isRecording, "Setup completion must not record after key release.")
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .idle)
    }

    @MainActor
    func testHoldDuringStartupPreparationDoesNotQueueRecording() async {
        let setup = PreparationGate(phase: .installingRuntime)
        let runner = makeRunner(setup: setup)
        defer { VoiceLevelOverlayController.shared.hide() }

        runner.warmUpTranscription()
        await fulfillment(of: [setup.started], timeout: 2)
        XCTAssertFalse(runner.beginHoldToTranscribe(),
                       "Setup must ask the user to try again when ready, not record later.")
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .installingRuntime)
        runner.endHoldToTranscribe()
        XCTAssertNotEqual(VoiceLevelMeter.shared.captureState, .transcribing)

        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertEqual(setup.callCount, 1)
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .idle)
        XCTAssertEqual(runner.statusMessage, "Ready to record")
    }

    @MainActor
    func testSetupFailureShowsRecoveryAndAllowsAnotherAttempt() async {
        let setup = PreparationGate(
            phase: .installingVoiceService,
            result: CommandResult(exitCode: 1, output: "Fixture download failed")
        )
        let runner = makeRunner(setup: setup)
        defer { VoiceLevelOverlayController.shared.hide() }

        XCTAssertTrue(runner.beginHoldToTranscribe())
        await fulfillment(of: [setup.started], timeout: 2)
        runner.endHoldToTranscribe()
        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .failed)
        XCTAssertFalse(runner.isRecording)
        XCTAssertTrue(runner.beginHoldToTranscribe(), "A setup failure must not leave the hold state stuck.")
        runner.endHoldToTranscribe()
        await waitUntilFinished(runner)
        XCTAssertEqual(setup.callCount, 2)
        XCTAssertEqual(setup.requirements, [.transcriptionModel, .transcriptionModel],
                       "A failed model setup must be retried visibly before recording.")
    }

    @MainActor
    func testRecordingChecksModelReadinessEvenAfterStartupWarmUp() async {
        let setup = PreparationGate(phase: .warmingWhisperModel)
        let runner = makeRunner(setup: setup)
        defer { VoiceLevelOverlayController.shared.hide() }
        runner.warmUpTranscription()
        await fulfillment(of: [setup.started], timeout: 2)
        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertTrue(runner.beginHoldToTranscribe())
        runner.endHoldToTranscribe()
        await waitUntilFinished(runner)
        XCTAssertEqual(setup.requirements, [.transcriptionModel, .transcriptionModel])
    }

    func testDismissedSetupDoesNotReopenOnBackgroundProgress() {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.showPreparation(.installingRuntime)
        overlay.hide()
        overlay.updatePreparation(.warmingWhisperModel)
        XCTAssertNil(overlay.preparationPhase)
        overlay.updatePreparation(.idle)
        XCTAssertNil(overlay.preparationPhase)
    }

    @MainActor
    func testUnrelatedCommandDoesNotReplaceFailedVoiceSetupWithReady() async {
        let setup = PreparationGate(phase: .installingVoiceService,
                                    result: CommandResult(exitCode: 1, output: "Service failed"))
        let runner = AgentCommandRunner(
            bootstrap: { requirement, force, progress in
                if requirement == .cliRuntime {
                    progress(.checkingRuntime)
                    return CommandResult(exitCode: 0, output: "")
                }
                return setup.bootstrap(requirement, force, progress)
            },
            recordingPermissionCheck: { true },
            sendNotification: { _ in },
            runCommand: { _ in CommandResult(exitCode: 0, output: "Clipboard corrected") }
        )
        defer { VoiceLevelOverlayController.shared.hide() }
        XCTAssertTrue(runner.beginHoldToTranscribe())
        await fulfillment(of: [setup.started], timeout: 2)
        runner.endHoldToTranscribe()
        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .failed)
        XCTAssertTrue(runner.run(.autocorrect))
        await waitUntilFinished(runner)
        XCTAssertEqual(runner.bootstrapPhase, .failed)
        XCTAssertEqual(VoiceLevelOverlayController.shared.preparationPhase, .failed)
    }

    @MainActor
    func testRecordingAttemptDoesNotRestoreMinimizedSetup() async throws {
        let setup = PreparationGate(phase: .warmingWhisperModel)
        let runner = makeRunner(setup: setup)
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        runner.warmUpTranscription()
        await fulfillment(of: [setup.started], timeout: 2)
        XCTAssertFalse(runner.beginHoldToTranscribe())
        let panel = try preparationPanel()
        overlay.minimize()
        XCTAssertFalse(runner.beginHoldToTranscribe())
        XCTAssertFalse(panel.isVisible)
        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertFalse(panel.isVisible)
        overlay.restore()
        XCTAssertTrue(panel.isVisible)
    }

    @MainActor
    func testLateSetupProgressCannotReviveFinishedPreparation() async {
        let setup = PreparationGate(phase: .installingRuntime)
        let runner = makeRunner(setup: setup)
        defer { VoiceLevelOverlayController.shared.hide() }
        runner.warmUpTranscription()
        await fulfillment(of: [setup.started], timeout: 2)
        setup.finish()
        await waitUntilFinished(runner)
        XCTAssertEqual(runner.bootstrapPhase, .idle)
        setup.reportLateProgress()
        try? await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertEqual(runner.bootstrapPhase, .idle, "A completed request cannot put setup back in progress.")
    }

    func testRetryStartsNewPreparationTimer() throws {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.showPreparation(.installingRuntime)
        let panel = try XCTUnwrap(NSApplication.shared.windows.first {
            $0.contentView is NSHostingView<VoicePreparationOverlayView>
        })
        let firstView = try XCTUnwrap(panel.contentView as? NSHostingView<VoicePreparationOverlayView>)
        let firstStart = firstView.rootView.startedAt
        overlay.updatePreparation(.failed)
        overlay.showPreparation(.checkingRuntime)
        let retryView = try XCTUnwrap(panel.contentView as? NSHostingView<VoicePreparationOverlayView>)
        XCTAssertGreaterThan(retryView.rootView.startedAt, firstStart)
    }

    func testPreparationUpdatesPreserveUserPosition() throws {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.showPreparation(.installingRuntime)
        let panel = try preparationPanel()
        let movedOrigin = NSPoint(x: panel.frame.minX + 30, y: panel.frame.minY + 60)
        panel.setFrameOrigin(movedOrigin)
        overlay.updatePreparation(.warmingWhisperModel)
        XCTAssertEqual(panel.frame.origin, movedOrigin, "A progress update must not move the card back.")
        XCTAssertTrue(panel.isMovableByWindowBackground)
    }

    func testMinimizedPreparationStaysHiddenUntilExplicitlyRestored() throws {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.showPreparation(.installingRuntime)
        let panel = try preparationPanel()
        overlay.minimize()
        XCTAssertFalse(panel.isVisible)
        overlay.updatePreparation(.warmingWhisperModel)
        XCTAssertFalse(panel.isVisible, "Background progress must not restore a minimized card.")
        overlay.updatePreparation(.idle)
        XCTAssertFalse(panel.isVisible, "Completion must not interrupt the user either.")
        XCTAssertEqual(overlay.preparationPhase, .idle)
        overlay.restore()
        XCTAssertTrue(panel.isVisible)
    }

    private func preparationPanel() throws -> NSWindow {
        try XCTUnwrap(NSApplication.shared.windows.first {
            $0.contentView is NSHostingView<VoicePreparationOverlayView>
        })
    }

    func testTranscribingPillCanMoveAndMinimizeWithoutStoppingWork() throws {
        let overlay = VoiceLevelOverlayController.shared
        defer { overlay.hide() }
        overlay.show(showsPreviewSpace: true)
        let panel = try XCTUnwrap(NSApplication.shared.windows.first {
            $0.contentView is NSHostingView<VoiceLevelOverlayView>
        })
        XCTAssertTrue(panel.isMovableByWindowBackground)
        XCTAssertFalse(panel.ignoresMouseEvents)
        let movedOrigin = NSPoint(x: panel.frame.minX + 30, y: panel.frame.minY + 60)
        panel.setFrameOrigin(movedOrigin)
        overlay.minimize()
        XCTAssertFalse(panel.isVisible)
        overlay.showTranscribing()
        overlay.endRecording()
        XCTAssertFalse(panel.isVisible, "Progress must not restore a minimized pill.")
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .transcribing)
        XCTAssertEqual(panel.frame.origin, movedOrigin)
        overlay.restore()
        XCTAssertTrue(panel.isVisible)
        XCTAssertEqual(VoiceLevelMeter.shared.captureState, .transcribing)
        overlay.finishTranscribing()
        XCTAssertFalse(overlay.hasActiveOverlay)
        XCTAssertFalse(panel.isVisible)
    }

    @MainActor
    private func makeRunner(setup: PreparationGate) -> AgentCommandRunner {
        AgentCommandRunner(
            bootstrap: setup.bootstrap,
            recordingPermissionCheck: { true },
            sendNotification: { _ in },
            runCommand: { arguments in
                XCTFail("Canceled setup must never launch a command: \(arguments)")
                return CommandResult(exitCode: 1, output: "Unexpected command")
            }
        )
    }

    @MainActor
    private func waitUntilFinished(_ runner: AgentCommandRunner) async {
        let deadline = Date().addingTimeInterval(2)
        while runner.isRunning && Date() < deadline {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertFalse(runner.isRunning, "Command should finish after the setup gate is released.")
    }
}

/// Blocks external setup, while leaving the runner and overlay state transitions real.
private final class PreparationGate {
    let started = XCTestExpectation(description: "setup started")
    private let condition = NSCondition()
    private var released = false
    private var calls = 0
    private var requestedRequirements: [AgentBootstrapRequirement] = []
    private var progress: AgentBootstrapProgress?
    private let phase: BootstrapPhase
    private let result: CommandResult

    init(phase: BootstrapPhase, result: CommandResult = CommandResult(exitCode: 0, output: "")) {
        self.phase = phase
        self.result = result
    }

    var callCount: Int {
        condition.lock()
        defer { condition.unlock() }
        return calls
    }

    var requirements: [AgentBootstrapRequirement] {
        condition.lock()
        defer { condition.unlock() }
        return requestedRequirements
    }

    func bootstrap(_ requirement: AgentBootstrapRequirement, _ force: Bool,
                   _ progress: @escaping AgentBootstrapProgress) -> CommandResult {
        condition.lock()
        calls += 1
        requestedRequirements.append(requirement)
        self.progress = progress
        let firstCall = calls == 1
        condition.unlock()
        progress(phase)
        if firstCall { started.fulfill() }
        condition.lock()
        while !released {
            if !condition.wait(until: Date().addingTimeInterval(5)) {
                condition.unlock()
                XCTFail("Test did not release setup gate")
                return CommandResult(exitCode: 1, output: "Test timed out")
            }
        }
        condition.unlock()
        return result
    }

    func finish() {
        condition.lock()
        released = true
        condition.broadcast()
        condition.unlock()
    }

    func reportLateProgress() {
        condition.lock()
        let progress = progress
        condition.unlock()
        progress?(.warmingWhisperModel)
    }
}
#endif
