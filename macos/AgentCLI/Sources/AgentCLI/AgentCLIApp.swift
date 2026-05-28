import AppKit
import SwiftUI

@main
struct AgentCLIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.openWindow) private var openWindow
    @StateObject private var runner = AgentCommandRunner.shared
    @StateObject private var loginItemController = LoginItemController.shared
    @StateObject private var shortcutSummary = ShortcutSummaryState.shared

    var body: some Scene {
        MenuBarExtra {
            Button {
                runner.run(.toggleTranscription)
            } label: {
                Label("Record to Clipboard", systemImage: "waveform")
            }

            Button {
                runner.run(.voiceEdit)
            } label: {
                Label("Voice Edit Clipboard", systemImage: "mic")
            }

            Button {
                runner.run(.autocorrect)
            } label: {
                Label("Autocorrect Clipboard", systemImage: "text.badge.checkmark")
            }

            Divider()

            Text("Voice: \(runner.menuStatusMessage)")
                .lineLimit(1)

            Text(shortcutSummary.summary)
                .lineLimit(1)

            Divider()

            Button {
                loginItemController.toggle()
            } label: {
                Label(
                    loginItemController.presentation.menuTitle,
                    systemImage: loginItemController.presentation.isEnabled ? "checkmark.circle" : "circle"
                )
            }
            .disabled(!loginItemController.presentation.canToggle)

            Button {
                openWindow(id: "settings")
                NSApp.activate(ignoringOtherApps: true)
            } label: {
                Label("Settings...", systemImage: "gearshape")
            }

            Menu {
                Button {
                    runner.run(.voiceServiceStatus)
                } label: {
                    Label("Voice Service Status", systemImage: "waveform.path.ecg")
                }

                Button {
                    runner.run(.installOrUpdateCLI)
                } label: {
                    Label("Update CLI Runtime", systemImage: "arrow.down.circle")
                }

                Button {
                    runner.run(.installVoiceService)
                } label: {
                    Label("Reinstall Voice Service", systemImage: "waveform.badge.plus")
                }

                Divider()

                if !runner.lastOutput.isEmpty {
                    Button {
                        runner.copyLastOutput()
                    } label: {
                        Label("Copy Last Output", systemImage: "doc.on.doc")
                    }
                }

                if runner.hasLastError {
                    Button {
                        runner.openLastError()
                    } label: {
                        Label("Open Last Error", systemImage: "exclamationmark.triangle")
                    }

                    Button {
                        runner.copyLastError()
                    } label: {
                        Label("Copy Last Error", systemImage: "doc.on.doc")
                    }
                }

                Button {
                    runner.openLogsFolder()
                } label: {
                    Label("Open Logs Folder", systemImage: "doc.text.magnifyingglass")
                }

                Button {
                    runner.openConfigFolder()
                } label: {
                    Label("Open Config Folder", systemImage: "folder")
                }

                Divider()

                Button {
                    runner.openNotificationSettings()
                } label: {
                    Label("Open Notification Settings", systemImage: "bell.badge")
                }

                Button {
                    runner.openAccessibilitySettings()
                } label: {
                    Label("Open Accessibility Settings", systemImage: "figure.wave")
                }

                Button {
                    ShortcutSummaryState.shared.resetDefaults()
                    runner.statusMessage = "Reset keyboard shortcuts to defaults"
                } label: {
                    Label("Reset Keyboard Shortcuts", systemImage: "arrow.counterclockwise")
                }
            } label: {
                Label("Troubleshooting", systemImage: "wrench.and.screwdriver")
            }

            Divider()

            Button {
                NSApp.terminate(nil)
            } label: {
                Label("Quit", systemImage: "power")
            }
        } label: {
            AgentCLIMenuBarIcon(isRecording: runner.isRecording)
        }
        .menuBarExtraStyle(.menu)

        Window("Agent CLI Settings", id: "settings") {
            SettingsView()
                .frame(width: 460)
        }
        .windowResizability(.contentSize)
    }
}
