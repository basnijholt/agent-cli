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

@MainActor
final class AgentCommandRunner: ObservableObject {
    static let shared = AgentCommandRunner()

    @Published var statusMessage = "Ready"
    @Published var lastOutput = ""
    @Published private(set) var hasLastError = false
    @Published private(set) var isRecording = false
    @Published private var activeCommandCount = 0
    private let commandExecutor: AgentCommandExecutor
    private var recordingIndicator = RecordingIndicatorController()
    private let pasteController: TranscriptPasteController
    private let errorStore: AgentErrorStore
    private let notificationPresenter: AgentNotificationPresenter
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

    private init(
        commandExecutor: AgentCommandExecutor = AgentCommandExecutor(),
        pasteController: TranscriptPasteController = TranscriptPasteController(),
        errorStore: AgentErrorStore = AgentErrorStore(),
        notificationPresenter: AgentNotificationPresenter = AgentNotificationPresenter()
    ) {
        self.commandExecutor = commandExecutor
        self.pasteController = pasteController
        self.errorStore = errorStore
        self.notificationPresenter = notificationPresenter
        hasLastError = errorStore.hasLastError()
    }

    nonisolated private static let menuStatusMaxLength = 72
    private static let notificationSettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!
    ]
    private static let accessibilitySettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Security-Privacy.extension?Privacy_Accessibility")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
    ]
    func beginHoldToTranscribe() {
        guard holdTranscriptionState == .idle else {
            if holdTranscriptionState.isFinishing {
                statusMessage = "Finishing previous hold-to-transcribe request"
            }
            return
        }
        guard !recordingIndicator.isRecordingCommand(.toggleTranscription), !isStopPending(for: .toggleTranscription) else {
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

        let wasRecording = recordingIndicator.isRecordingCommand(.toggleTranscription)
        if wasRecording {
            endRecordingIndicator(for: .toggleTranscription)
            statusMessage = "Transcribing..."
            stopHeldTranscriptionWhenReady()
        } else {
            statusMessage = "Stopping transcription as soon as it starts..."
        }
    }

    func run(_ command: AgentCommand) {
        let isStopRequest = command.showsRecordingIndicator && recordingIndicator.isRecordingCommand(command)
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

        let commandExecutor = commandExecutor
        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrap = commandExecutor.prepare(command)
            guard bootstrap.exitCode == 0 else {
                let message = Self.statusMessage(for: command, result: bootstrap)
                let notificationTitle = Self.notificationTitle(for: command, result: bootstrap)
                let notificationBody = Self.notificationBody(for: command, result: bootstrap, statusMessage: message)
                Task { @MainActor in
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
                    self.notificationPresenter.notify(title: notificationTitle, body: notificationBody)
                }
                return
            }

            if shouldStartRecording {
                Task { @MainActor in
                    self.beginRecordingIndicator(for: command)
                    self.notificationPresenter.notifyStart(for: command)
                }
            }

            let result = commandExecutor.run(command)
            let message = Self.statusMessage(for: command, result: result)
            let notificationTitle = Self.notificationTitle(for: command, result: result)
            let notificationBody = Self.notificationBody(for: command, result: result, statusMessage: message)

            Task { @MainActor in
                if shouldStartRecording {
                    self.clearHoldTranscriptionState(for: command)
                    let shouldPaste = self.shouldPasteAfterRecording(for: command) && result.exitCode == 0
                    let pasteTarget = self.holdToTranscribePasteTarget
                    self.endRecordingIndicator(for: command)
                    self.clearStopRequested(for: command)
                    if shouldPaste {
                        self.pasteController.pasteTranscriptIntoFocusedField(result.output, target: pasteTarget) { message in
                            self.statusMessage = message
                        }
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
                self.notificationPresenter.notify(title: notificationTitle, body: notificationBody)
            }
        }
    }

    private func stopHeldTranscriptionWhenReady() {
        guard holdTranscriptionState == .awaitingPid else { return }

        holdTranscriptionState = .stopping
        statusMessage = "Stopping Toggle Transcription..."

        let commandExecutor = commandExecutor
        DispatchQueue.global(qos: .userInitiated).async {
            let result = commandExecutor.stopHeldTranscription()

            Task { @MainActor in
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
                self.notificationPresenter.notify(title: "Toggle Transcription Failed", body: Self.errorNotificationBody(message))
            }
        }
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
        recordingIndicator.begin(for: command)
        isRecording = recordingIndicator.isRecording
        if command.identifier == AgentCommand.toggleTranscription.identifier,
           holdTranscriptionState == .awaitingPid {
            endRecordingIndicator(for: command)
            stopHeldTranscriptionWhenReady()
        }
    }

    private func endRecordingIndicator(for command: AgentCommand) {
        recordingIndicator.end(for: command)
        isRecording = recordingIndicator.isRecording
    }

    func copyLastOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(lastOutput, forType: .string)
        statusMessage = "Copied last output"
    }

    func openLastError() {
        guard errorStore.hasLastError() else {
            hasLastError = false
            statusMessage = "No last error recorded"
            return
        }

        if errorStore.openLastError() {
            statusMessage = "Opened last error"
        } else {
            statusMessage = "Could not open last error"
        }
    }

    func copyLastError() {
        guard let details = errorStore.readLastError() else {
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

    @discardableResult
    private func recordFailure(command: AgentCommand, result: CommandResult) -> String {
        recordFailure(title: command.title, result: result)
    }

    @discardableResult
    private func recordFailure(title: String, result: CommandResult) -> String {
        let details = errorStore.recordFailure(title: title, result: result)
        hasLastError = errorStore.hasLastError()
        if !hasLastError {
            lastOutput = details
        }
        return details
    }

    nonisolated private static func statusMessage(for command: AgentCommand, result: CommandResult) -> String {
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

    nonisolated private static let voiceServiceLogPath = "~/Library/Logs/agent-cli-whisper/"

    nonisolated private static func voiceServiceStatusMessage(_ output: String) -> String {
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

    nonisolated private static func notificationTitle(for command: AgentCommand, result: CommandResult) -> String {
        if result.exitCode == 0 {
            return command.finishNotificationTitle ?? command.title
        }
        return "\(command.title) Failed"
    }

    nonisolated private static func notificationBody(
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

    nonisolated private static func errorNotificationBody(_ statusMessage: String) -> String {
        "\(statusMessage)\nFull error saved. Open Agent CLI > Open Last Error for details."
    }

    nonisolated private static func summarize(_ output: String) -> String {
        output
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .suffix(4)
            .joined(separator: " ")
    }

    nonisolated private static func compactMenuStatus(_ status: String) -> String {
        let summary = summarize(status)
        guard !summary.isEmpty else {
            return "Ready"
        }
        guard summary.count > menuStatusMaxLength else {
            return summary
        }
        return "Last output available"
    }

}
