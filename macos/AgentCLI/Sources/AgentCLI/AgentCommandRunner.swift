import AppKit
import Foundation
import SwiftUI
import UserNotifications

private enum HoldTranscriptionState {
    case idle
    case recording
    case stopping

    var isFinishing: Bool {
        switch self {
        case .stopping:
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
    @Published private(set) var bootstrapPhase: BootstrapPhase = .idle
    @Published private var activeCommandCount = 0
    private var recordingIndicator = RecordingIndicatorController()
    private let pasteController: TranscriptPasteController
    private let bootstrap: AgentBootstrap
    private var activityTracker = MenuActivityTracker()
    private var pendingStopRecordingCommands: Set<String> = []
    private var holdTranscriptionState: HoldTranscriptionState = .idle
    private var holdToTranscribePasteTarget: FocusedTextTarget?
    private var pasteAfterRecordingCommands: Set<String> = []
    private var hasStartedTranscriptionWarmUp = false

    var isRunning: Bool {
        activeCommandCount > 0
    }

    var menuStatusMessage: String {
        menuActivityStatus.message
    }

    var menuActivityStatus: MenuActivityStatus {
        menuActivityStatus(now: Date())
    }

    func menuActivityStatus(now: Date) -> MenuActivityStatus {
        if hasLastError && statusMessage.localizedCaseInsensitiveContains("failed") {
            return activityTracker.status(
                now: now,
                fallback: MenuActivityStatus.inactive(message: "Last command failed")
            )
        }
        return activityTracker.status(
            now: now,
            fallback: MenuActivityStatus.completed(title: Self.compactMenuStatus(statusMessage))
        )
    }

    var menuBarIconState: MenuBarIconState {
        if isRecording {
            return .recording
        }
        if bootstrapPhase.isPreparing {
            return .preparing
        }
        return .idle
    }

    init(
        pasteController: TranscriptPasteController = TranscriptPasteController(),
        bootstrap: @escaping AgentBootstrap = { requirement, force, progress in
            AgentRuntime.shared.ensureReady(for: requirement, force: force, progress: progress)
        }
    ) {
        self.pasteController = pasteController
        self.bootstrap = bootstrap
        hasLastError = FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path)
    }

    nonisolated private static let menuStatusMaxLength = 72
    private static let notificationSettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!
    ]
    func warmUpTranscription() {
        guard !hasStartedTranscriptionWarmUp else { return }
        hasStartedTranscriptionWarmUp = true

        activeCommandCount += 1
        reportBootstrapPhase(.checkingRuntime)

        let bootstrap = self.bootstrap
        let reportBootstrapPhase = makeBootstrapProgressReporter()
        DispatchQueue.global(qos: .utility).async {
            let result = bootstrap(.transcriptionModel, false, reportBootstrapPhase)

            Task { @MainActor in
                self.activeCommandCount = max(0, self.activeCommandCount - 1)
                if !result.output.isEmpty {
                    self.lastOutput = result.output
                }

                if result.exitCode == 0 {
                    self.reportBootstrapPhase(.idle)
                    return
                }

                self.reportBootstrapPhase(.failed)
                self.recordFailure(title: "Startup Voice Service Warm-Up", result: result)
                self.statusMessage = result.output.isEmpty
                    ? "Voice service warm-up failed with exit code \(result.exitCode)"
                    : "Voice service warm-up failed: \(Self.summarize(result.output))"
            }
        }
    }

    private func reportBootstrapPhase(_ phase: BootstrapPhase) {
        let wasPreparing = bootstrapPhase.isPreparing
        let phaseChanged = bootstrapPhase != phase
        bootstrapPhase = phase
        if phase.isPreparing {
            if !wasPreparing || phaseChanged {
                activityTracker.beginBootstrap(title: phase.activityTitle)
            }
        } else {
            activityTracker.finishBootstrap()
        }
    }

    private func makeBootstrapProgressReporter() -> AgentBootstrapProgress {
        { [weak self] phase in
            Task { @MainActor in
                self?.reportBootstrapPhase(phase)
            }
        }
    }

    @discardableResult
    func beginHoldToTranscribe() -> Bool {
        guard holdTranscriptionState == .idle else {
            if holdTranscriptionState.isFinishing {
                statusMessage = "Finishing previous hold-to-transcribe request"
            }
            return false
        }
        guard !recordingIndicator.isRecordingCommand(.toggleTranscription), !isStopPending(for: .toggleTranscription) else {
            statusMessage = "Transcription is already recording"
            return false
        }

        holdTranscriptionState = .recording
        holdToTranscribePasteTarget = FocusedTextTarget.capture()
        pasteAfterRecordingCommands.insert(AgentCommand.toggleTranscription.identifier)
        run(.toggleTranscription)
        return true
    }

    func endHoldToTranscribe() {
        guard holdTranscriptionState == .recording else { return }
        holdTranscriptionState = .stopping

        let wasRecording = recordingIndicator.isRecordingCommand(.toggleTranscription)
        beginTranscribingActivity()
        if wasRecording {
            endRecordingIndicator(for: .toggleTranscription)
            statusMessage = "Transcribing..."
        } else {
            statusMessage = "Stopping transcription as soon as it starts..."
        }
        stopHeldTranscriptionWhenReady()
    }

    @discardableResult
    func stopTranscriptionFromFunctionKeyIfNeeded() -> Bool {
        guard holdTranscriptionState == .idle,
              recordingIndicator.isRecordingCommand(.toggleTranscription),
              !isStopPending(for: .toggleTranscription) else {
            return false
        }

        run(.toggleTranscription)
        return true
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
            beginTranscribingActivity()
        }

        activeCommandCount += 1
        beginCommandActivity(for: command)
        if !self.bootstrapPhase.isPreparing {
            statusMessage = isStopRequest
                ? "Stopping \(command.title)..."
                : "Running \(command.title)..."
        }

        let bootstrap = self.bootstrap
        let reportBootstrapPhase = makeBootstrapProgressReporter()
        let commandArguments = command.resolvedArguments(extraInstructions: TranscriptionSettings.extraInstructions)
        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrapResult = bootstrap(command.bootstrapRequirement, command.forceBootstrap, reportBootstrapPhase)
            guard bootstrapResult.exitCode == 0 else {
                let message = Self.statusMessage(for: command, result: bootstrapResult)
                let notificationTitle = Self.notificationTitle(for: command, result: bootstrapResult)
                let notificationBody = Self.notificationBody(for: command, result: bootstrapResult, statusMessage: message)
                Task { @MainActor in
                    self.reportBootstrapPhase(.failed)
                    if isStopRequest {
                        self.clearStopRequested(for: command)
                    }
                    if shouldStartRecording {
                        self.clearPasteAfterRecording(for: command)
                    }
                    self.clearHoldTranscriptionState(for: command)
                    self.clearTranscribingActivityIfFinished()
                    self.finishCommandActivity(for: command)
                    self.activeCommandCount = max(0, self.activeCommandCount - 1)
                    self.lastOutput = bootstrapResult.output
                    self.recordFailure(command: command, result: bootstrapResult)
                    self.statusMessage = message
                    self.notify(title: notificationTitle, body: notificationBody)
                }
                return
            }

            Task { @MainActor in
                self.reportBootstrapPhase(.idle)
            }

            if shouldStartRecording {
                Task { @MainActor in
                    if self.beginRecordingIndicator(for: command) {
                        self.notifyStart(for: command)
                    }
                }
            }

            let result = AgentRuntime.shared.runAgentCLI(arguments: commandArguments)
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
                    self.clearTranscribingActivityIfFinished()
                }
                self.finishCommandActivity(for: command)
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
                    self.clearTranscribingActivityIfFinished()
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
        guard holdTranscriptionState == .stopping else { return }

        statusMessage = "Stopping Toggle Transcription..."

        let bootstrap = self.bootstrap
        let reportBootstrapPhase = makeBootstrapProgressReporter()
        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrapResult = bootstrap(
                AgentCommand.stopTranscription.bootstrapRequirement,
                AgentCommand.stopTranscription.forceBootstrap,
                reportBootstrapPhase
            )
            guard bootstrapResult.exitCode == 0 else {
                let message = Self.statusMessage(for: AgentCommand.stopTranscription, result: bootstrapResult)
                Task { @MainActor in
                    self.reportBootstrapPhase(.failed)
                    self.holdTranscriptionState = .idle
                    self.clearTranscribingActivityIfFinished()
                    self.lastOutput = bootstrapResult.output
                    self.recordFailure(command: AgentCommand.stopTranscription, result: bootstrapResult)
                    self.statusMessage = message
                    self.notify(
                        title: "Toggle Transcription Failed",
                        body: Self.errorNotificationBody(message)
                    )
                }
                return
            }

            Task { @MainActor in
                self.reportBootstrapPhase(.idle)
            }

            let result = AgentRuntime.shared.runAgentCLI(arguments: AgentCommand.stopTranscription.arguments)

            Task { @MainActor in
                if result.exitCode == 0 {
                    if self.holdTranscriptionState == .stopping {
                        self.statusMessage = "Transcribing..."
                    }
                    return
                }

                self.holdTranscriptionState = .idle
                self.clearTranscribingActivityIfFinished()
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

    private func isStopPending(for command: AgentCommand) -> Bool {
        pendingStopRecordingCommands.contains(command.identifier)
    }

    private func markStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.insert(command.identifier)
    }

    private func clearStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.remove(command.identifier)
    }

    private func beginCommandActivity(for command: AgentCommand) {
        activityTracker.beginCommand(identifier: command.identifier, title: command.menuActivityTitle)
    }

    private func finishCommandActivity(for command: AgentCommand) {
        activityTracker.finishCommand(identifier: command.identifier)
    }

    private func beginTranscribingActivity() {
        activityTracker.beginTranscribing()
    }

    private func clearTranscribingActivityIfFinished() {
        if pendingStopRecordingCommands.isEmpty && !holdTranscriptionState.isFinishing {
            activityTracker.finishTranscribing()
        }
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

    private func beginRecordingIndicator(for command: AgentCommand) -> Bool {
        if command.identifier == AgentCommand.toggleTranscription.identifier,
           holdTranscriptionState == .stopping {
            return false
        }

        let wasRecording = isRecording
        recordingIndicator.begin(for: command)
        isRecording = recordingIndicator.isRecording
        if !wasRecording && isRecording {
            activityTracker.beginRecording()
        }
        return true
    }

    private func endRecordingIndicator(for command: AgentCommand) {
        recordingIndicator.end(for: command)
        isRecording = recordingIndicator.isRecording
        if !isRecording {
            activityTracker.finishRecording()
        }
    }

    func copyLastOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(lastOutput, forType: .string)
        statusMessage = "Copied last output"
    }

    func copyRecentTranscription(_ transcription: RecentTranscription) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(transcription.text, forType: .string)
        statusMessage = "Copied recent transcription"
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
        statusMessage = "Notifications are disabled. Use Fix Notification Permission to enable Agent CLI notifications."
    }

    func repairNotificationPermission() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            switch settings.authorizationStatus {
            case .notDetermined:
                UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { granted, _ in
                    Task { @MainActor in
                        self.statusMessage = granted
                            ? "Notification permission enabled"
                            : "Notifications are disabled. Enable Agent CLI in Notification Settings."
                    }
                }
            case .denied:
                Task { @MainActor in
                    _ = self.openNotificationSettings()
                    self.statusMessage = "Notifications are disabled. Enable Agent CLI in Notification Settings."
                }
            default:
                Task { @MainActor in
                    self.statusMessage = "Notification permission is already enabled"
                }
            }
        }
    }

    @discardableResult
    func openNotificationSettings() -> Bool {
        for url in Self.notificationSettingsURLs where NSWorkspace.shared.open(url) {
            statusMessage = "Opened Notification Settings"
            return true
        }
        statusMessage = "Could not open Notification Settings"
        return false
    }

    func resetAccessibilityPermission() {
        ConfigurableHotkeyController.shared.suspendFunctionAwareHotkeysForAccessibilityReset()
        statusMessage = "Resetting Accessibility permission..."

        DispatchQueue.global(qos: .utility).async {
            let result = self.runTCCReset(service: "Accessibility")

            Task { @MainActor in
                try? FileManager.default.removeItem(at: AgentRuntime.shared.accessibilityPromptMarkerURL)

                guard result.exitCode == 0 else {
                    ConfigurableHotkeyController.shared.resumeFunctionAwareHotkeysAfterAccessibilityReset(runner: self)
                    let output = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.statusMessage = output.isEmpty
                        ? "Could not reset Accessibility permission"
                        : "Could not reset Accessibility permission: \(output)"
                    return
                }

                self.statusMessage = "Accessibility permission reset. Restarting AgentCLI to request permission cleanly."
                self.relaunchAfterAccessibilityReset()
            }
        }
    }

    private func relaunchAfterAccessibilityReset() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = [
            "-c",
            "sleep 1; /usr/bin/open \"$1\"",
            "relaunch-agentcli",
            Bundle.main.bundleURL.path
        ]

        do {
            try process.run()
            NSApp.terminate(nil)
        } catch {
            statusMessage = "Accessibility permission reset. Reopen AgentCLI, then enable it in Accessibility."
        }
    }

    nonisolated private func runTCCReset(service: String) -> CommandResult {
        let bundleIdentifier = Bundle.main.bundleIdentifier ?? "lt.nijho.agent-cli.menubar"
        let process = Process()
        let pipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        process.arguments = ["reset", service, bundleIdentifier]
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""
            return CommandResult(exitCode: process.terminationStatus, output: output)
        } catch {
            return CommandResult(exitCode: 1, output: error.localizedDescription)
        }
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
