import AppKit
import SwiftUI

@main
struct AgentCLIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        Window("Agent CLI Settings", id: "settings") {
            SettingsView()
                .frame(width: 460)
        }
        .windowResizability(.contentSize)
    }
}
