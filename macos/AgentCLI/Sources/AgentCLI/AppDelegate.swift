import AppKit
import Darwin
import Foundation
import UserNotifications

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    private var instanceLockFD: Int32 = -1

    func applicationDidFinishLaunching(_ notification: Notification) {
        AgentRuntime.shared.runSelfTestIfRequested()
        guard !terminateIfAnotherInstanceIsRunning() else { return }

        NSApp.setActivationPolicy(.accessory)
        UNUserNotificationCenter.current().delegate = self
        configureNotifications()
        ShortcutDefaultsMigrator.migrate()
        ConfigurableHotkeyController.shared.registerDefaultHotkeys(runner: AgentCommandRunner.shared)
        ShortcutSummaryState.shared.refresh()
    }

    func applicationWillTerminate(_ notification: Notification) {
        VoiceLevelOverlayController.shared.hide()
        releaseInstanceLock()
    }

    private func terminateIfAnotherInstanceIsRunning() -> Bool {
        let lockURL = Self.instanceLockURL()
        instanceLockFD = Darwin.open(lockURL.path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard instanceLockFD >= 0 else { return false }
        if flock(instanceLockFD, LOCK_EX | LOCK_NB) == 0 {
            return false
        }

        releaseInstanceLock()
        Task { @MainActor in
            AgentCommandRunner.shared.statusMessage = "Agent CLI is already running"
        }
        NSApp.terminate(nil)
        return true
    }

    private static func instanceLockURL() -> URL {
        if let override = ProcessInfo.processInfo.environment["AGENTCLI_INSTANCE_LOCK_PATH"],
           !override.isEmpty {
            return URL(fileURLWithPath: override)
        }
        return FileManager.default.temporaryDirectory
            .appendingPathComponent("lt.nijho.agent-cli.menubar.lock")
    }

    private func releaseInstanceLock() {
        guard instanceLockFD >= 0 else { return }
        flock(instanceLockFD, LOCK_UN)
        close(instanceLockFD)
        instanceLockFD = -1
    }

    private func configureNotifications() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            switch settings.authorizationStatus {
            case .notDetermined:
                center.requestAuthorization(options: [.alert]) { granted, _ in
                    if !granted {
                        DispatchQueue.main.async {
                            AgentCommandRunner.shared.notificationsDisabled()
                        }
                    }
                }
            case .denied:
                DispatchQueue.main.async {
                    AgentCommandRunner.shared.notificationsDisabled()
                }
            default:
                break
            }
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list])
    }
}
