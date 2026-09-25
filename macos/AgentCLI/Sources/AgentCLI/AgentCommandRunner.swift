import AppKit
import Foundation
import SwiftUI
import UserNotifications

private enum HoldTranscriptionState {
    case idle
    case preparing
    case recording
    case stopping

    var isFinishing: Bool {
        switch self {
        case .stopping:
            return true
        case .idle, .preparing, .recording:
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
    @Published private(set) var isResettingAccessibility = false
    @Published private(set) var bootstrapPhase: BootstrapPhase = .idle
    @Published private var activeCommandCount = 0
    private var recordingIndicator = RecordingIndicatorController()
    private let pasteController: TranscriptPasteController
    private let bootstrap: AgentBootstrap
    private let recordingPermissionCheck: @MainActor () -> Bool
    private let showPermissionSettings: @MainActor () -> Void
    private let sendNotification: (UNNotificationRequest) -> Void
    private let runCommand: ([String]) -> CommandResult
    private var activityTracker = MenuActivityTracker()
    private var pendingStopRecordingCommands: Set<String> = []
    private var holdTranscriptionState: HoldTranscriptionState = .idle
    private var holdToTranscribePasteTarget: FocusedTextTarget?
    private var pasteAfterRecordingCommands: Set<String> = []
    private var hasStartedTranscriptionWarmUp = false
    private var pendingRecordingStarts: [String: UUID] = [:]
    private var bootstrapRequests: [UUID: BootstrapPhase] = [:]
    private var bootstrapRequestOrder: [UUID] = []

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
        MenuBarIconState.current(isPreparing: bootstrapPhase.isPreparing, isRecording: isRecording)
    }

    init(
        pasteController: TranscriptPasteController = TranscriptPasteController(),
        bootstrap: @escaping AgentBootstrap = { requirement, force, progress in
            AgentRuntime.shared.ensureReady(for: requirement, force: force, progress: progress)
        },
        recordingPermissionCheck: @escaping @MainActor () -> Bool = { PermissionController.shared.canRecord },
        showPermissionSettings: @escaping @MainActor () -> Void = { SettingsWindowController.shared.show(.permissions) },
        sendNotification: @escaping (UNNotificationRequest) -> Void = { UNUserNotificationCenter.current().add($0) },
        runCommand: @escaping ([String]) -> CommandResult = { AgentRuntime.shared.runAgentCLI(arguments: $0) }
    ) {
        self.pasteController = pasteController
        self.bootstrap = bootstrap
        self.recordingPermissionCheck = recordingPermissionCheck
        self.showPermissionSettings = showPermissionSettings
        self.sendNotification = sendNotification
        self.runCommand = runCommand
        hasLastError = FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path)
    }

    nonisolated private static let menuStatusMaxLength = 72
    func warmUpTranscription() {
        guard !hasStartedTranscriptionWarmUp else { return }
        hasStartedTranscriptionWarmUp = true

        activeCommandCount += 1
        let bootstrapRequestID = beginBootstrap(initialPhase: .checkingRuntime)

        let bootstrap = self.bootstrap
        let reportBootstrapPhase = makeBootstrapProgressReporter(for: bootstrapRequestID)
        DispatchQueue.global(qos: .utility).async {
            let result = bootstrap(.transcriptionModel, false, reportBootstrapPhase)

            Task { @MainActor in
                self.activeCommandCount = max(0, self.activeCommandCount - 1)
                if !result.output.isEmpty {
                    self.lastOutput = result.output
                }

                if result.exitCode == 0 {
                    self.finishBootstrap(bootstrapRequestID)
                    return
                }

                self.finishBootstrap(bootstrapRequestID, failed: true)
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
        VoiceLevelOverlayController.shared.updatePreparation(phase)
        if phase.isPreparing {
            statusMessage = phase.statusMessage
            if !wasPreparing || phaseChanged {
                activityTracker.beginBootstrap(title: phase.activityTitle)
            }
        } else {
            activityTracker.finishBootstrap()
            if phase == .idle, !isRunning, !isRecording {
                statusMessage = "Ready to record"
            }
        }
    }

    private func beginBootstrap(initialPhase: BootstrapPhase = .idle) -> UUID {
        let id = UUID()
        bootstrapRequests[id] = initialPhase
        bootstrapRequestOrder.append(id)
        if initialPhase.isPreparing { reportBootstrapPhase(initialPhase) }
        return id
    }

    private func finishBootstrap(_ id: UUID, failed: Bool = false) {
        bootstrapRequests.removeValue(forKey: id)
        bootstrapRequestOrder.removeAll { $0 == id }
        // Another command may already be setting up. Only finish this request.
        let currentPhase = bootstrapRequestOrder.reversed()
            .compactMap { bootstrapRequests[$0] }.first { $0.isPreparing }
        reportBootstrapPhase(currentPhase ?? (failed ? .failed : .idle))
    }

    private func makeBootstrapProgressReporter(for id: UUID) -> AgentBootstrapProgress {
        { [weak self] phase in
            DispatchQueue.main.async {
                guard let self, self.bootstrapRequests[id] != nil else { return }
                self.bootstrapRequests[id] = phase
                self.bootstrapRequestOrder.removeAll { $0 == id }
                self.bootstrapRequestOrder.append(id)
                self.reportBootstrapPhase(phase)
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
        guard run(.toggleTranscription) else { return false }
        holdTranscriptionState = .preparing
        holdToTranscribePasteTarget = FocusedTextTarget.capture()
        pasteAfterRecordingCommands.insert(AgentCommand.toggleTranscription.identifier)
        return true
    }

    func endHoldToTranscribe() {
        if holdTranscriptionState == .preparing {
            pendingRecordingStarts.removeValue(forKey: AgentCommand.toggleTranscription.identifier)
            holdTranscriptionState = .idle
            clearPasteAfterRecording(for: .toggleTranscription)
            statusMessage = "Recording canceled. Voice setup will finish in the background; hold the shortcut again when ready."
            return
        }
        guard holdTranscriptionState == .recording else { return }
        holdTranscriptionState = .stopping

        let wasRecording = recordingIndicator.isRecordingCommand(.toggleTranscription)
        if wasRecording {
            endRecordingIndicator(for: .toggleTranscription)
            statusMessage = "Transcribing..."
        } else {
            statusMessage = "Stopping transcription as soon as it starts..."
        }
        beginTranscribingActivity()
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

    @discardableResult
    func run(_ command: AgentCommand) -> Bool {
        guard !isResettingAccessibility else {
            statusMessage = "Accessibility reset is in progress. Wait for Agent CLI to restart."
            return false
        }
        let isStopRequest = command.showsRecordingIndicator && recordingIndicator.isRecordingCommand(command)
        let shouldStartRecording = command.showsRecordingIndicator && !isStopRequest
        guard !shouldStartRecording || ensureMicrophonePermission() else { return false }
        if shouldStartRecording && bootstrapPhase.isPreparing {
            VoiceLevelOverlayController.shared.showPreparation(bootstrapPhase)
            statusMessage = "Voice setup is still in progress. Try recording again when ready."
            return false
        }

        if isStopRequest && isStopPending(for: command) {
            statusMessage = "Stop already requested for \(command.title)"
            return false
        }

        let bootstrapRequestID = beginBootstrap(initialPhase: shouldStartRecording ? .checkingRuntime : .idle)
        let recordingRequestID = shouldStartRecording ? UUID() : nil
        if let recordingRequestID {
            pendingRecordingStarts[command.identifier] = recordingRequestID
            VoiceLevelOverlayController.shared.showPreparation(.checkingRuntime)
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
        let reportBootstrapPhase = makeBootstrapProgressReporter(for: bootstrapRequestID)
        let transcriptionDaemonArguments = AgentRuntime.shared.usesUserInstalledAgentCLI
            ? nil
            : TranscriptionSettings.whisperDaemonInstallArguments()
        let commandArguments = command.resolvedArguments(
            extraInstructions: TranscriptionSettings.extraInstructions,
            transcriptionDaemonArguments: transcriptionDaemonArguments
        )
        let runCommand = self.runCommand
        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrapResult = bootstrap(command.bootstrapRequirement, command.forceBootstrap, reportBootstrapPhase)
            guard bootstrapResult.exitCode == 0 else {
                let message = Self.statusMessage(for: command, result: bootstrapResult)
                let notificationTitle = Self.notificationTitle(for: command, result: bootstrapResult)
                let notificationBody = Self.notificationBody(for: command, result: bootstrapResult, statusMessage: message)
                Task { @MainActor in
                    self.finishBootstrap(bootstrapRequestID, failed: true)
                    if isStopRequest {
                        self.clearStopRequested(for: command)
                    }
                    if shouldStartRecording {
                        self.pendingRecordingStarts.removeValue(forKey: command.identifier)
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

            // Commit the start on the main queue, where key release can cancel it.
            // A queued main-actor Task here would let the CLI start before that decision.
            let shouldRun = DispatchQueue.main.sync {
                self.finishBootstrap(bootstrapRequestID)
                if let recordingRequestID {
                    guard self.pendingRecordingStarts[command.identifier] == recordingRequestID else {
                        self.finishCommandActivity(for: command)
                        self.activeCommandCount = max(0, self.activeCommandCount - 1)
                        if !self.isRunning, !self.isRecording, self.bootstrapPhase == .idle {
                            self.statusMessage = "Ready to record"
                        }
                        return false
                    }
                    self.pendingRecordingStarts.removeValue(forKey: command.identifier)
                    if self.beginRecordingIndicator(for: command) {
                        self.notifyStart(for: command)
                    }
                }
                if !self.bootstrapPhase.isPreparing {
                    self.statusMessage = isStopRequest
                        ? "Stopping \(command.title)..."
                        : "Running \(command.title)..."
                }
                return true
            }
            guard shouldRun else { return }

            let commandResult = runCommand(commandArguments)
            // A stop acknowledgement may be empty; a completed recording must contain text.
            // Validate here too because user-installed CLIs can predate the CLI-side check.
            let result = shouldStartRecording && command.identifier == AgentCommand.toggleTranscription.identifier
                ? commandResult.requiringTranscript()
                : commandResult
            let message = Self.statusMessage(for: command, result: result)
            let notificationTitle = Self.notificationTitle(for: command, result: result)
            let notificationBody = Self.notificationBody(for: command, result: result, statusMessage: message)

            Task { @MainActor in
                if shouldStartRecording {
                    self.clearHoldTranscriptionState(for: command)
                    let shouldPaste = self.shouldPasteAfterRecording(for: command)
                    let pasteTarget = self.holdToTranscribePasteTarget
                    self.endRecordingIndicator(for: command)
                    self.clearStopRequested(for: command)
                    if shouldPaste, let pasteText = result.pasteText {
                        self.pasteController.pasteTranscriptIntoFocusedField(pasteText, target: pasteTarget) { message in
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
        return true
    }

    private func notifyStart(for command: AgentCommand) {
        guard let title = command.startNotificationTitle else { return }
        notify(title: title, body: command.startNotificationBody ?? "")
    }

    private func stopHeldTranscriptionWhenReady() {
        guard holdTranscriptionState == .stopping else { return }

        statusMessage = "Stopping Toggle Transcription..."

        let bootstrap = self.bootstrap
        let runCommand = self.runCommand
        let bootstrapRequestID = beginBootstrap()
        let reportBootstrapPhase = makeBootstrapProgressReporter(for: bootstrapRequestID)
        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrapResult = bootstrap(
                AgentCommand.stopTranscription.bootstrapRequirement,
                AgentCommand.stopTranscription.forceBootstrap,
                reportBootstrapPhase
            )
            guard bootstrapResult.exitCode == 0 else {
                let message = Self.statusMessage(for: AgentCommand.stopTranscription, result: bootstrapResult)
                Task { @MainActor in
                    self.finishBootstrap(bootstrapRequestID, failed: true)
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
                self.finishBootstrap(bootstrapRequestID)
            }

            let result = runCommand(AgentCommand.stopTranscription.arguments)

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
        VoiceLevelOverlayController.shared.showTranscribing()
    }

    private func clearTranscribingActivityIfFinished() {
        if pendingStopRecordingCommands.isEmpty && !holdTranscriptionState.isFinishing {
            activityTracker.finishTranscribing()
            VoiceLevelOverlayController.shared.finishTranscribing()
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

        if command.identifier == AgentCommand.toggleTranscription.identifier,
           holdTranscriptionState == .preparing {
            holdTranscriptionState = .recording
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

    func openTranscriptionLog() {
        let url = RecentTranscriptionReader.defaultLogURL

        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            if !FileManager.default.fileExists(atPath: url.path) {
                _ = FileManager.default.createFile(atPath: url.path, contents: nil)
            }
            NSWorkspace.shared.activateFileViewerSelecting([url])
            statusMessage = "Opened transcription log"
        } catch {
            statusMessage = "Could not open transcription log: \(error.localizedDescription)"
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

    private func ensureMicrophonePermission() -> Bool {
        guard recordingPermissionCheck() else {
            statusMessage = "Microphone access is needed. Open Permissions to enable recording."
            showPermissionSettings()
            return false
        }
        return true
    }

    func resetAccessibilityPermission() {
        guard !isRunning, !isRecording, !isResettingAccessibility else {
            statusMessage = "Finish the current command before resetting Accessibility."
            return
        }
        let alert = NSAlert()
        alert.messageText = "Reset Accessibility access?"
        alert.informativeText = "This removes Agent CLI's existing Accessibility permission and restarts the app. You will need to enable Agent CLI again in System Settings. Use this only if reopening the app did not help."
        alert.addButton(withTitle: "Cancel")
        alert.addButton(withTitle: "Reset and Restart")
        guard alert.runModal() == .alertSecondButtonReturn else { return }
        // The modal alert runs the main loop, so a hotkey may have started work meanwhile.
        guard !isRunning, !isRecording, !isResettingAccessibility else {
            statusMessage = "Finish the current command before resetting Accessibility."
            return
        }
        isResettingAccessibility = true
        ConfigurableHotkeyController.shared.suspendFunctionAwareHotkeysForAccessibilityReset()
        statusMessage = "Resetting Accessibility permission..."

        DispatchQueue.global(qos: .utility).async {
            let result = self.runTCCReset(service: "Accessibility")

            Task { @MainActor in
                try? FileManager.default.removeItem(at: AgentRuntime.shared.accessibilityPromptMarkerURL)

                guard result.exitCode == 0 else {
                    self.isResettingAccessibility = false
                    ConfigurableHotkeyController.shared.resumeFunctionAwareHotkeysAfterAccessibilityReset(runner: self)
                    let output = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.statusMessage = output.isEmpty
                        ? "Could not reset Accessibility permission"
                        : "Could not reset Accessibility permission: \(output)"
                    return
                }

                self.statusMessage = "Accessibility permission reset. Restarting AgentCLI to reopen setup."
                UserDefaults.standard.set(true, forKey: PermissionController.showOnNextLaunchKey)
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
            isResettingAccessibility = false
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
        sendNotification(request)
    }
}
