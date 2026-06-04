import AppKit
import SwiftUI

@MainActor
final class SettingsWindowController {
    static let shared = SettingsWindowController()

    private static let contentSize = NSSize(width: 460, height: 680)

    private var window: NSWindow?

    private init() {}

    func show() {
        if window == nil {
            let controller = NSHostingController(rootView: SettingsView().frame(width: Self.contentSize.width))
            let window = NSWindow(contentViewController: controller)
            window.title = "Agent CLI Settings"
            window.styleMask = [.titled, .closable]
            window.isReleasedWhenClosed = false
            window.setContentSize(Self.contentSize)
            window.center()
            self.window = window
        }

        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
