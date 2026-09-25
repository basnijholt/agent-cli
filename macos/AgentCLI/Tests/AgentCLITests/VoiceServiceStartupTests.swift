#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

final class VoiceServiceStartupTests: XCTestCase {
    func testUserInstalledVoiceBootstrapOnlyChecksCLIAvailability() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let suite = "AgentCLITests.user-voice-bootstrap.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        defer { defaults.removePersistentDomain(forName: suite) }
        var commands: [[String]] = []
        var phases: [BootstrapPhase] = []
        var connectionChecks = 0
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                commands.append(arguments)
                return CommandResult(exitCode: 0, output: "")
            },
            localhostConnector: { _ in connectionChecks += 1; return true },
            whisperReadyTimeout: 0.01
        )

        // Startup and recording request model readiness; stopping only requests transcription.
        for requirement: AgentBootstrapRequirement in [.transcriptionModel, .transcription] {
            for force in [false, true] {
                XCTAssertEqual(runtime.ensureReady(for: requirement, force: force) { phases.append($0) }.exitCode, 0)
            }
        }

        XCTAssertEqual(commands, Array(repeating: ["agent-cli", "--version"], count: 3))
        XCTAssertEqual(phases, Array(repeating: .checkingRuntime, count: 3))
        XCTAssertEqual(connectionChecks, 0, "An external CLI may use a remote or cloud provider.")
        XCTAssertFalse(FileManager.default.fileExists(atPath: runtime.whisperDaemonMarkerURL.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: runtime.whisperWarmUpAudioURL.path))
    }

    func testUserInstalledVoiceBootstrapStillReportsMissingCLIAndRetries() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let suite = "AgentCLITests.missing-user-cli.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        defer { defaults.removePersistentDomain(forName: suite) }
        var commands: [[String]] = []
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                commands.append(arguments)
                return CommandResult(exitCode: 127, output: "")
            },
            localhostConnector: { _ in XCTFail("Must not contact a local voice service."); return false }
        )

        for requirement: AgentBootstrapRequirement in [.transcriptionModel, .transcription] {
            let result = runtime.ensureReady(for: requirement)
            XCTAssertEqual(result.exitCode, 127)
            XCTAssertTrue(result.output.contains("not found on PATH"))
        }
        XCTAssertEqual(commands, Array(repeating: ["agent-cli", "--version"], count: 2))
    }

    func testModelWarmUpRetriesFailuresCachesSuccessAndResetsAfterServiceInstall() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let suite = "AgentCLITests.model-ready.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var warmUpCount = 0
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                if arguments.contains("--from-file") {
                    warmUpCount += 1
                    if warmUpCount == 1 { return CommandResult(exitCode: 1, output: "Download failed") }
                }
                return CommandResult(exitCode: 0, output: "")
            },
            localhostConnector: { _ in true },
            whisperReadyTimeout: 0.01,
            voiceServiceLogURL: root.appendingPathComponent("stderr.log")
        )
        try prepareBundledCLI(runtime)
        XCTAssertNotEqual(runtime.ensureReady(for: .transcriptionModel).exitCode, 0)
        XCTAssertEqual(runtime.ensureReady(for: .transcriptionModel).exitCode, 0)
        XCTAssertEqual(warmUpCount, 2, "Failed model setup must be retried.")
        XCTAssertEqual(runtime.ensureReady(for: .transcriptionModel).exitCode, 0)
        XCTAssertEqual(warmUpCount, 2, "Normal recording must not repeatedly transcribe warm-up audio.")
        XCTAssertEqual(runtime.runAgentCLI(arguments: ["daemon", "install", "whisper", "-y"]).exitCode, 0)
        XCTAssertEqual(runtime.ensureReady(for: .transcriptionModel).exitCode, 0)
        XCTAssertEqual(warmUpCount, 3, "Replacing the service invalidates model readiness.")
    }

    func testTransientWyomingListenerDoesNotHideHTTPBindFailure() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let log = root.appendingPathComponent("stderr.log")
        let suite = "AgentCLITests.transient-port.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var connectionChecks = 0
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, _, _ in CommandResult(exitCode: 0, output: "") },
            localhostConnector: { _ in
                connectionChecks += 1
                if connectionChecks == 1 {
                    // Wyoming starts during ASGI lifespan, before the HTTP bind fails.
                    try! "[Errno 48] HTTP 10301: address already in use\n"
                        .write(to: log, atomically: true, encoding: .utf8)
                    return true
                }
                return false
            },
            whisperReadyTimeout: 0.01,
            voiceServiceLogURL: log
        )
        try prepareBundledCLI(runtime)
        let result = runtime.ensureReady(for: .transcription)
        XCTAssertNotEqual(result.exitCode, 0)
        XCTAssertTrue(result.output.contains("address already in use"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: runtime.whisperDaemonMarkerURL.path))
    }

    func testNewPortConflictFailsWithoutWaitingForTimeoutOrSavingReadyMarker() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let log = root.appendingPathComponent("stderr.log")
        let suite = "AgentCLITests.port-conflict.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var requestedTimeoutDiagnostics = false
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                if arguments.starts(with: ["daemon", "install", "whisper"]) {
                    try! "[Errno 48] error while attempting to bind on address ('0.0.0.0', 10301): address already in use\n"
                        .write(to: log, atomically: true, encoding: .utf8)
                }
                if arguments.contains("status") { requestedTimeoutDiagnostics = true }
                return CommandResult(exitCode: 0, output: "")
            },
            localhostConnector: { _ in false },
            whisperReadyTimeout: 0.01,
            voiceServiceLogURL: log
        )
        try prepareBundledCLI(runtime)
        let result = runtime.ensureReady(for: .transcription)
        XCTAssertNotEqual(result.exitCode, 0)
        XCTAssertTrue(result.output.contains("address already in use"))
        XCTAssertFalse(requestedTimeoutDiagnostics, "A definitive startup failure should not wait for the readiness timeout.")
        XCTAssertFalse(FileManager.default.fileExists(atPath: runtime.whisperDaemonMarkerURL.path),
                       "A launched process is not yet a ready service.")
    }

    func testOldPortConflictDoesNotRejectSuccessfulRetry() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let log = root.appendingPathComponent("stderr.log")
        try "[Errno 48] address already in use\n".write(to: log, atomically: true, encoding: .utf8)
        let suite = "AgentCLITests.old-port-conflict.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var checks = 0
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, _, _ in CommandResult(exitCode: 0, output: "") },
            localhostConnector: { _ in checks += 1; return checks > 1 },
            whisperReadyTimeout: 2,
            voiceServiceLogURL: log
        )
        try prepareBundledCLI(runtime)
        XCTAssertEqual(runtime.ensureReady(for: .transcription).exitCode, 0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: runtime.whisperDaemonMarkerURL.path))
    }

    private func prepareBundledCLI(_ runtime: AgentRuntime) throws {
        try FileManager.default.createDirectory(at: runtime.binURL, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: runtime.agentCLIURL.path, contents: Data())
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: runtime.agentCLIURL.path)
        try "packageSource=agent-cli\ninstallRequirement=agent-cli[audio,llm]\n".write(
            to: runtime.agentCLIInstallMarkerURL,
            atomically: true,
            encoding: .utf8
        )
    }
}
#endif
