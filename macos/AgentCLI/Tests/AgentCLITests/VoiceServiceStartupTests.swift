#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

final class VoiceServiceStartupTests: XCTestCase {
    func testTransientWyomingListenerDoesNotHideHTTPBindFailure() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let log = root.appendingPathComponent("stderr.log")
        let suite = "AgentCLITests.transient-port.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
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
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        defer { defaults.removePersistentDomain(forName: suite) }
        var requestedTimeoutDiagnostics = false
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": root.path, "SHELL": "/no/such/shell"],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                if arguments.contains("ensure") {
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
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
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
        XCTAssertEqual(runtime.ensureReady(for: .transcription).exitCode, 0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: runtime.whisperDaemonMarkerURL.path))
    }
}
#endif
