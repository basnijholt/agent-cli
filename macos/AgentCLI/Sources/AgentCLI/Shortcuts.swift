import AppKit
import Carbon.HIToolbox
import Foundation
import KeyboardShortcuts
import SwiftUI

extension KeyboardShortcuts.Name {
    static let toggleTranscription = Self(
        "toggleTranscription",
        default: KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)
    )
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
        KeyboardShortcuts.reset(
            .toggleTranscription,
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
        if event.modifierFlags.contains(.function) {
            carbonModifiers |= kEventKeyModifierFnMask
        }
        return KeyboardShortcuts.Shortcut(
            carbonKeyCode: shortcut.carbonKeyCode,
            carbonModifiers: carbonModifiers
        )
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
            to: KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)
        )
        migrateDefault(
            name: .holdToTranscribe,
            from: KeyboardShortcuts.Shortcut(.space, modifiers: [.control, .option]),
            to: KeyboardShortcuts.Shortcut(.function)
        )
    }

    private static func migrateDefault(
        name: KeyboardShortcuts.Name,
        from oldShortcut: KeyboardShortcuts.Shortcut,
        to newShortcut: KeyboardShortcuts.Shortcut
    ) {
        guard KeyboardShortcuts.getShortcut(for: name) == oldShortcut else {
            return
        }
        KeyboardShortcuts.setShortcut(newShortcut, for: name)
    }
}

struct SettingsView: View {
    @ObservedObject private var loginItemController = LoginItemController.shared
    @State private var shortcutRevision = 0

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
            } header: {
                Text("General")
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
        .onAppear {
            loginItemController.refresh()
        }
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
            stopRecording()
        case kVK_Delete, kVK_ForwardDelete:
            KeyboardShortcuts.setShortcut(nil, for: shortcutName)
            stopRecording()
        default:
            guard let shortcut = ShortcutDisplay.shortcut(from: event) else {
                NSSound.beep()
                return
            }
            KeyboardShortcuts.setShortcut(shortcut, for: shortcutName)
            stopRecording()
        }
    }

    private func stopRecording() {
        if let eventMonitor {
            NSEvent.removeMonitor(eventMonitor)
            self.eventMonitor = nil
        }
        isRecording = false
        updateTitle()
        ShortcutSummaryState.shared.refresh()
    }
}
