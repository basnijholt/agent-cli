import AppKit
import SwiftUI

@MainActor
final class SettingsWindowController {
    static let shared = SettingsWindowController()

    private static let contentSize = NSSize(width: 860, height: 700)

    private var window: NSWindow?
    private let navigation = SettingsNavigation()

    private init() {}

    func show(_ section: SettingsSection? = nil) {
        if let section { navigation.selection = section }
        if window == nil {
            let controller = NSHostingController(rootView: SettingsView(
                navigation: navigation,
                permissions: PermissionController.shared
            ))
            let window = NSWindow(contentViewController: controller)
            window.title = "Agent CLI Settings"
            window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
            window.isReleasedWhenClosed = false
            window.setContentSize(Self.contentSize)
            window.contentMinSize = NSSize(width: 780, height: 600)
            window.center()
            window.setFrameAutosaveName("AgentCLISettings")
            self.window = window
        }

        if window?.isMiniaturized == true { window?.deminiaturize(nil) }
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
