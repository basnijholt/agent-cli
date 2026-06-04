#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class ConfigurableHotkeyControllerTests: XCTestCase {
    func testReleaseStopsPendingHoldStart() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        XCTAssertTrue(state.releaseNeedsStop())
        state.completeStart(started: true)

        XCTAssertFalse(state.releaseNeedsStop())
    }

    func testFailedHoldStartClearsPendingState() {
        var state = HoldToTranscribeKeyState()

        XCTAssertTrue(state.requestStart())
        state.completeStart(started: false)

        XCTAssertFalse(state.releaseNeedsStop())
    }
}
#endif
