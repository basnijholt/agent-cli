import AppKit
import ApplicationServices
import Carbon.HIToolbox
import Foundation

struct TranscriptPasteController {
    func pasteTranscriptIntoFocusedField(
        _ transcript: String,
        target: FocusedTextTarget?,
        onStatus: @escaping @MainActor (String) -> Void
    ) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(transcript, forType: .string)

        guard AXIsProcessTrusted() else {
            requestAccessibilityPermissionIfNeeded()
            Task { @MainActor in
                onStatus("Transcript copied. Allow Accessibility permission to auto-insert text.")
            }
            return
        }

        target?.refocus()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.20) {
            postPasteShortcut()
            Task { @MainActor in
                onStatus("Inserted transcript")
            }
        }
    }

    private var accessibilityPromptMarkerContents: String {
        let executableURL = Bundle.main.executableURL ?? Bundle.main.bundleURL
        let executableValues = try? executableURL.resourceValues(forKeys: [.contentModificationDateKey])
        let executableModified = executableValues?.contentModificationDate?.timeIntervalSince1970 ?? 0
        return [
            "packageSource=\(AgentRuntime.shared.agentCLIPackageSource)",
            "executable=\(executableURL.path)",
            "executableModified=\(executableModified)"
        ].joined(separator: "\n") + "\n"
    }

    private func requestAccessibilityPermissionIfNeeded() {
        let accessibilityPromptMarkerContents = self.accessibilityPromptMarkerContents
        guard (try? String(contentsOf: AgentRuntime.shared.accessibilityPromptMarkerURL)) != accessibilityPromptMarkerContents else {
            return
        }

        try? FileManager.default.createDirectory(at: AgentRuntime.shared.appSupportURL, withIntermediateDirectories: true)
        try? accessibilityPromptMarkerContents.write(
            to: AgentRuntime.shared.accessibilityPromptMarkerURL,
            atomically: true,
            encoding: .utf8
        )

        // Equivalent to kAXTrustedCheckOptionPrompt as String, but Swift exposes it unmanaged.
        let promptOption = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let options = [promptOption: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
    }
}

private func postPasteShortcut() {
    let source = CGEventSource(stateID: .hidSystemState)
    let commandDown = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_Command), keyDown: true)
    let commandUp = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_Command), keyDown: false)
    let keyDown = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_V), keyDown: true)
    let keyUp = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_V), keyDown: false)
    commandDown?.flags = .maskCommand
    keyDown?.flags = .maskCommand
    keyUp?.flags = .maskCommand

    commandDown?.post(tap: .cghidEventTap)
    keyDown?.post(tap: .cghidEventTap)
    keyUp?.post(tap: .cghidEventTap)
    commandUp?.post(tap: .cghidEventTap)
}
