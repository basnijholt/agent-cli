import AppKit
import Foundation

@MainActor
final class StatusMenuController: NSObject, NSMenuDelegate {
    static let shared = StatusMenuController()

    private static let statusRefreshInterval: TimeInterval = 0.8
    private static let statusRefreshRunLoopModes: [RunLoop.Mode] = [.common, .eventTracking]
    private static let voiceStatusTitlePrefix = "Voice: "
    private static let activityStatusTitlePrefix = "Status: "

    private let runner = AgentCommandRunner.shared
    private let appUpdater = AppUpdater.shared
    private let loginItemController = LoginItemController.shared
    private let shortcutSummary = ShortcutSummaryState.shared

    private var statusItem: NSStatusItem?
    private let menu = NSMenu()
    private let recentRecordingsMenu = NSMenu()
    private let troubleshootingMenu = NSMenu()
    private var voiceStatusItem: NSMenuItem?
    private var recentActivityStatusItem: NSMenuItem?
    private var recentActivityStatusSeparator: NSMenuItem?
    private var troubleshootingActivityStatusItem: NSMenuItem?
    private var troubleshootingActivityStatusSeparator: NSMenuItem?
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

        let voiceStatusItem = disabledItem("")
        menu.addItem(voiceStatusItem)
        self.voiceStatusItem = voiceStatusItem

        menu.addItem(disabledItem(shortcutSummary.summary))
        menu.addItem(.separator())

        menu.addItem(submenuItem(
            "Recent Recordings",
            symbolName: "clock.arrow.circlepath",
            submenu: recentRecordingsMenu
        ))
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

        menu.addItem(submenuItem(
            "Troubleshooting",
            symbolName: "wrench.and.screwdriver",
            submenu: troubleshootingMenu
        ))

        menu.addItem(.separator())
        menu.addItem(actionItem("Quit", symbolName: "power", action: #selector(quit)))
        refreshDynamicStatus()
    }

    private func rebuildRecentRecordingsMenu() {
        recentRecordingsMenu.removeAllItems()
        let activityItem = disabledItem("")
        let activitySeparator = NSMenuItem.separator()
        recentRecordingsMenu.addItem(activityItem)
        recentRecordingsMenu.addItem(activitySeparator)
        recentActivityStatusItem = activityItem
        recentActivityStatusSeparator = activitySeparator

        let recentTranscriptions = RecentTranscriptionReader.recentTranscriptions()
        if recentTranscriptions.isEmpty {
            recentRecordingsMenu.addItem(disabledItem("No recent transcriptions"))
            refreshDynamicStatus()
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
        refreshDynamicStatus()
    }

    private func rebuildTroubleshootingMenu() {
        troubleshootingMenu.removeAllItems()
        let activityItem = disabledItem("")
        let activitySeparator = NSMenuItem.separator()
        troubleshootingMenu.addItem(activityItem)
        troubleshootingMenu.addItem(activitySeparator)
        troubleshootingActivityStatusItem = activityItem
        troubleshootingActivityStatusSeparator = activitySeparator

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
        refreshDynamicStatus()
    }

    private func startStatusRefreshTimer() {
        guard statusRefreshTimer == nil else { return }
        let timer = Timer(timeInterval: Self.statusRefreshInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshDynamicStatus()
            }
        }
        for mode in Self.statusRefreshRunLoopModes {
            RunLoop.main.add(timer, forMode: mode)
        }
        statusRefreshTimer = timer
    }

    private func refreshDynamicStatus() {
        let activityStatus = runner.menuActivityStatus
        voiceStatusItem?.title = "\(Self.voiceStatusTitlePrefix)\(activityStatus.message)"
        updateSubmenuActivityStatus(activityStatus)
        if let button = statusItem?.button {
            button.image = MenuBarIconImage.logoImage(state: runner.menuBarIconState)
            button.imagePosition = .imageOnly
            button.toolTip = accessibilityLabel(for: runner.menuBarIconState)
        }
    }

    private func updateSubmenuActivityStatus(_ activityStatus: MenuActivityStatus) {
        updateSubmenuActivityStatus(
            item: recentActivityStatusItem,
            separator: recentActivityStatusSeparator,
            activityStatus: activityStatus
        )
        updateSubmenuActivityStatus(
            item: troubleshootingActivityStatusItem,
            separator: troubleshootingActivityStatusSeparator,
            activityStatus: activityStatus
        )
    }

    private func updateSubmenuActivityStatus(
        item: NSMenuItem?,
        separator: NSMenuItem?,
        activityStatus: MenuActivityStatus
    ) {
        item?.title = "\(Self.activityStatusTitlePrefix)\(activityStatus.message)"
        item?.isHidden = !activityStatus.isActive
        separator?.isHidden = !activityStatus.isActive
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

    private func disabledItem(_ title: String) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.isEnabled = false
        return item
    }

    private func submenuItem(_ title: String, symbolName: String, submenu: NSMenu) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.image = symbolImage(symbolName)
        item.submenu = submenu
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
