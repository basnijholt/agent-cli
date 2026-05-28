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

    func testNotFoundCanStillBeToggledToLetServiceManagementRecoverOrReportError() {
        let presentation = LoginItemPresentation(status: .notFound)

        XCTAssertFalse(presentation.isEnabled)
        XCTAssertTrue(presentation.canToggle)
        XCTAssertEqual(presentation.menuTitle, "Start at Login: Unavailable")
        XCTAssertEqual(
            presentation.helpText,
            "macOS could not find Agent CLI's login item registration. Remove old copies, keep Agent CLI in /Applications, then toggle Start at Login again."
        )
    }
}
#endif
