import AppKit
import KeyboardShortcuts
import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case general = "General"
    case recording = "Recording"
    case shortcuts = "Shortcuts"
    case permissions = "Permissions"
    case advanced = "Advanced"

    var id: Self { self }

    var symbol: String {
        switch self {
        case .general: return "slider.horizontal.3"
        case .recording: return "waveform"
        case .shortcuts: return "keyboard"
        case .permissions: return "hand.raised"
        case .advanced: return "gearshape.2"
        }
    }

    var subtitle: String {
        switch self {
        case .general: return "Make Agent CLI feel at home on your Mac."
        case .recording: return "Choose how your voice is captured and transcribed."
        case .shortcuts: return "Your voice tools, one shortcut away."
        case .permissions: return "You choose what Agent CLI can access."
        case .advanced: return "Manage your runtime and troubleshoot problems."
        }
    }
}

@MainActor
final class SettingsNavigation: ObservableObject {
    @Published var selection: SettingsSection? = .general
}

struct SettingsView: View {
    @ObservedObject var navigation: SettingsNavigation
    @ObservedObject var permissions: PermissionController
    @ObservedObject private var loginItemController = LoginItemController.shared
    @ObservedObject private var appUpdater = AppUpdater.shared
    @ObservedObject private var runner = AgentCommandRunner.shared
    @AppStorage(RuntimeSettings.useUserInstalledAgentCLIKey) private var useUserInstalledAgentCLI = false
    @AppStorage(RecordingSoundSettings.enabledKey) private var recordingSoundsEnabled = false
    @AppStorage(TranscriptionSettings.livePreviewOverlayEnabledKey) private var livePreviewOverlayEnabled = false
    @AppStorage(TranscriptionSettings.transcriptionBackendKey) private var transcriptionBackend = TranscriptionBackend.whisper.rawValue
    @AppStorage(TranscriptionSettings.transcriptionModelKey) private var transcriptionModel = TranscriptionBackend.whisper.defaultModelName
    @AppStorage(TranscriptionSettings.transcriptionModelTTLSecondsKey) private var transcriptionModelTTLSeconds = TranscriptionSettings.defaultModelTTLSeconds
    @AppStorage(TranscriptionSettings.transcriptionExtraInstructionsKey) private var transcriptionExtraInstructions = ""
    @State private var shortcutRevision = 0

    private var section: SettingsSection { navigation.selection ?? .general }
    private var backend: TranscriptionBackend { TranscriptionBackend(rawValue: transcriptionBackend) ?? .whisper }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(section.rawValue).font(.largeTitle.weight(.bold))
                    Text(section.subtitle).foregroundStyle(.secondary)
                }
                .padding(28)
                Divider()
                if section == .permissions {
                    PermissionsView(controller: permissions)
                } else {
                    Form {
                        switch section {
                        case .general: generalSettings
                        case .recording: recordingSettings
                        case .shortcuts: shortcutSettings
                        case .advanced: advancedSettings
                        case .permissions: EmptyView()
                        }
                    }
                    .formStyle(.grouped)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(minWidth: 780, minHeight: 600)
        .background(Color(nsColor: .windowBackgroundColor))
        .onChange(of: transcriptionBackend) { _ in normalizeModel() }
        .onAppear {
            loginItemController.refresh()
            normalizeModel()
            shortcutRevision += 1
        }
        .task { await permissions.refresh() }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "waveform.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(Color.accentColor)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Agent CLI").font(.headline)
                    Text("Settings").font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(20)
            List(selection: $navigation.selection) {
                ForEach(SettingsSection.allCases) { item in
                    HStack {
                        Label(item.rawValue, systemImage: item.symbol)
                        Spacer(minLength: 0)
                        if item == .permissions && permissions.needsSetup {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundStyle(.orange)
                                .accessibilityLabel("Setup needed")
                        }
                    }
                    .padding(.vertical, 5)
                    .tag(item)
                }
            }
            .listStyle(.sidebar)
            Text("Always here in your menu bar.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(20)
        }
        .frame(width: 200)
        .background(.regularMaterial)
    }

    @ViewBuilder private var generalSettings: some View {
        Section {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: permissions.needsSetup ? "hand.raised.fill" : "checkmark.circle.fill")
                    .foregroundStyle(permissions.needsSetup ? Color.orange : Color.green)
                    .font(.title2)
                VStack(alignment: .leading, spacing: 5) {
                    Text(permissions.needsSetup ? "Finish setting up Agent CLI" : "Ready to record")
                        .font(.headline)
                    Text(permissions.needsSetup
                         ? "Review access for recording, Fn shortcuts, and automatic text insertion."
                         : permissions.accessibility == .granted
                            ? "Microphone and Accessibility access are enabled."
                            : "Record to the clipboard from the menu bar. Enable Accessibility for Fn shortcuts and automatic text insertion.")
                        .foregroundStyle(.secondary)
                    Button(permissions.needsSetup ? "Review Permissions…" : "Manage Permissions…") {
                        navigation.selection = .permissions
                    }
                    .padding(.top, 4)
                }
            }
            .padding(.vertical, 6)
        }
        Section {
            Toggle("Start at login", isOn: Binding(
                get: { loginItemController.presentation.isEnabled },
                set: { loginItemController.setEnabled($0) }
            ))
            .disabled(!loginItemController.presentation.canToggle)
            if !loginItemController.detailText.isEmpty {
                Text(loginItemController.detailText).font(.callout).foregroundStyle(.secondary)
            }
        } header: {
            Text("Startup")
        } footer: {
            Text("Keep Agent CLI available in the menu bar when you sign in to your Mac.")
        }
        Section {
            LabeledContent("Version", value: AppMetadata.versionDisplayString)
            Button("Check for Updates…") { appUpdater.checkForUpdates() }
                .disabled(!appUpdater.canCheckForUpdates)
        } header: {
            Text("App Updates")
        } footer: {
            Text(appUpdater.canCheckForUpdates
                 ? "Check for a newer version of the macOS app."
                 : "App updates are not configured for this build.")
        }
    }

    @ViewBuilder private var recordingSettings: some View {
        Section("While Recording") {
            Toggle("Play start and stop sounds", isOn: $recordingSoundsEnabled)
            Toggle("Show live transcription preview", isOn: $livePreviewOverlayEnabled)
            Text("Preview shows provisional text above the recording meter.")
                .font(.callout).foregroundStyle(.secondary)
        }
        Section {
            Picker("Speech engine", selection: $transcriptionBackend) {
                ForEach(TranscriptionBackend.allCases) { Text($0.title).tag($0.rawValue) }
            }
            Picker("Model", selection: $transcriptionModel) {
                ForEach(backend.modelOptions) { Text($0.title).tag($0.id) }
            }
            Stepper(value: Binding(
                get: { max(0, transcriptionModelTTLSeconds) },
                set: { transcriptionModelTTLSeconds = max(0, $0) }
            ), in: 0...86_400, step: 60) {
                LabeledContent("Unload model after", value: Self.formatTTL(transcriptionModelTTLSeconds))
            }
        } header: {
            Text("Local Speech Model")
        } footer: {
            Text(useUserInstalledAgentCLI
                 ? "Your installed CLI manages these settings. Switch runtimes in Advanced to use the app's model settings."
                 : "Free memory after this much idle time. Choose Never to keep the model loaded. Changes apply the next time the voice service is prepared.")
        }
        .disabled(useUserInstalledAgentCLI)
        Section {
            TextEditor(text: $transcriptionExtraInstructions)
                .font(.body)
                .frame(minHeight: 90)
                .scrollContentBackground(.hidden)
                .accessibilityLabel("Transcription vocabulary and instructions")
        } header: {
            Text("Vocabulary & Instructions")
        } footer: {
            Text(backend == .nemo && !useUserInstalledAgentCLI
                 ? "The bundled NeMo engine does not use text instructions. Your instructions are kept for Whisper."
                 : "Add names, technical terms, or context to help the speech model. For example: “Kubernetes, Nijholt, Agent CLI.”")
        }
    }

    @ViewBuilder private var shortcutSettings: some View {
        Section {
            ShortcutRecorderRow(title: "Start or stop recording", name: .toggleTranscription, revision: shortcutRevision)
            ShortcutRecorderRow(title: "Hold to record and insert", name: .holdToTranscribe, revision: shortcutRevision)
        } header: { Text("Transcription") } footer: {
            Text("Toggle recording to copy a transcript. Hold the shortcut, speak, then release to insert text into your current app.")
        }
        Section("Clipboard Tools") {
            ShortcutRecorderRow(title: "Autocorrect clipboard", name: .autocorrect, revision: shortcutRevision)
            ShortcutRecorderRow(title: "Voice edit clipboard", name: .voiceEdit, revision: shortcutRevision)
        }
        Section {
            Button("Restore Default Shortcuts") {
                ShortcutSummaryState.shared.resetDefaults()
                shortcutRevision += 1
            }
            if permissions.accessibility != .granted {
                Button("Enable Accessibility for Fn Shortcuts…") { navigation.selection = .permissions }
            }
        } footer: {
            Text("Click a shortcut and press your keys. Delete clears it; Escape cancels. Defaults: Fn+Space, Fn, ⇧⌘A, and ⇧⌘V.")
        }
    }

    @ViewBuilder private var advancedSettings: some View {
        Section {
            Toggle("Use my installed agent-cli", isOn: $useUserInstalledAgentCLI)
            Text(useUserInstalledAgentCLI
                 ? "Uses agent-cli from your shell's PATH and your existing configuration."
                 : "The app manages a private agent-cli runtime. Recommended for most users.")
                .font(.callout).foregroundStyle(.secondary)
            Button(useUserInstalledAgentCLI ? "Check Installed CLI" : "Update CLI Runtime") { runner.run(.installOrUpdateCLI) }
                .disabled(runner.isRunning || runner.isRecording)
        } header: { Text("CLI Runtime") }
        Section("Voice Service") {
            Text(runner.statusMessage).foregroundStyle(.secondary).textSelection(.enabled)
            HStack {
                Button("Check Status") { runner.run(.voiceServiceStatus) }
                Button("Reinstall Voice Service…") { runner.run(.installVoiceService) }
            }
            .disabled(runner.isRunning || runner.isRecording)
        }
        Section("Diagnostics") {
            Button("Open Logs Folder") { runner.openLogsFolder() }
            Button("Open Config Folder") { runner.openConfigFolder() }
            if !runner.lastOutput.isEmpty {
                Button("Copy Last Output") { runner.copyLastOutput() }
            }
            if runner.hasLastError {
                Button("Open Last Error") { runner.openLastError() }
                Button("Copy Last Error") { runner.copyLastError() }
            }
        }
    }

    private func normalizeModel() {
        guard backend.modelOption(named: transcriptionModel) == nil else { return }
        transcriptionModel = backend.defaultModelName
    }

    private static func formatTTL(_ seconds: Int) -> String {
        let seconds = max(0, seconds)
        if seconds == 0 { return "Never" }
        if seconds < 60 { return "\(seconds) seconds" }
        if seconds < 3_600 { return "\(seconds / 60) minutes" }
        let hours = seconds / 3_600
        let minutes = (seconds % 3_600) / 60
        return minutes == 0 ? "\(hours) hours" : "\(hours)h \(minutes)m"
    }
}
