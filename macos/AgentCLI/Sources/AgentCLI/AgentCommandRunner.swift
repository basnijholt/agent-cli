import AppKit
import ApplicationServices
import Carbon.HIToolbox
import Foundation
import SwiftUI
import UserNotifications

private enum HoldTranscriptionState {
    case idle
    case recording
    case awaitingPid
    case stopping

    var isFinishing: Bool {
        switch self {
        case .awaitingPid, .stopping:
            return true
        case .idle, .recording:
            return false
        }
    }
}

final class AgentCommandRunner: ObservableObject {
    static let shared = AgentCommandRunner()

    @Published var statusMessage = "Ready"
    @Published var lastOutput = ""
    @Published private(set) var hasLastError = false
    @Published private(set) var isRecording = false
    @Published private var activeCommandCount = 0
    private var recordingCommandCount = 0
    private var activeRecordingCommands: [String: Int] = [:]
    private var pendingStopRecordingCommands: Set<String> = []
    private var holdTranscriptionState: HoldTranscriptionState = .idle
    private var holdToTranscribePasteTarget: FocusedTextTarget?
    private var pasteAfterRecordingCommands: Set<String> = []

    var isRunning: Bool {
        activeCommandCount > 0
    }

    var menuStatusMessage: String {
        if isRecording {
            return "Recording"
        }
        if holdTranscriptionState.isFinishing {
            return "Transcribing..."
        }
        if hasLastError && statusMessage.localizedCaseInsensitiveContains("failed") {
            return "Last command failed"
        }
        return Self.compactMenuStatus(statusMessage)
    }

    private init() {
        hasLastError = FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path)
    }

    private static let menuStatusMaxLength = 72
    private static let notificationSettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!
    ]
    private static let accessibilitySettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Security-Privacy.extension?Privacy_Accessibility")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
    ]
    private static let holdStopShell = #""$AGENTCLI_AGENT_CLI" transcribe --stop --quiet"#

    func beginHoldToTranscribe() {
        guard holdTranscriptionState == .idle else {
            if holdTranscriptionState.isFinishing {
                statusMessage = "Finishing previous hold-to-transcribe request"
            }
            return
        }
        guard !isRecordingCommand(.toggleTranscription), !isStopPending(for: .toggleTranscription) else {
            statusMessage = "Transcription is already recording"
            return
        }

        holdTranscriptionState = .recording
        holdToTranscribePasteTarget = FocusedTextTarget.capture()
        pasteAfterRecordingCommands.insert(AgentCommand.toggleTranscription.identifier)
        run(.toggleTranscription)
    }

    func endHoldToTranscribe() {
        guard holdTranscriptionState == .recording else { return }
        holdTranscriptionState = .awaitingPid

        let wasRecording = isRecordingCommand(.toggleTranscription)
        if wasRecording {
            endRecordingIndicator(for: .toggleTranscription)
            statusMessage = "Transcribing..."
            stopHeldTranscriptionWhenReady()
        } else {
            statusMessage = "Stopping transcription as soon as it starts..."
        }
    }

    func run(_ command: AgentCommand) {
        let isStopRequest = command.showsRecordingIndicator && isRecordingCommand(command)
        let shouldStartRecording = command.showsRecordingIndicator && !isStopRequest

        if isStopRequest && isStopPending(for: command) {
            statusMessage = "Stop already requested for \(command.title)"
            return
        }

        if isStopRequest {
            markStopRequested(for: command)
        }

        activeCommandCount += 1
        statusMessage = isStopRequest
            ? "Stopping \(command.title)..."
            : "Running \(command.title)..."

        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrap = command.requiresWhisperDaemon
                ? AgentRuntime.shared.ensureTranscriptionReady(force: command.forceBootstrap)
                : AgentRuntime.shared.ensureInstalled(force: command.forceBootstrap)
            guard bootstrap.exitCode == 0 else {
                let message = Self.statusMessage(for: command, result: bootstrap)
                let notificationTitle = Self.notificationTitle(for: command, result: bootstrap)
                let notificationBody = Self.notificationBody(for: command, result: bootstrap, statusMessage: message)
                DispatchQueue.main.async {
                    if isStopRequest {
                        self.clearStopRequested(for: command)
                    }
                    if shouldStartRecording {
                        self.clearPasteAfterRecording(for: command)
                    }
                    self.clearHoldTranscriptionState(for: command)
                    self.activeCommandCount = max(0, self.activeCommandCount - 1)
                    self.lastOutput = bootstrap.output
                    self.recordFailure(command: command, result: bootstrap)
                    self.statusMessage = message
                    self.notify(title: notificationTitle, body: notificationBody)
                }
                return
            }

            if shouldStartRecording {
                DispatchQueue.main.async {
                    self.beginRecordingIndicator(for: command)
                    self.notifyStart(for: command)
                }
            }

            let result = Self.execute(command.shell)
            let message = Self.statusMessage(for: command, result: result)
            let notificationTitle = Self.notificationTitle(for: command, result: result)
            let notificationBody = Self.notificationBody(for: command, result: result, statusMessage: message)

            DispatchQueue.main.async {
                if shouldStartRecording {
                    self.clearHoldTranscriptionState(for: command)
                    let shouldPaste = self.shouldPasteAfterRecording(for: command) && result.exitCode == 0
                    let pasteTarget = self.holdToTranscribePasteTarget
                    self.endRecordingIndicator(for: command)
                    self.clearStopRequested(for: command)
                    if shouldPaste {
                        self.pasteTranscriptIntoFocusedField(result.output, for: command, target: pasteTarget)
                    }
                    self.clearPasteAfterRecording(for: command)
                }
                self.activeCommandCount = max(0, self.activeCommandCount - 1)

                if isStopRequest && result.exitCode == 0 {
                    if !result.output.isEmpty {
                        self.lastOutput = result.output
                    }
                    self.statusMessage = "Stop requested for \(command.title)"
                    return
                }

                if isStopRequest {
                    self.clearStopRequested(for: command)
                }
                self.lastOutput = result.output
                if result.exitCode != 0 {
                    self.recordFailure(command: command, result: result)
                }
                self.statusMessage = message
                self.notify(title: notificationTitle, body: notificationBody)
            }
        }
    }

    private func notifyStart(for command: AgentCommand) {
        guard let title = command.startNotificationTitle else { return }
        notify(title: title, body: command.startNotificationBody ?? "")
    }

    private func stopHeldTranscriptionWhenReady() {
        guard holdTranscriptionState == .awaitingPid else { return }

        holdTranscriptionState = .stopping
        statusMessage = "Stopping Toggle Transcription..."

        DispatchQueue.global(qos: .userInitiated).async {
            let result = Self.execute(Self.holdStopShell)

            DispatchQueue.main.async {
                if result.exitCode == 0 {
                    if self.holdTranscriptionState == .stopping {
                        self.statusMessage = "Transcribing..."
                    }
                    return
                }

                self.holdTranscriptionState = .idle
                let message = result.output.isEmpty
                    ? "Toggle Transcription stop failed with exit code \(result.exitCode)"
                    : "Toggle Transcription stop failed: \(result.output)"
                self.lastOutput = result.output
                self.recordFailure(title: "Toggle Transcription Stop", result: result)
                self.statusMessage = message
                self.notify(title: "Toggle Transcription Failed", body: Self.errorNotificationBody(message))
            }
        }
    }

    private func isRecordingCommand(_ command: AgentCommand) -> Bool {
        activeRecordingCommands[command.identifier, default: 0] > 0
    }

    private func isStopPending(for command: AgentCommand) -> Bool {
        pendingStopRecordingCommands.contains(command.identifier)
    }

    private func markStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.insert(command.identifier)
    }

    private func clearStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.remove(command.identifier)
    }

    private func shouldPasteAfterRecording(for command: AgentCommand) -> Bool {
        pasteAfterRecordingCommands.contains(command.identifier)
    }

    private func clearPasteAfterRecording(for command: AgentCommand) {
        pasteAfterRecordingCommands.remove(command.identifier)
        if command.identifier == AgentCommand.toggleTranscription.identifier {
            holdToTranscribePasteTarget = nil
        }
    }

    private func clearHoldTranscriptionState(for command: AgentCommand) {
        guard command.identifier == AgentCommand.toggleTranscription.identifier else { return }
        holdTranscriptionState = .idle
    }

    private func beginRecordingIndicator(for command: AgentCommand) {
        activeRecordingCommands[command.identifier, default: 0] += 1
        recordingCommandCount += 1
        isRecording = true
        VoiceLevelOverlayController.shared.show()
        if command.identifier == AgentCommand.toggleTranscription.identifier,
           holdTranscriptionState == .awaitingPid {
            endRecordingIndicator(for: command)
            stopHeldTranscriptionWhenReady()
        }
    }

    private func endRecordingIndicator(for command: AgentCommand) {
        let activeCommandCount = max(0, activeRecordingCommands[command.identifier, default: 0] - 1)
        if activeCommandCount > 0 {
            activeRecordingCommands[command.identifier] = activeCommandCount
        } else {
            activeRecordingCommands.removeValue(forKey: command.identifier)
        }
        recordingCommandCount = max(0, recordingCommandCount - 1)
        isRecording = recordingCommandCount > 0
        if !isRecording {
            VoiceLevelOverlayController.shared.hide()
        }
    }

    private func pasteTranscriptIntoFocusedField(
        _ transcript: String,
        for command: AgentCommand,
        target: FocusedTextTarget?
    ) {
        _ = command

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(transcript, forType: .string)

        guard AXIsProcessTrusted() else {
            requestAccessibilityPermissionIfNeeded()
            statusMessage = "Transcript copied. Allow Accessibility permission to auto-insert text."
            return
        }

        target?.refocus()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.20) {
            self.postPasteShortcut()
            self.statusMessage = "Inserted transcript"
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

    func copyLastOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(lastOutput, forType: .string)
        statusMessage = "Copied last output"
    }

    func openLastError() {
        guard FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path) else {
            hasLastError = false
            statusMessage = "No last error recorded"
            return
        }

        if NSWorkspace.shared.open(AgentRuntime.shared.lastErrorURL) {
            statusMessage = "Opened last error"
        } else {
            statusMessage = "Could not open last error"
        }
    }

    func copyLastError() {
        guard let details = try? String(contentsOf: AgentRuntime.shared.lastErrorURL),
              !details.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            hasLastError = false
            statusMessage = "No last error recorded"
            return
        }

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(details, forType: .string)
        statusMessage = "Copied last error"
    }

    func openLogsFolder() {
        let url = AgentRuntime.shared.logsURL

        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            if NSWorkspace.shared.open(url) {
                statusMessage = "Opened logs folder"
            } else {
                statusMessage = "Could not open logs folder"
            }
        } catch {
            statusMessage = "Could not open logs folder: \(error.localizedDescription)"
        }
    }

    func openConfigFolder() {
        let url = AgentRuntime.shared.appSupportURL.appendingPathComponent("config", isDirectory: true)

        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            NSWorkspace.shared.open(url)
            statusMessage = "Opened config folder"
        } catch {
            statusMessage = "Could not open config folder: \(error.localizedDescription)"
        }
    }

    func notificationsDisabled() {
        statusMessage = "Notifications are disabled. Use Open Notification Settings to enable Agent CLI notifications."
    }

    func openNotificationSettings() {
        for url in Self.notificationSettingsURLs where NSWorkspace.shared.open(url) {
            statusMessage = "Opened Notification Settings"
            return
        }
        statusMessage = "Could not open Notification Settings"
    }

    func openAccessibilitySettings() {
        for url in Self.accessibilitySettingsURLs where NSWorkspace.shared.open(url) {
            statusMessage = "Opened Accessibility Settings. Accessibility permission controls auto-inserting transcripts."
            return
        }
        statusMessage = "Could not open Accessibility Settings"
    }

    private static func execute(_ shell: String) -> CommandResult {
        AgentRuntime.shared.runShell(shell)
    }

    @discardableResult
    private func recordFailure(command: AgentCommand, result: CommandResult) -> String {
        recordFailure(title: command.title, result: result)
    }

    @discardableResult
    private func recordFailure(title: String, result: CommandResult) -> String {
        let output = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
        let details = """
        Agent CLI Error
        Time: \(ISO8601DateFormatter().string(from: Date()))
        Context: \(title)
        Exit code: \(result.exitCode)

        Output:
        \(output.isEmpty ? "(no output)" : output)
        """

        do {
            try FileManager.default.createDirectory(
                at: AgentRuntime.shared.appSupportURL,
                withIntermediateDirectories: true
            )
            try details.write(to: AgentRuntime.shared.lastErrorURL, atomically: true, encoding: .utf8)
            hasLastError = true
        } catch {
            lastOutput = details
            hasLastError = false
        }

        return details
    }

    private static func statusMessage(for command: AgentCommand, result: CommandResult) -> String {
        let summary = command.identifier == "voice-service-status"
            ? voiceServiceStatusMessage(result.output)
            : summarize(result.output)
        if result.exitCode == 0 {
            return summary.isEmpty ? "\(command.title) finished" : summary
        }
        return summary.isEmpty
            ? "\(command.title) failed with exit code \(result.exitCode)"
            : "\(command.title) failed: \(summary)"
    }

    private static let voiceServiceLogPath = "~/Library/Logs/agent-cli-whisper/"

    private static func voiceServiceStatusMessage(_ output: String) -> String {
        let lines = output
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        guard let statusLine = lines.first(where: { $0.localizedCaseInsensitiveContains("whisper:") }) else {
            return summarize(output)
        }

        let lowerStatus = statusLine.lowercased()
        if lowerStatus.contains("installed but not running") {
            return "Whisper is installed but not running.\nLogs: \(voiceServiceLogPath)"
        }
        if lowerStatus.contains("not installed") {
            return "Whisper is not installed. Use Troubleshooting > Reinstall Voice Service."
        }
        if lowerStatus.contains("running") {
            let pidSuffix = statusLine.range(of: "(pid ").map { " " + statusLine[$0.lowerBound...] } ?? ""
            return "Whisper is running\(pidSuffix)\nLogs: \(voiceServiceLogPath)"
        }

        return summarize(output)
    }

    private static func notificationTitle(for command: AgentCommand, result: CommandResult) -> String {
        if result.exitCode == 0 {
            return command.finishNotificationTitle ?? command.title
        }
        return "\(command.title) Failed"
    }

    private static func notificationBody(
        for command: AgentCommand,
        result: CommandResult,
        statusMessage: String
    ) -> String {
        if result.exitCode != 0 {
            return errorNotificationBody(statusMessage)
        }

        if command.finishNotificationTitle != nil, result.exitCode == 0 {
            let transcript = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
            if !transcript.isEmpty {
                return transcript
            }
        }
        return statusMessage
    }

    private static func errorNotificationBody(_ statusMessage: String) -> String {
        "\(statusMessage)\nFull error saved. Open Agent CLI > Open Last Error for details."
    }

    private static func summarize(_ output: String) -> String {
        output
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .suffix(4)
            .joined(separator: " ")
    }

    private static func compactMenuStatus(_ status: String) -> String {
        let summary = summarize(status)
        guard !summary.isEmpty else {
            return "Ready"
        }
        guard summary.count > menuStatusMaxLength else {
            return summary
        }
        return "Last output available"
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body

        if let logoURL = AgentRuntime.shared.notificationLogoURL,
           let attachment = try? UNNotificationAttachment(
               identifier: "agentcli-logo",
               url: logoURL
           ) {
            content.attachments = [attachment]
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }
}
