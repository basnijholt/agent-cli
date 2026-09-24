import AppKit
import ApplicationServices
import AVFoundation
import SwiftUI
import UserNotifications

enum AppPermission: String, CaseIterable, Identifiable {
    case microphone, accessibility, notifications

    var id: String { rawValue }

    var title: String {
        switch self {
        case .microphone: return "Microphone"
        case .accessibility: return "Accessibility"
        case .notifications: return "Notifications"
        }
    }

    var symbol: String {
        switch self {
        case .microphone: return "mic.fill"
        case .accessibility: return "hand.point.up.left.fill"
        case .notifications: return "bell.fill"
        }
    }

    var purpose: String {
        switch self {
        case .microphone: return "Record your voice for transcription and voice editing."
        case .accessibility: return "Use Fn shortcuts and insert finished transcripts into the app you're using."
        case .notifications: return "Show recording updates and errors. Optional; recording works without notifications."
        }
    }
}

enum PermissionStatus: Equatable {
    case checking, notRequested, notGranted, denied, restricted, granted

    var title: String {
        switch self {
        case .checking: return "Checking…"
        case .notRequested: return "Not requested"
        case .notGranted: return "Not enabled"
        case .denied: return "Not allowed"
        case .restricted: return "Restricted by macOS"
        case .granted: return "Allowed"
        }
    }

    var actionTitle: String? {
        switch self {
        case .notRequested: return "Allow…"
        case .notGranted, .denied: return "Open System Settings…"
        case .checking, .restricted, .granted: return nil
        }
    }
}

@MainActor
protocol PermissionServicing {
    var microphoneStatus: PermissionStatus { get }
    var accessibilityStatus: PermissionStatus { get }
    func readNotificationStatus() async -> PermissionStatus
    func requestMicrophone() async
    func requestAccessibility()
    func requestNotifications() async throws
    func openSettings(for permission: AppPermission) -> Bool
}

@MainActor
final class PermissionController: ObservableObject {
    static let shared = PermissionController(service: SystemPermissionService())
    static let hasSeenSetupKey = "hasSeenPermissionSetup"
    static let showOnNextLaunchKey = "showPermissionsOnNextLaunch"

    @Published private(set) var microphone: PermissionStatus
    @Published private(set) var accessibility: PermissionStatus
    @Published private(set) var notifications: PermissionStatus = .checking
    @Published private(set) var requestingPermission: AppPermission?
    @Published private(set) var errorMessage = ""

    private let service: PermissionServicing
    private var refreshRevision = 0

    init(service: PermissionServicing) {
        self.service = service
        microphone = service.microphoneStatus
        accessibility = service.accessibilityStatus
    }

    var needsSetup: Bool { microphone != .granted }

    func shouldShowSetupOnLaunch(hasSeenSetup: Bool, recoveryRequested: Bool) -> Bool {
        recoveryRequested || (!hasSeenSetup && needsSetup)
    }

    var canRecord: Bool {
        microphone = service.microphoneStatus
        return microphone == .granted
    }

    func status(for permission: AppPermission) -> PermissionStatus {
        switch permission {
        case .microphone: return microphone
        case .accessibility: return accessibility
        case .notifications: return notifications
        }
    }

    func refresh() async {
        refreshRevision += 1
        let revision = refreshRevision
        microphone = service.microphoneStatus
        accessibility = service.accessibilityStatus
        let notificationStatus = await service.readNotificationStatus()
        guard revision == refreshRevision else { return }
        notifications = notificationStatus
    }

    func performAction(for permission: AppPermission) async {
        guard requestingPermission == nil else { return }
        requestingPermission = permission
        errorMessage = ""
        defer { requestingPermission = nil }
        await refresh()

        switch status(for: permission) {
        case .granted, .restricted, .checking:
            return
        case .denied:
            openSettings(for: permission)
        case .notRequested, .notGranted:
            switch permission {
            case .microphone:
                await service.requestMicrophone()
            case .accessibility:
                service.requestAccessibility()
                openSettings(for: permission)
            case .notifications:
                do {
                    try await service.requestNotifications()
                } catch {
                    errorMessage = "Could not request notifications: \(error.localizedDescription)"
                }
            }
        }
        await refresh()
    }

    private func openSettings(for permission: AppPermission) {
        guard service.openSettings(for: permission) else {
            errorMessage = "Could not open System Settings. Open it manually and select \(permission.title)."
            return
        }
    }
}

@MainActor
private struct SystemPermissionService: PermissionServicing {
    var microphoneStatus: PermissionStatus {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .notDetermined: return .notRequested
        case .authorized: return .granted
        case .denied: return .denied
        case .restricted: return .restricted
        @unknown default: return .restricted
        }
    }

    var accessibilityStatus: PermissionStatus {
        AXIsProcessTrusted() ? .granted : .notGranted
    }

    func readNotificationStatus() async -> PermissionStatus {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .notDetermined: return .notRequested
        case .denied: return .denied
        case .authorized, .provisional, .ephemeral: return .granted
        @unknown default: return .restricted
        }
    }

    func requestMicrophone() async {
        _ = await AVCaptureDevice.requestAccess(for: .audio)
    }

    func requestAccessibility() {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        _ = AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
    }

    func requestNotifications() async throws {
        _ = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert])
    }

    func openSettings(for permission: AppPermission) -> Bool {
        let destinations: [String]
        switch permission {
        case .microphone:
            destinations = ["com.apple.preference.security?Privacy_Microphone"]
        case .accessibility:
            destinations = ["com.apple.preference.security?Privacy_Accessibility"]
        case .notifications:
            destinations = ["com.apple.Notifications-Settings.extension", "com.apple.preference.notifications"]
        }
        return destinations.contains { destination in
            guard let url = URL(string: "x-apple.systempreferences:\(destination)") else { return false }
            return NSWorkspace.shared.open(url)
        }
    }
}
