import AppKit
import Carbon.HIToolbox
import Foundation
import KeyboardShortcuts
import SwiftUI

extension KeyboardShortcuts.Name {
    static let toggleTranscription = Self("toggleTranscription")
    static let holdToTranscribe = Self(
        "holdToTranscribe",
        default: KeyboardShortcuts.Shortcut(.function)
    )
    static let autocorrect = Self(
        "autocorrect",
        default: KeyboardShortcuts.Shortcut(.a, modifiers: [.command, .shift])
    )
    static let voiceEdit = Self(
        "voiceEdit",
        default: KeyboardShortcuts.Shortcut(.v, modifiers: [.command, .shift])
    )
}

enum ToggleTranscriptionDefault {
    static let shortcut = FunctionShortcutPersistence.rawShortcut(
        carbonKeyCode: kVK_Space,
        carbonModifiers: kEventKeyModifierFnMask
    )

    static func set() {
        FunctionShortcutPersistence.set(shortcut, for: .toggleTranscription)
    }

    static func seedIfNeeded() {
        guard !userDefaultsContainsShortcut else {
            return
        }
        set()
    }

    private static var userDefaultsContainsShortcut: Bool {
        UserDefaults.standard.object(forKey: userDefaultsKey) != nil
    }

    private static var userDefaultsKey: String {
        "KeyboardShortcuts_\(KeyboardShortcuts.Name.toggleTranscription.rawValue)"
    }
}

enum FunctionShortcutPersistence {
    static func rawShortcut(carbonKeyCode: Int, carbonModifiers: Int) -> KeyboardShortcuts.Shortcut {
        // KeyboardShortcuts' public initializer normalizes away Fn, but Codable preserves raw Carbon modifiers.
        let shortcutJSON = """
        {"carbonKeyCode":\(carbonKeyCode),"carbonModifiers":\(carbonModifiers)}
        """
        guard let data = shortcutJSON.data(using: .utf8),
              let shortcut = try? JSONDecoder().decode(KeyboardShortcuts.Shortcut.self, from: data) else {
            return KeyboardShortcuts.Shortcut(
                carbonKeyCode: carbonKeyCode,
                carbonModifiers: carbonModifiers
            )
        }
        return shortcut
    }

    static func set(_ shortcut: KeyboardShortcuts.Shortcut, for name: KeyboardShortcuts.Name) {
        KeyboardShortcuts.setShortcut(nil, for: name)
        guard let encoded = try? JSONEncoder().encode(shortcut),
              let encodedString = String(data: encoded, encoding: .utf8) else {
            return
        }
        UserDefaults.standard.set(encodedString, forKey: userDefaultsKey(for: name))
    }

    private static func userDefaultsKey(for name: KeyboardShortcuts.Name) -> String {
        "KeyboardShortcuts_\(name.rawValue)"
    }
}

private extension KeyboardShortcuts.Shortcut {
    var usesFunctionModifier: Bool {
        carbonModifiers & kEventKeyModifierFnMask != 0
    }
}

final class ShortcutRecordingState {
    static let shared = ShortcutRecordingState()

    private let lock = NSLock()
    private var activeRecorderCount = 0

    var isRecording: Bool {
        lock.lock()
        defer { lock.unlock() }
        return activeRecorderCount > 0
    }

    private init() {}

    func beginRecording() {
        lock.lock()
        activeRecorderCount += 1
        lock.unlock()
    }

    func endRecording() {
        lock.lock()
        activeRecorderCount = max(0, activeRecorderCount - 1)
        lock.unlock()
    }
}

final class ShortcutSummaryState: ObservableObject {
    static let shared = ShortcutSummaryState()

    @Published private(set) var summary = ""

    private init() {
        refresh()
    }

    func refresh() {
        summary = Self.makeSummary()
    }

    func resetDefaults() {
        ToggleTranscriptionDefault.set()
        KeyboardShortcuts.reset(
            .holdToTranscribe,
            .autocorrect,
            .voiceEdit
        )
        refresh()
    }

    private static func makeSummary() -> String {
        let shortcuts: [(label: String, name: KeyboardShortcuts.Name)] = [
            ("Toggle", .toggleTranscription),
            ("Hold", .holdToTranscribe),
            ("Autocorrect", .autocorrect),
            ("Voice Edit", .voiceEdit)
        ]

        return "Hotkeys: " + shortcuts
            .map { "\($0.label) \(label(for: $0.name))" }
            .joined(separator: " / ")
    }

    private static func label(for name: KeyboardShortcuts.Name) -> String {
        ShortcutDisplay.label(for: name)
    }
}

private enum ShortcutDisplay {
    static func label(for name: KeyboardShortcuts.Name) -> String {
        guard let shortcut = KeyboardShortcuts.getShortcut(for: name) else {
            return "Not Set"
        }

        return label(
            for: shortcut,
            fallback: KeyboardShortcuts.getShortcut(for: name)?.description ?? "Not Set"
        )
    }

    static func shortcut(from event: NSEvent) -> KeyboardShortcuts.Shortcut? {
        if event.type == .flagsChanged,
           Int(event.keyCode) == kVK_Function,
           event.modifierFlags.contains(.function) {
            return KeyboardShortcuts.Shortcut(.function)
        }

        guard let shortcut = KeyboardShortcuts.Shortcut(event: event) else {
            return nil
        }

        var carbonModifiers = shortcut.carbonModifiers
        if event.modifierFlags.contains(.function),
           shouldTreatFunctionFlagAsModifier(for: shortcut.carbonKeyCode) {
            carbonModifiers |= kEventKeyModifierFnMask
        }

        guard carbonModifiers & kEventKeyModifierFnMask != 0 else {
            return KeyboardShortcuts.Shortcut(
                carbonKeyCode: shortcut.carbonKeyCode,
                carbonModifiers: carbonModifiers
            )
        }

        return FunctionShortcutPersistence.rawShortcut(
            carbonKeyCode: shortcut.carbonKeyCode,
            carbonModifiers: carbonModifiers
        )
    }

    private static func shouldTreatFunctionFlagAsModifier(for carbonKeyCode: Int) -> Bool {
        !isFunctionRowKey(carbonKeyCode)
    }

    private static func isFunctionRowKey(_ carbonKeyCode: Int) -> Bool {
        switch carbonKeyCode {
        case kVK_F1,
             kVK_F2,
             kVK_F3,
             kVK_F4,
             kVK_F5,
             kVK_F6,
             kVK_F7,
             kVK_F8,
             kVK_F9,
             kVK_F10,
             kVK_F11,
             kVK_F12,
             kVK_F13,
             kVK_F14,
             kVK_F15,
             kVK_F16,
             kVK_F17,
             kVK_F18,
             kVK_F19,
             kVK_F20:
            return true
        default:
            return false
        }
    }

    private static func label(for shortcut: KeyboardShortcuts.Shortcut, fallback: String) -> String {
        if shortcut.carbonKeyCode == kVK_Function, shortcut.carbonModifiers == 0 {
            return "Fn"
        }

        guard shortcut.carbonModifiers & kEventKeyModifierFnMask != 0 else {
            return fallback
        }

        let remainingModifiers = shortcut.carbonModifiers & ~kEventKeyModifierFnMask
        let displayShortcut = KeyboardShortcuts.Shortcut(
            carbonKeyCode: shortcut.carbonKeyCode,
            carbonModifiers: remainingModifiers
        )
        return "Fn+\(keyLabel(for: displayShortcut))"
    }

    private static func keyLabel(for shortcut: KeyboardShortcuts.Shortcut) -> String {
        if shortcut.carbonKeyCode == kVK_Space {
            return "Space"
        }
        return shortcut.description
    }
}

enum ShortcutDefaultsMigrator {
    static func migrate() {
        migrateDefault(
            name: .toggleTranscription,
            from: KeyboardShortcuts.Shortcut(.r, modifiers: [.command, .shift]),
            to: ToggleTranscriptionDefault.shortcut
        )
        migrateDefault(
            name: .toggleTranscription,
            from: KeyboardShortcuts.Shortcut(.space),
            to: ToggleTranscriptionDefault.shortcut
        )
        migrateDefault(
            name: .holdToTranscribe,
            from: KeyboardShortcuts.Shortcut(.space, modifiers: [.control, .option]),
            to: KeyboardShortcuts.Shortcut(.function)
        )
        ToggleTranscriptionDefault.seedIfNeeded()
    }

    private static func migrateDefault(
        name: KeyboardShortcuts.Name,
        from oldShortcut: KeyboardShortcuts.Shortcut,
        to newShortcut: KeyboardShortcuts.Shortcut
    ) {
        guard KeyboardShortcuts.getShortcut(for: name) == oldShortcut else {
            return
        }
        setShortcut(newShortcut, for: name)
    }

    private static func setShortcut(
        _ shortcut: KeyboardShortcuts.Shortcut,
        for name: KeyboardShortcuts.Name
    ) {
        guard name == .toggleTranscription,
              shortcut == ToggleTranscriptionDefault.shortcut else {
            KeyboardShortcuts.setShortcut(shortcut, for: name)
            return
        }
        ToggleTranscriptionDefault.set()
    }
}

struct SettingsView: View {
    @ObservedObject private var loginItemController = LoginItemController.shared
    @ObservedObject private var appUpdater = AppUpdater.shared
    @AppStorage(RuntimeSettings.useUserInstalledAgentCLIKey)
    private var useUserInstalledAgentCLI = false
    @AppStorage(RecordingSoundSettings.enabledKey)
    private var recordingSoundsEnabled = false
    @AppStorage(TranscriptionSettings.livePreviewOverlayEnabledKey)
    private var livePreviewOverlayEnabled = false
    @AppStorage(TranscriptionSettings.transcriptionBackendKey)
    private var transcriptionBackend = TranscriptionBackend.whisper.rawValue
    @AppStorage(TranscriptionSettings.transcriptionModelKey)
    private var transcriptionModel = TranscriptionBackend.whisper.defaultModelName
    @AppStorage(TranscriptionSettings.transcriptionModelTTLSecondsKey)
    private var transcriptionModelTTLSeconds = TranscriptionSettings.defaultModelTTLSeconds
    @AppStorage(TranscriptionSettings.transcriptionExtraInstructionsKey)
    private var transcriptionExtraInstructions = ""
    @State private var shortcutRevision = 0

    private var selectedTranscriptionBackend: TranscriptionBackend {
        TranscriptionBackend(rawValue: transcriptionBackend) ?? .whisper
    }

    var body: some View {
        Form {
            Section {
                Toggle(
                    "Start at Login",
                    isOn: Binding(
                        get: { loginItemController.presentation.isEnabled },
                        set: { loginItemController.setEnabled($0) }
                    )
                )
                .disabled(!loginItemController.presentation.canToggle)

                if !loginItemController.detailText.isEmpty {
                    Text(loginItemController.detailText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Toggle("Use User-Installed agent-cli", isOn: $useUserInstalledAgentCLI)
                Toggle("Play Recording Sounds", isOn: $recordingSoundsEnabled)
                Toggle("Show Live Transcription Preview", isOn: $livePreviewOverlayEnabled)
            } header: {
                Text("General")
            } footer: {
                Text("Runs the agent-cli found on PATH with your normal config instead of the app's private bundled-uv runtime. Live preview shows provisional transcription text above the recording meter.")
            }

            Section {
                Picker("Backend", selection: $transcriptionBackend) {
                    ForEach(TranscriptionBackend.allCases) { backend in
                        Text(backend.title).tag(backend.rawValue)
                    }
                }
                .pickerStyle(.menu)
                .disabled(useUserInstalledAgentCLI)

                Picker("Model", selection: $transcriptionModel) {
                    ForEach(selectedTranscriptionBackend.modelOptions) { model in
                        Text(model.title).tag(model.id)
                    }
                }
                .pickerStyle(.menu)
                .disabled(useUserInstalledAgentCLI)

                Stepper(
                    value: Binding(
                        get: { max(0, transcriptionModelTTLSeconds) },
                        set: { transcriptionModelTTLSeconds = max(0, $0) }
                    ),
                    in: 0...86_400,
                    step: 60
                ) {
                    HStack {
                        Text("Model TTL")
                        Spacer()
                        Text(Self.formatTTLSeconds(transcriptionModelTTLSeconds))
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                }
                .disabled(useUserInstalledAgentCLI)
            } header: {
                Text("Voice Service")
            } footer: {
                Text(
                    useUserInstalledAgentCLI
                        ? "Disabled while User-Installed agent-cli is active."
                        : "TTL is how long the selected model lives in memory after the last transcription. Set to 0 to keep it loaded until the voice service restarts."
                )
            }

            Section {
                TextEditor(text: $transcriptionExtraInstructions)
                    .font(.body)
                    .frame(minHeight: 96)
                    .scrollContentBackground(.hidden)
            } header: {
                Text("Transcription Instructions")
            } footer: {
                Text(
                    selectedTranscriptionBackend == .nemo && !useUserInstalledAgentCLI
                        ? "Parakeet does not support names or vocabulary as text prompt context, so this field has no effect for bundled NeMo transcription."
                        : "Names, vocabulary, and guidance to pass as initial transcription context."
                )
            }

            Section {
                HStack {
                    Text("Version")
                    Spacer()
                    Text(AppMetadata.versionDisplayString)
                        .foregroundStyle(.secondary)
                }

                Button("Check for Updates...") {
                    appUpdater.checkForUpdates()
                }
                .disabled(!appUpdater.canCheckForUpdates)
            } header: {
                Text("Updates")
            } footer: {
                Text(
                    appUpdater.canCheckForUpdates
                        ? "Uses Sparkle to install signed Agent CLI app updates."
                        : "App updates are not configured for this build."
                )
            }

            Section {
                ShortcutRecorderRow(
                    title: "Toggle Transcription",
                    name: .toggleTranscription,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Hold to Transcribe",
                    name: .holdToTranscribe,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Autocorrect Clipboard",
                    name: .autocorrect,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Voice Edit Clipboard",
                    name: .voiceEdit,
                    revision: shortcutRevision
                )

                Button("Reset Defaults") {
                    ShortcutSummaryState.shared.resetDefaults()
                    shortcutRevision += 1
                }
            } header: {
                Text("Keyboard Shortcuts")
            } footer: {
                Text("Defaults: Fn+Space, Fn, Cmd+Shift+A, Cmd+Shift+V. Click a shortcut field and press a new key combination. Press Delete to clear it or Escape to cancel.")
            }
        }
        .formStyle(.grouped)
        .padding()
        .onChange(of: transcriptionBackend) { _ in
            normalizeTranscriptionModel()
        }
        .onAppear {
            loginItemController.refresh()
            normalizeTranscriptionModel()
        }
    }

    private func normalizeTranscriptionModel() {
        let backend = selectedTranscriptionBackend
        guard backend.modelOption(named: transcriptionModel) == nil else { return }
        transcriptionModel = backend.defaultModelName
    }

    private static func formatTTLSeconds(_ seconds: Int) -> String {
        let clampedSeconds = max(0, seconds)
        if clampedSeconds == 0 {
            return "Never"
        }
        if clampedSeconds < 60 {
            return "\(clampedSeconds)s"
        }
        if clampedSeconds < 3_600 {
            return "\(clampedSeconds / 60)m"
        }

        let hours = clampedSeconds / 3_600
        let minutes = (clampedSeconds % 3_600) / 60
        if minutes == 0 {
            return "\(hours)h"
        }
        return "\(hours)h \(minutes)m"
    }
}

struct ShortcutRecorderRow: View {
    let title: String
    let name: KeyboardShortcuts.Name
    let revision: Int

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            ShortcutRecorder(name: name, revision: revision)
                .frame(width: 150)
        }
    }
}

struct ShortcutRecorder: NSViewRepresentable {
    let name: KeyboardShortcuts.Name
    let revision: Int

    func makeNSView(context: Context) -> ShortcutRecorderButton {
        ShortcutRecorderButton(name: name)
    }

    func updateNSView(_ nsView: ShortcutRecorderButton, context: Context) {
        _ = revision
        nsView.shortcutName = name
        nsView.updateTitle()
    }
}

final class ShortcutRecorderButton: NSButton {
    var shortcutName: KeyboardShortcuts.Name {
        didSet {
            updateTitle()
        }
    }

    private var isRecording = false
    private var eventMonitor: Any?
    private var pendingFunctionShortcut = false

    init(name: KeyboardShortcuts.Name) {
        self.shortcutName = name
        super.init(frame: .zero)
        bezelStyle = .rounded
        controlSize = .regular
        target = self
        action = #selector(startRecording)
        updateTitle()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        stopRecording()
    }

    override func viewWillMove(toWindow newWindow: NSWindow?) {
        super.viewWillMove(toWindow: newWindow)
        if newWindow == nil {
            stopRecording()
        }
    }

    func updateTitle() {
        guard !isRecording else { return }
        title = ShortcutDisplay.label(for: shortcutName)
    }

    @objc private func startRecording() {
        guard !isRecording else {
            stopRecording()
            return
        }

        isRecording = true
        ShortcutRecordingState.shared.beginRecording()
        title = "Press shortcut"
        window?.makeFirstResponder(self)

        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .flagsChanged]) { [weak self] event in
            guard let self, self.isRecording else {
                return event
            }
            self.capture(event)
            return nil
        }
    }

    private func capture(_ event: NSEvent) {
        switch Int(event.keyCode) {
        case kVK_Escape:
            pendingFunctionShortcut = false
            stopRecording()
        case kVK_Delete, kVK_ForwardDelete:
            pendingFunctionShortcut = false
            KeyboardShortcuts.setShortcut(nil, for: shortcutName)
            stopRecording()
        case kVK_Function:
            handleFunctionKeyChange(event)
        default:
            pendingFunctionShortcut = false
            guard let shortcut = ShortcutDisplay.shortcut(from: event) else {
                NSSound.beep()
                return
            }
            if shortcut.usesFunctionModifier {
                guard supportsFunctionChord(shortcutName) else {
                    NSSound.beep()
                    return
                }
                FunctionShortcutPersistence.set(shortcut, for: shortcutName)
            } else {
                KeyboardShortcuts.setShortcut(shortcut, for: shortcutName)
            }
            stopRecording()
        }
    }

    private func handleFunctionKeyChange(_ event: NSEvent) {
        guard event.type == .flagsChanged else {
            return
        }

        if event.modifierFlags.contains(.function) {
            pendingFunctionShortcut = true
            return
        }

        if pendingFunctionShortcut {
            captureBareFunctionShortcut()
        }
    }

    private func captureBareFunctionShortcut() {
        pendingFunctionShortcut = false
        KeyboardShortcuts.setShortcut(KeyboardShortcuts.Shortcut(.function), for: shortcutName)
        stopRecording()
    }

    private func supportsFunctionChord(_ name: KeyboardShortcuts.Name) -> Bool {
        name == .toggleTranscription || name == .holdToTranscribe
    }

    private func stopRecording() {
        if let eventMonitor {
            NSEvent.removeMonitor(eventMonitor)
            self.eventMonitor = nil
        }
        pendingFunctionShortcut = false
        let wasRecording = isRecording
        isRecording = false
        if wasRecording {
            ShortcutRecordingState.shared.endRecording()
        }
        updateTitle()
        ShortcutSummaryState.shared.refresh()
    }
}
