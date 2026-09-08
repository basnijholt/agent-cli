#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class MicrophonePermissionTests: XCTestCase {
    func testAuthorizedPermissionAllowsRecording() {
        let presentation = MicrophonePermissionPresentation(status: .authorized)

        XCTAssertTrue(presentation.canRecord)
        XCTAssertEqual(presentation.statusMessage, nil)
    }

    func testDeniedPermissionExplainsSettingsFix() {
        let presentation = MicrophonePermissionPresentation(status: .denied)

        XCTAssertFalse(presentation.canRecord)
        XCTAssertEqual(
            presentation.statusMessage,
            "Allow Microphone permission for Agent CLI in System Settings."
        )
    }
}
#endif
