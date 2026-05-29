import AppKit
import SwiftUI

@MainActor
final class SettingsWindowController {
    static let shared = SettingsWindowController()

    private var window: NSWindow?

    private init() {}

    func show() {
        if window == nil {
            let contentSize = NSSize(width: 460, height: 640)
            let controller = NSHostingController(rootView: SettingsView().frame(width: contentSize.width))
            let window = NSWindow(contentViewController: controller)
            window.title = "Agent CLI Settings"
            window.styleMask = [.titled, .closable]
            window.isReleasedWhenClosed = false
            window.setContentSize(contentSize)
            window.center()
            self.window = window
        }

        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
