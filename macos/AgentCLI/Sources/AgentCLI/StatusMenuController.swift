import AppKit
import Foundation

@MainActor
final class StatusMenuController: NSObject, NSMenuDelegate {
    static let shared = StatusMenuController()

    private let runner = AgentCommandRunner.shared
    private let appUpdater = AppUpdater.shared
    private let loginItemController = LoginItemController.shared
    private let shortcutSummary = ShortcutSummaryState.shared

    private var statusItem: NSStatusItem?
    private let menu = NSMenu()
    private let recentRecordingsMenu = NSMenu()
    private let troubleshootingMenu = NSMenu()
    private var voiceStatusItem: NSMenuItem?
    private var statusRefreshTimer: Timer?

    private override init() {
        super.init()
        menu.delegate = self
        recentRecordingsMenu.delegate = self
        troubleshootingMenu.delegate = self
    }

    func start() {
        guard statusItem == nil else { return }

        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.menu = menu
        statusItem = item
        rebuildRootMenu()
        refreshDynamicStatus()
        startStatusRefreshTimer()
    }

    func stop() {
        statusRefreshTimer?.invalidate()
        statusRefreshTimer = nil
        if let statusItem {
            NSStatusBar.system.removeStatusItem(statusItem)
        }
        statusItem = nil
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        if menu === self.menu {
            rebuildRootMenu()
        } else if menu === recentRecordingsMenu {
            rebuildRecentRecordingsMenu()
        } else if menu === troubleshootingMenu {
            rebuildTroubleshootingMenu()
        }
        refreshDynamicStatus()
    }

    private func rebuildRootMenu() {
        menu.removeAllItems()

        menu.addItem(actionItem("Record to Clipboard", symbolName: "waveform", action: #selector(recordToClipboard)))
        menu.addItem(actionItem("Voice Edit Clipboard", symbolName: "mic", action: #selector(voiceEditClipboard)))
        menu.addItem(actionItem("Autocorrect Clipboard", symbolName: "text.badge.checkmark", action: #selector(autocorrectClipboard)))
        menu.addItem(.separator())

        let voiceStatusItem = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        voiceStatusItem.isEnabled = false
        menu.addItem(voiceStatusItem)
        self.voiceStatusItem = voiceStatusItem

        let shortcutItem = NSMenuItem(title: shortcutSummary.summary, action: nil, keyEquivalent: "")
        shortcutItem.isEnabled = false
        menu.addItem(shortcutItem)
        menu.addItem(.separator())

        let recentItem = NSMenuItem(title: "Recent Recordings", action: nil, keyEquivalent: "")
        recentItem.image = symbolImage("clock.arrow.circlepath")
        recentItem.submenu = recentRecordingsMenu
        menu.addItem(recentItem)
        menu.addItem(.separator())

        let loginItem = actionItem(
            loginItemController.presentation.menuTitle,
            symbolName: loginItemController.presentation.isEnabled ? "checkmark.circle" : "circle",
            action: #selector(toggleStartAtLogin)
        )
        loginItem.isEnabled = loginItemController.presentation.canToggle
        menu.addItem(loginItem)

        menu.addItem(actionItem("Settings...", symbolName: "gearshape", action: #selector(openSettings)))

        let updateItem = actionItem("Check for Updates...", symbolName: "arrow.down.circle", action: #selector(checkForUpdates))
        updateItem.isEnabled = appUpdater.canCheckForUpdates
        menu.addItem(updateItem)

        let troubleshootingItem = NSMenuItem(title: "Troubleshooting", action: nil, keyEquivalent: "")
        troubleshootingItem.image = symbolImage("wrench.and.screwdriver")
        troubleshootingItem.submenu = troubleshootingMenu
        menu.addItem(troubleshootingItem)

        menu.addItem(.separator())
        menu.addItem(actionItem("Quit", symbolName: "power", action: #selector(quit)))
        refreshDynamicStatus()
    }

    private func rebuildRecentRecordingsMenu() {
        recentRecordingsMenu.removeAllItems()
        let recentTranscriptions = RecentTranscriptionReader.recentTranscriptions()
        if recentTranscriptions.isEmpty {
            let item = NSMenuItem(title: "No recent transcriptions", action: nil, keyEquivalent: "")
            item.isEnabled = false
            recentRecordingsMenu.addItem(item)
            return
        }

        for transcription in recentTranscriptions {
            let item = actionItem(
                transcription.menuTitle,
                symbolName: "doc.on.clipboard",
                action: #selector(copyRecentTranscription)
            )
            item.representedObject = transcription.text
            recentRecordingsMenu.addItem(item)
        }
    }

    private func rebuildTroubleshootingMenu() {
        troubleshootingMenu.removeAllItems()
        troubleshootingMenu.addItem(actionItem(
            "Voice Service Status",
            symbolName: "waveform.path.ecg",
            action: #selector(showVoiceServiceStatus)
        ))
        troubleshootingMenu.addItem(actionItem(
            runtimeCheckTitle,
            symbolName: usesUserInstalledAgentCLI ? "checkmark.circle" : "arrow.down.circle",
            action: #selector(checkRuntime)
        ))
        troubleshootingMenu.addItem(actionItem(
            "Reinstall Voice Service",
            symbolName: "waveform.badge.plus",
            action: #selector(reinstallVoiceService)
        ))
        troubleshootingMenu.addItem(.separator())

        if !runner.lastOutput.isEmpty {
            troubleshootingMenu.addItem(actionItem(
                "Copy Last Output",
                symbolName: "doc.on.doc",
                action: #selector(copyLastOutput)
            ))
        }

        if runner.hasLastError {
            troubleshootingMenu.addItem(actionItem(
                "Open Last Error",
                symbolName: "exclamationmark.triangle",
                action: #selector(openLastError)
            ))
            troubleshootingMenu.addItem(actionItem(
                "Copy Last Error",
                symbolName: "doc.on.doc",
                action: #selector(copyLastError)
            ))
        }

        troubleshootingMenu.addItem(actionItem(
            "Open Logs Folder",
            symbolName: "doc.text.magnifyingglass",
            action: #selector(openLogsFolder)
        ))
        troubleshootingMenu.addItem(actionItem(
            "Open Config Folder",
            symbolName: "folder",
            action: #selector(openConfigFolder)
        ))
        troubleshootingMenu.addItem(.separator())
        troubleshootingMenu.addItem(actionItem(
            "Fix Notification Permission...",
            symbolName: "bell.badge",
            action: #selector(fixNotificationPermission)
        ))
        troubleshootingMenu.addItem(actionItem(
            "Reset Accessibility Permission...",
            symbolName: "figure.wave",
            action: #selector(resetAccessibilityPermission)
        ))
        troubleshootingMenu.addItem(actionItem(
            "Reset Keyboard Shortcuts",
            symbolName: "arrow.counterclockwise",
            action: #selector(resetKeyboardShortcuts)
        ))
    }

    private func startStatusRefreshTimer() {
        guard statusRefreshTimer == nil else { return }
        let timer = Timer(timeInterval: 0.8, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshDynamicStatus()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        RunLoop.main.add(timer, forMode: .eventTracking)
        statusRefreshTimer = timer
    }

    private func refreshDynamicStatus() {
        voiceStatusItem?.title = "Voice: \(runner.menuStatusMessage)"
        if let button = statusItem?.button {
            button.image = MenuBarIconImage.logoImage(state: runner.menuBarIconState)
            button.imagePosition = .imageOnly
            button.toolTip = accessibilityLabel(for: runner.menuBarIconState)
        }
    }

    private var usesUserInstalledAgentCLI: Bool {
        UserDefaults.standard.bool(forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
    }

    private var runtimeCheckTitle: String {
        usesUserInstalledAgentCLI ? "Check User CLI" : "Update CLI Runtime"
    }

    private func actionItem(_ title: String, symbolName: String, action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.image = symbolImage(symbolName)
        return item
    }

    private func symbolImage(_ name: String) -> NSImage? {
        NSImage(systemSymbolName: name, accessibilityDescription: nil)
    }

    private func accessibilityLabel(for state: MenuBarIconState) -> String {
        switch state {
        case .idle:
            return "Agent CLI"
        case .preparing:
            return "Agent CLI preparing"
        case .recording:
            return "Agent CLI recording"
        }
    }

    @objc private func recordToClipboard() {
        runner.run(.toggleTranscription)
    }

    @objc private func voiceEditClipboard() {
        runner.run(.voiceEdit)
    }

    @objc private func autocorrectClipboard() {
        runner.run(.autocorrect)
    }

    @objc private func toggleStartAtLogin() {
        loginItemController.toggle()
    }

    @objc private func openSettings() {
        SettingsWindowController.shared.show()
    }

    @objc private func checkForUpdates() {
        appUpdater.checkForUpdates()
    }

    @objc private func showVoiceServiceStatus() {
        runner.run(.voiceServiceStatus)
    }

    @objc private func checkRuntime() {
        runner.run(.installOrUpdateCLI)
    }

    @objc private func reinstallVoiceService() {
        runner.run(.installVoiceService)
    }

    @objc private func copyLastOutput() {
        runner.copyLastOutput()
    }

    @objc private func openLastError() {
        runner.openLastError()
    }

    @objc private func copyLastError() {
        runner.copyLastError()
    }

    @objc private func openLogsFolder() {
        runner.openLogsFolder()
    }

    @objc private func openConfigFolder() {
        runner.openConfigFolder()
    }

    @objc private func fixNotificationPermission() {
        runner.repairNotificationPermission()
    }

    @objc private func resetAccessibilityPermission() {
        runner.resetAccessibilityPermission()
    }

    @objc private func resetKeyboardShortcuts() {
        ShortcutSummaryState.shared.resetDefaults()
        runner.statusMessage = "Reset keyboard shortcuts to defaults"
    }

    @objc private func copyRecentTranscription(_ sender: NSMenuItem) {
        guard let text = sender.representedObject as? String else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        runner.statusMessage = "Copied recent transcription"
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}
