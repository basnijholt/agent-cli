#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class ConfigurableHotkeyControllerTests: XCTestCase {
    func testReleaseBeforeHoldStartCompletesStopsAfterSuccessfulStart() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.releaseKey(), .deferUntilStartCompletes)

        XCTAssertEqual(state.completeStart(started: true), .stopNow)
        XCTAssertFalse(state.isStartPendingOrRecording)
    }

    func testReleaseAfterHoldStartStopsImmediately() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.completeStart(started: true), .none)

        XCTAssertEqual(state.releaseKey(), .stopNow)
        XCTAssertFalse(state.isStartPendingOrRecording)
    }

    func testFailedHoldStartAfterReleaseClearsPendingStateWithoutStop() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertEqual(state.releaseKey(), .deferUntilStartCompletes)

        XCTAssertEqual(state.completeStart(started: false), .none)
        XCTAssertFalse(state.isStartPendingOrRecording)
    }
}
#endif
