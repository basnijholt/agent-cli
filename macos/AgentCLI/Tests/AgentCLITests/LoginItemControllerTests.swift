#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class LoginItemControllerTests: XCTestCase {
    func testEnabledStatusIsPresentedAsOn() {
        let presentation = LoginItemPresentation(status: .enabled)

        XCTAssertTrue(presentation.isEnabled)
        XCTAssertEqual(presentation.menuTitle, "Start at Login: On")
        XCTAssertEqual(presentation.helpText, "")
    }

    func testRequiresApprovalIsNotPresentedAsOn() {
        let presentation = LoginItemPresentation(status: .requiresApproval)

        XCTAssertFalse(presentation.isEnabled)
        XCTAssertEqual(presentation.menuTitle, "Start at Login: Needs Approval")
        XCTAssertEqual(
            presentation.helpText,
            "Approve Agent CLI in System Settings > General > Login Items."
        )
    }
}
#endif
