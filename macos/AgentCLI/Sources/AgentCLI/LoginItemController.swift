import Foundation
#if canImport(ServiceManagement)
import ServiceManagement
#endif
import SwiftUI

enum LoginItemStatus: Equatable {
    case notRegistered
    case enabled
    case requiresApproval
    case notFound
    case unavailable
}

struct LoginItemPresentation: Equatable {
    let status: LoginItemStatus

    var isEnabled: Bool {
        status == .enabled
    }

    var canToggle: Bool {
        switch status {
        case .unavailable:
            return false
        case .notRegistered, .enabled, .requiresApproval, .notFound:
            return true
        }
    }

    var menuTitle: String {
        "Start at Login: \(statusTitle)"
    }

    var helpText: String {
        switch status {
        case .requiresApproval:
            return "Approve Agent CLI in System Settings > General > Login Items."
        case .notFound:
            return "macOS could not find Agent CLI's login item registration. Remove old copies, keep Agent CLI in /Applications, then toggle Start at Login again."
        case .unavailable:
            return "Start at login is unavailable on this macOS version."
        case .notRegistered, .enabled:
            return ""
        }
    }

    private var statusTitle: String {
        switch status {
        case .notRegistered:
            return "Off"
        case .enabled:
            return "On"
        case .requiresApproval:
            return "Needs Approval"
        case .notFound, .unavailable:
            return "Unavailable"
        }
    }
}

protocol LoginItemServicing {
    var status: LoginItemStatus { get }
    func register() throws
    func unregister() throws
}

@MainActor
final class LoginItemController: ObservableObject {
    static let shared = LoginItemController(service: MainAppLoginItemService())

    @Published private(set) var status: LoginItemStatus
    @Published private(set) var errorMessage = ""

    private let service: LoginItemServicing

    var presentation: LoginItemPresentation {
        LoginItemPresentation(status: status)
    }

    var detailText: String {
        if !errorMessage.isEmpty {
            return errorMessage
        }
        return presentation.helpText
    }

    init(service: LoginItemServicing) {
        self.service = service
        self.status = service.status
    }

    func refresh() {
        status = service.status
    }

    func toggle() {
        setEnabled(!presentation.isEnabled)
    }

    func setEnabled(_ enabled: Bool) {
        do {
            if enabled {
                try service.register()
            } else {
                try service.unregister()
            }
            errorMessage = ""
        } catch {
            errorMessage = error.localizedDescription
        }
        refresh()
    }
}

struct MainAppLoginItemService: LoginItemServicing {
    var status: LoginItemStatus {
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            return LoginItemStatus(SMAppService.mainApp.status)
        }
        #endif
        return .unavailable
    }

    func register() throws {
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            try SMAppService.mainApp.register()
            return
        }
        #endif
        throw LoginItemServiceError.unavailable
    }

    func unregister() throws {
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            try SMAppService.mainApp.unregister()
            return
        }
        #endif
        throw LoginItemServiceError.unavailable
    }
}

private enum LoginItemServiceError: LocalizedError {
    case unavailable

    var errorDescription: String? {
        "Start at login is unavailable on this macOS version."
    }
}

#if canImport(ServiceManagement)
@available(macOS 13.0, *)
private extension LoginItemStatus {
    init(_ status: SMAppService.Status) {
        switch status {
        case .notRegistered:
            self = .notRegistered
        case .enabled:
            self = .enabled
        case .requiresApproval:
            self = .requiresApproval
        case .notFound:
            self = .notFound
        @unknown default:
            self = .unavailable
        }
    }
}
#endif
