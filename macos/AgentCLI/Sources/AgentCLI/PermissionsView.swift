import AppKit
import SwiftUI

struct PermissionsView: View {
    @ObservedObject var controller: PermissionController
    @ObservedObject private var runner = AgentCommandRunner.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    Label(controller.needsSetup ? "Set up your voice tools" : "You're ready to record",
                          systemImage: controller.needsSetup ? "checklist" : "checkmark.circle.fill")
                        .font(.headline)
                    Spacer()
                    Button("Check Again") {
                        Task {
                            await controller.refresh()
                            ConfigurableHotkeyController.shared.retryFunctionAwareHotkeysIfTrusted(runner: runner)
                        }
                    }
                    .disabled(controller.requestingPermission != nil)
                }
                Text("Enable only the access you need. Status updates when you return from System Settings.")
                    .foregroundStyle(.secondary)
                ForEach(AppPermission.allCases) { permission in
                    permissionCard(permission)
                }
                if !controller.errorMessage.isEmpty {
                    Label(controller.errorMessage, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                }
                DisclosureGroup("Still having trouble?") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("If access is enabled in System Settings but not here, quit and reopen Agent CLI. Make sure the enabled entry is this copy of the app.")
                        Text(Bundle.main.bundleURL.path)
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        Button("Show This App in Finder") {
                            NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
                        }
                        Divider()
                        Text("As a last resort, reset Accessibility. This removes Agent CLI's grant and restarts the app; you will need to enable access again.")
                        Button("Reset Accessibility Access…") { runner.resetAccessibilityPermission() }
                            .disabled(runner.isRunning || runner.isRecording)
                    }
                    .font(.callout)
                    .padding(.top, 10)
                }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func permissionCard(_ permission: AppPermission) -> some View {
        let status = controller.status(for: permission)
        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: permission.symbol)
                    .font(.title3)
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 36, height: 36)
                    .background(Color.accentColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(permission.title).font(.headline)
                        Spacer()
                        Label(status.title, systemImage: status == .granted ? "checkmark.circle.fill" : "circle")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(status == .granted ? Color.green : Color.secondary)
                    }
                    Text(permission.purpose).font(.callout).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if status != .granted {
                Divider()
                HStack(alignment: .center, spacing: 16) {
                    Text(guidance(for: permission, status: status))
                        .font(.callout).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    if controller.requestingPermission == permission {
                        ProgressView().controlSize(.small)
                    } else if let action = status.actionTitle {
                        Button(action) { Task { await controller.performAction(for: permission) } }
                            .fixedSize()
                            .disabled(controller.requestingPermission != nil)
                            .accessibilityLabel("\(action) for \(permission.title)")
                    }
                }
            }
        }
        .padding(18)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.primary.opacity(0.08)))
    }

    private func guidance(for permission: AppPermission, status: PermissionStatus) -> String {
        if status == .restricted { return "macOS or a device policy restricts this access. Contact your administrator if needed." }
        if status == .checking { return "Checking the current macOS permission…" }
        if status == .notRequested { return "Choose Allow to see the macOS permission request." }
        switch permission {
        case .microphone: return "In Privacy & Security > Microphone, enable Agent CLI."
        case .accessibility: return "In Privacy & Security > Accessibility, enable Agent CLI. You can still record to the clipboard without this."
        case .notifications: return "In Notifications > Agent CLI, turn on Allow Notifications."
        }
    }
}
