import XCTest
@testable import AgentCLI

@MainActor
final class PermissionControllerTests: XCTestCase {
    func testRefreshNeverRequestsAccess() async {
        let service = TestPermissionService()
        let controller = PermissionController(service: service)

        await controller.refresh()

        XCTAssertEqual(controller.microphone, .notRequested)
        XCTAssertEqual(controller.accessibility, .notGranted)
        XCTAssertEqual(controller.notifications, .notRequested)
        XCTAssertTrue(controller.needsSetup)
        XCTAssertTrue(service.actions.isEmpty)
    }

    func testMicrophoneRequestRefreshesActualGrant() async {
        let service = TestPermissionService()
        let controller = PermissionController(service: service)

        await controller.performAction(for: .microphone)

        XCTAssertEqual(service.actions, [.request(.microphone)])
        XCTAssertEqual(controller.microphone, .granted)
        XCTAssertNil(controller.requestingPermission)
    }

    func testDeniedMicrophoneOpensSettingsInsteadOfRequestingAgain() async {
        let service = TestPermissionService()
        service.microphoneStatus = .denied
        let controller = PermissionController(service: service)

        await controller.performAction(for: .microphone)

        XCTAssertEqual(service.actions, [.openSettings(.microphone)])
        XCTAssertEqual(controller.microphone, .denied)
    }

    func testRestrictedMicrophoneCannotBeRequested() async {
        let service = TestPermissionService()
        service.microphoneStatus = .restricted
        let controller = PermissionController(service: service)

        await controller.performAction(for: .microphone)

        XCTAssertTrue(service.actions.isEmpty)
        XCTAssertNil(controller.microphone.actionTitle)
    }

    func testAccessibilityRequestDoesNotAssumeGrant() async {
        let service = TestPermissionService()
        let controller = PermissionController(service: service)

        await controller.performAction(for: .accessibility)

        XCTAssertEqual(service.actions, [.request(.accessibility), .openSettings(.accessibility)])
        XCTAssertEqual(controller.accessibility, .notGranted)
        service.accessibilityStatus = .granted
        await controller.refresh()
        XCTAssertEqual(controller.accessibility, .granted)
    }

    func testOptionalNotificationsDoNotBlockSetupOrRecording() async {
        let service = TestPermissionService()
        service.microphoneStatus = .granted
        service.accessibilityStatus = .granted
        service.notificationStatus = .denied
        let controller = PermissionController(service: service)

        await controller.refresh()

        XCTAssertFalse(controller.needsSetup)
        XCTAssertTrue(controller.canRecord)
        await controller.performAction(for: .notifications)
        XCTAssertEqual(service.actions, [.openSettings(.notifications)])
    }

    func testClipboardRecordingIsReadyWithoutAccessibility() async {
        let service = TestPermissionService()
        service.microphoneStatus = .granted
        let controller = PermissionController(service: service)

        await controller.refresh()

        XCTAssertFalse(controller.needsSetup)
        XCTAssertTrue(controller.canRecord)
        XCTAssertEqual(controller.accessibility, .notGranted)
    }

    func testLaunchSetupDoesNotNagButRecoveryAlwaysReopensIt() {
        let service = TestPermissionService()
        let controller = PermissionController(service: service)
        XCTAssertTrue(controller.shouldShowSetupOnLaunch(hasSeenSetup: false, recoveryRequested: false))
        XCTAssertFalse(controller.shouldShowSetupOnLaunch(hasSeenSetup: true, recoveryRequested: false))

        service.microphoneStatus = .granted
        XCTAssertTrue(controller.canRecord)

        XCTAssertFalse(controller.shouldShowSetupOnLaunch(hasSeenSetup: false, recoveryRequested: false))
        XCTAssertTrue(controller.shouldShowSetupOnLaunch(hasSeenSetup: true, recoveryRequested: true))
    }

    func testDeniedRequestStaysDenied() async {
        let service = TestPermissionService()
        service.microphoneRequestResult = .denied
        let controller = PermissionController(service: service)

        await controller.performAction(for: .microphone)

        XCTAssertEqual(controller.microphone, .denied)
        XCTAssertFalse(controller.canRecord)
        XCTAssertTrue(controller.needsSetup)
    }

    func testGrantedPermissionsDoNotRequestOrOpenSettings() async {
        let service = TestPermissionService()
        service.microphoneStatus = .granted
        service.accessibilityStatus = .granted
        service.notificationStatus = .granted
        let controller = PermissionController(service: service)

        for permission in AppPermission.allCases {
            await controller.performAction(for: permission)
        }

        XCTAssertTrue(service.actions.isEmpty)
    }

    func testConcurrentActionsCannotShowTwoSystemRequests() async {
        let service = TestPermissionService()
        let started = expectation(description: "Microphone request started")
        var resumeRequest: CheckedContinuation<Void, Never>?
        service.waitForMicrophoneResponse = {
            await withCheckedContinuation { continuation in
                resumeRequest = continuation
                started.fulfill()
            }
        }
        let controller = PermissionController(service: service)
        let request = Task { await controller.performAction(for: .microphone) }
        await fulfillment(of: [started], timeout: 2)

        await controller.performAction(for: .notifications)
        XCTAssertEqual(service.actions, [.request(.microphone)])
        XCTAssertEqual(controller.requestingPermission, .microphone)
        resumeRequest?.resume()
        await request.value
        XCTAssertNil(controller.requestingPermission)
    }

    func testRecordingCheckReadsRevokedPermissionWithoutRequesting() {
        let service = TestPermissionService()
        service.microphoneStatus = .granted
        let controller = PermissionController(service: service)
        XCTAssertTrue(controller.canRecord)

        service.microphoneStatus = .denied

        XCTAssertFalse(controller.canRecord)
        XCTAssertEqual(controller.microphone, .denied)
        XCTAssertTrue(service.actions.isEmpty)
    }

    func testNotificationRequestErrorIsVisibleAndCanBeRetried() async {
        let service = TestPermissionService()
        service.notificationError = TestError.unavailable
        let controller = PermissionController(service: service)

        await controller.performAction(for: .notifications)

        XCTAssertFalse(controller.errorMessage.isEmpty)
        XCTAssertNil(controller.requestingPermission)
        service.notificationError = nil
        await controller.performAction(for: .notifications)
        XCTAssertEqual(controller.notifications, .granted)
        XCTAssertEqual(controller.errorMessage, "")
    }

    func testSettingsOpenFailureIsVisible() async {
        let service = TestPermissionService()
        service.microphoneStatus = .denied
        service.canOpenSettings = false
        let controller = PermissionController(service: service)

        await controller.performAction(for: .microphone)

        XCTAssertFalse(controller.errorMessage.isEmpty)
        XCTAssertEqual(controller.microphone, .denied)
    }

    func testBlockedHoldDoesNotBootstrapOrLeaveRecordingState() {
        var settingsOpened = 0
        let runner = AgentCommandRunner(
            bootstrap: { _, _, _ in
                XCTFail("Blocked recording must not bootstrap the runtime")
                return CommandResult(exitCode: 1, output: "Unexpected bootstrap")
            },
            recordingPermissionCheck: { false },
            showPermissionSettings: { settingsOpened += 1 }
        )

        XCTAssertFalse(runner.beginHoldToTranscribe())
        runner.run(.voiceEdit)
        XCTAssertEqual(settingsOpened, 2)
        XCTAssertFalse(runner.isRunning)
        XCTAssertFalse(runner.isRecording)
        // Another blocked attempt must remain idle, rather than become a stop request.
        XCTAssertFalse(runner.beginHoldToTranscribe())
        XCTAssertEqual(settingsOpened, 3)
    }
}

private enum TestError: Error { case unavailable }

@MainActor
private final class TestPermissionService: PermissionServicing {
    enum Action: Equatable {
        case request(AppPermission)
        case openSettings(AppPermission)
    }

    var microphoneStatus: PermissionStatus = .notRequested
    var microphoneRequestResult: PermissionStatus = .granted
    var waitForMicrophoneResponse: (() async -> Void)?
    var accessibilityStatus: PermissionStatus = .notGranted
    var notificationStatus: PermissionStatus = .notRequested
    var notificationError: Error?
    var canOpenSettings = true
    var actions: [Action] = []

    func readNotificationStatus() async -> PermissionStatus { notificationStatus }

    func requestMicrophone() async {
        actions.append(.request(.microphone))
        await waitForMicrophoneResponse?()
        microphoneStatus = microphoneRequestResult
    }

    func requestAccessibility() { actions.append(.request(.accessibility)) }

    func requestNotifications() async throws {
        actions.append(.request(.notifications))
        if let notificationError { throw notificationError }
        notificationStatus = .granted
    }

    func openSettings(for permission: AppPermission) -> Bool {
        actions.append(.openSettings(permission))
        return canOpenSettings
    }
}
