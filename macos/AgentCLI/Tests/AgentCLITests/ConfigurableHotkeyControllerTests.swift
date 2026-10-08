#if canImport(XCTest)
import Carbon.HIToolbox
import KeyboardShortcuts
import XCTest
@testable import AgentCLI

final class ConfigurableHotkeyControllerTests: XCTestCase {
    @MainActor
    func testFunctionSpaceAfterHoldStartsCanBeToggledOff() async throws {
        try await assertLatchedHoldStops(withSpace: true)
    }

    @MainActor
    func testBareFunctionStopsLatchedHoldRecording() async throws {
        try await assertLatchedHoldStops(withSpace: false)
    }

    @MainActor
    private func assertLatchedHoldStops(withSpace: Bool) async throws {
        try await withRecording { fixture, runner, controller in
            // Fn crosses the hold threshold before Space arrives.
            try send(controller, .flagsChanged, kVK_Function, [.maskSecondaryFn])
            await fulfillment(of: [fixture.started], timeout: 3)
            XCTAssertTrue(runner.isRecording)
            try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn])
            try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn], autorepeat: true)
            try send(controller, .keyUp, kVK_Space, [.maskSecondaryFn])
            try send(controller, .flagsChanged, kVK_Function, [])

            // A second press must stop it without restarting. Bare Fn stops only toggle
            // recordings, so stopping with it also proves that the hold was latched.
            try send(controller, .flagsChanged, kVK_Function, [.maskSecondaryFn])
            if withSpace {
                try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn])
                try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn], autorepeat: true)
                try send(controller, .keyUp, kVK_Space, [.maskSecondaryFn])
            }
            try send(controller, .flagsChanged, kVK_Function, [])
            await fulfillment(of: [fixture.stopped], timeout: 2)
            XCTAssertEqual(fixture.commandCount, 2, "One recording start and one stop, without restarting.")
        }
    }

    @MainActor
    func testFunctionSpaceAfterFailedHoldStartsToggleRecording() async throws {
        try await withRecording(RecordingCommandFixture(failsFirstStart: true)) { fixture, runner, controller in
            // The hold recording fails while Fn is still down.
            try send(controller, .flagsChanged, kVK_Function, [.maskSecondaryFn])
            let deadline = Date().addingTimeInterval(2)
            while fixture.commandCount == 0 || runner.isRunning, Date() < deadline {
                try? await Task.sleep(nanoseconds: 10_000_000)
            }
            XCTAssertEqual(fixture.commandCount, 1)
            XCTAssertFalse(runner.isRecording)
            try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn])
            try send(controller, .keyUp, kVK_Space, [.maskSecondaryFn])
            try send(controller, .flagsChanged, kVK_Function, [])
            await fulfillment(of: [fixture.started], timeout: 2)
            XCTAssertEqual(fixture.commandCount, 2, "Fn+Space must start a toggle recording once the hold ended.")
        }
    }

    @MainActor
    func testDelayedSecondFunctionSpaceStopsOnlyOnce() async throws {
        try await assertDelayedStop(withSpace: true)
    }

    @MainActor
    func testBareFunctionStopsToggleRecordingOnRelease() async throws {
        try await assertDelayedStop(withSpace: false)
    }

    @MainActor
    private func assertDelayedStop(withSpace: Bool) async throws {
        try await withRecording { fixture, runner, controller in
            XCTAssertTrue(runner.run(.toggleTranscription))
            await fulfillment(of: [fixture.started], timeout: 2)
            try send(controller, .flagsChanged, kVK_Function, [.maskSecondaryFn])
            // Wait for the delayed Fn action, using its observable result rather than sleeping.
            let deadline = Date().addingTimeInterval(2)
            while fixture.commandCount == 1,
                  runner.statusMessage != "Release Fn to stop transcription",
                  Date() < deadline {
                try? await Task.sleep(nanoseconds: 10_000_000)
            }
            XCTAssertEqual(runner.statusMessage, "Release Fn to stop transcription")
            XCTAssertEqual(fixture.commandCount, 1, "Fn must not stop before a possible Space chord.")
            XCTAssertTrue(runner.isRecording)
            if withSpace {
                try send(controller, .keyDown, kVK_Space, [.maskSecondaryFn])
                try send(controller, .keyUp, kVK_Space, [.maskSecondaryFn])
            }
            try send(controller, .flagsChanged, kVK_Function, [])
            await fulfillment(of: [fixture.stopped], timeout: 2)
            XCTAssertEqual(fixture.commandCount, 2)
        }
    }

    @MainActor
    private func withRecording(
        _ fixture: RecordingCommandFixture = RecordingCommandFixture(),
        _ operation: (RecordingCommandFixture, AgentCommandRunner, ConfigurableHotkeyController) async throws -> Void
    ) async throws {
        let runner = AgentCommandRunner(
            pasteController: fixture,
            bootstrap: { _, _, _ in CommandResult(exitCode: 0, output: "") },
            recordingPermissionCheck: { true },
            sendNotification: { _ in },
            runCommand: fixture.run
        )
        let controller = ConfigurableHotkeyController(runner: runner)
        let defaults = UserDefaults.standard
        let keys = ["KeyboardShortcuts_toggleTranscription", "KeyboardShortcuts_holdToTranscribe"]
        let saved = keys.map { defaults.object(forKey: $0) }
        ToggleTranscriptionDefault.set()
        KeyboardShortcuts.setShortcut(.init(.function), for: .holdToTranscribe)
        defer {
            fixture.finish()
            controller.suspendFunctionAwareHotkeysForAccessibilityReset()
            VoiceLevelOverlayController.shared.hide()
            for (key, value) in zip(keys, saved) {
                if let value { defaults.set(value, forKey: key) }
                else { defaults.removeObject(forKey: key) }
            }
        }
        try await operation(fixture, runner, controller)
        fixture.finish()
        let deadline = Date().addingTimeInterval(2)
        while runner.isRunning && Date() < deadline {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertFalse(runner.isRunning)
        XCTAssertFalse(runner.isRecording)
        XCTAssertEqual(fixture.pastedTranscripts, [], "Toggle recordings must not paste into the focused field.")
    }

    private func send(_ controller: ConfigurableHotkeyController, _ type: CGEventType,
                      _ keyCode: Int, _ flags: CGEventFlags, autorepeat: Bool = false) throws {
        let event = try XCTUnwrap(CGEvent(keyboardEventSource: nil,
                                         virtualKey: CGKeyCode(keyCode), keyDown: type != .keyUp))
        event.type = type
        event.flags = flags
        event.setIntegerValueField(.keyboardEventAutorepeat, value: autorepeat ? 1 : 0)
        XCTAssertNil(controller.handleFunctionAwareHotkey(type: type, event: event))
    }

    func testReleaseBeforeHoldStartCompletesStopsAfterSuccessfulStart() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.releaseKey(), .deferUntilStartCompletes)

        XCTAssertEqual(state.completeStart(started: true), .stopNow)
        XCTAssertTrue(state.requestStart(), "Releasing the key must allow the next hold.")
    }

    func testReleaseAfterHoldStartStopsImmediately() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.completeStart(started: true), .none)

        XCTAssertEqual(state.releaseKey(), .stopNow)
        XCTAssertTrue(state.requestStart(), "Releasing the key must allow the next hold.")
    }

    func testFailedHoldStartAfterReleaseClearsPendingStateWithoutStop() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.releaseKey(), .deferUntilStartCompletes)

        XCTAssertEqual(state.completeStart(started: false), .none)
        XCTAssertTrue(state.requestStart(), "A failed start must allow the next hold.")
    }

    func testFunctionReleaseBeforeFailedHoldStartStopsExistingToggle() {
        var state = HoldToTranscribeKeyState()
        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.releaseKey(stopExistingFunctionRecording: true), .deferUntilStartCompletes)
        XCTAssertEqual(state.completeStart(started: false), .stopExistingFunctionRecording)
        XCTAssertTrue(state.requestStart())
    }

    func testFunctionReleaseWithoutHoldStopsExistingToggle() {
        var state = HoldToTranscribeKeyState()
        XCTAssertEqual(state.releaseKey(stopExistingFunctionRecording: true), .stopExistingFunctionRecording)
        XCTAssertEqual(state.releaseKey(), .none)
    }

    func testToggleDuringPendingHoldPromotesAfterSuccessfulStart() {
        var state = HoldToTranscribeKeyState()
        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.requestToggle(), .none)
        XCTAssertEqual(state.completeStart(started: true), .promoteToToggle)
        XCTAssertEqual(state.releaseKey(), .none)
        XCTAssertEqual(state.requestToggle(), .toggleNormally)
    }

    func testToggleDuringFailedHoldStillTogglesExistingRecording() {
        var state = HoldToTranscribeKeyState()
        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.requestToggle(), .none)
        XCTAssertEqual(state.completeStart(started: false), .toggleNormally)
        XCTAssertEqual(state.releaseKey(), .none)
        XCTAssertEqual(state.requestToggle(), .toggleNormally)
    }

    func testTogglePromotesActiveHoldWithoutStoppingIt() {
        var state = HoldToTranscribeKeyState()
        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.completeStart(started: true), .none)
        XCTAssertEqual(state.requestToggle(), .promoteToToggle)
        XCTAssertEqual(state.releaseKey(), .none)
        XCTAssertEqual(state.requestToggle(), .toggleNormally)
    }
}
#endif
