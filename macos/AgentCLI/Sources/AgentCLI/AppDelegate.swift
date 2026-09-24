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
        StatusMenuController.shared.start()
        ShortcutDefaultsMigrator.migrate()
        LoginItemController.shared.refresh()
        ConfigurableHotkeyController.shared.registerDefaultHotkeys(runner: AgentCommandRunner.shared)
        ShortcutSummaryState.shared.refresh()
        AgentCommandRunner.shared.warmUpTranscription()
        Task { @MainActor in
            let permissions = PermissionController.shared
            await permissions.refresh()
            let defaults = UserDefaults.standard
            let shouldShowSetup = permissions.shouldShowSetupOnLaunch(
                hasSeenSetup: defaults.bool(forKey: PermissionController.hasSeenSetupKey),
                recoveryRequested: defaults.bool(forKey: PermissionController.showOnNextLaunchKey)
            )
            defaults.set(true, forKey: PermissionController.hasSeenSetupKey)
            defaults.removeObject(forKey: PermissionController.showOnNextLaunchKey)
            if shouldShowSetup {
                SettingsWindowController.shared.show(.permissions)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        VoiceLevelOverlayController.shared.hide()
        StatusMenuController.shared.stop()
        releaseInstanceLock()
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        ConfigurableHotkeyController.shared.retryFunctionAwareHotkeysIfTrusted(runner: AgentCommandRunner.shared)
        Task { @MainActor in
            LoginItemController.shared.refresh()
            await PermissionController.shared.refresh()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
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

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list])
    }
}
