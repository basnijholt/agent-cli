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
            Task { @MainActor in
                onStatus("Transcript copied. Enable Accessibility in Settings > Permissions to insert text automatically.")
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
