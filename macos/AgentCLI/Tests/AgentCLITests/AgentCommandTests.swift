#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class AgentCommandTests: XCTestCase {
    func testToggleTranscriptionUsesTypedArgumentsAndTranscriptionBootstrap() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.arguments,
            [
                "transcribe",
                "--toggle",
                "--quiet",
                "--transcription-log",
                "~/.config/agent-cli/transcriptions.jsonl",
            ]
        )
        XCTAssertEqual(AgentCommand.toggleTranscription.bootstrapRequirement, .transcription)
    }

    func testToggleTranscriptionAppendsConfiguredExtraInstructions() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(
                extraInstructions: "  Remember Bas and Henk.\nPrefer project names.  "
            ),
            [
                "transcribe",
                "--toggle",
                "--quiet",
                "--transcription-log",
                "~/.config/agent-cli/transcriptions.jsonl",
                "--extra-instructions",
                "Remember Bas and Henk.\nPrefer project names.",
            ]
        )
    }

    func testBlankExtraInstructionsAreIgnored() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(extraInstructions: "  \n\t  "),
            AgentCommand.toggleTranscription.arguments
        )
    }

    func testVisuallyBlankExtraInstructionsAreIgnored() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(extraInstructions: "\u{2060}\u{FEFF}"),
            AgentCommand.toggleTranscription.arguments
        )
    }

    func testExtraInstructionsOnlyApplyToTranscription() {
        XCTAssertEqual(
            AgentCommand.autocorrect.resolvedArguments(extraInstructions: "Remember Bas."),
            AgentCommand.autocorrect.arguments
        )
    }

    func testAutocorrectOnlyRequiresCliRuntime() {
        XCTAssertEqual(AgentCommand.autocorrect.arguments, ["autocorrect", "--quiet"])
        XCTAssertEqual(AgentCommand.autocorrect.bootstrapRequirement, .cliRuntime)
    }

    func testRuntimeUsesBundledCLIByDefault() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.default-runtime")!
        defaults.removePersistentDomain(forName: "AgentCLITests.default-runtime")
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": "/tmp/agentcli-test-support"],
            userDefaults: defaults
        )

        XCTAssertFalse(runtime.usesUserInstalledAgentCLI)
        XCTAssertEqual(runtime.agentCLIExecutableURL.path, "/tmp/agentcli-test-support/bin/agent-cli")
        XCTAssertEqual(runtime.agentCLIProcessArguments(["--version"]), ["--version"])
        XCTAssertEqual(runtime.commandEnvironment()["AGENT_CLI_CONFIG_HOME"], "/tmp/agentcli-test-support/config")
        XCTAssertEqual(runtime.commandEnvironment()["UV_TOOL_BIN_DIR"], "/tmp/agentcli-test-support/bin")
    }

    func testRuntimeCanUseUserInstalledCLIWithoutPrivateConfig() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.user-runtime")!
        defaults.removePersistentDomain(forName: "AgentCLITests.user-runtime")
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        let runtime = AgentRuntime(
            environment: [
                "AGENTCLI_APP_SUPPORT_DIR": "/tmp/agentcli-test-support",
                "AGENTCLI_RUNTIME_DIR": "/tmp/agentcli-test-support/runtime",
                "AGENTCLI_BUNDLED_UV": "/tmp/agentcli-test-support/bin/uv",
                "AGENTCLI_PACKAGE_SOURCE": "agent-cli",
                "AGENTCLI_AGENT_CLI": "/tmp/agentcli-test-support/bin/agent-cli",
                "AGENT_CLI_CONFIG_HOME": "/tmp/agentcli-test-support/config",
                "AGENTCLI_UV_PATH": "/custom/uv",
                "UV_TOOL_BIN_DIR": "/tmp/agentcli-test-support/bin",
                "PATH": "/custom/bin",
                "SHELL": "/no/such/shell",
            ],
            userDefaults: defaults
        )

        XCTAssertTrue(runtime.usesUserInstalledAgentCLI)
        XCTAssertEqual(runtime.agentCLIExecutableURL.path, "/usr/bin/env")
        XCTAssertEqual(runtime.agentCLIProcessArguments(["--version"]), ["agent-cli", "--version"])
        XCTAssertNil(runtime.commandEnvironment()["AGENTCLI_APP_SUPPORT_DIR"])
        XCTAssertNil(runtime.commandEnvironment()["AGENTCLI_RUNTIME_DIR"])
        XCTAssertNil(runtime.commandEnvironment()["AGENTCLI_BUNDLED_UV"])
        XCTAssertNil(runtime.commandEnvironment()["AGENTCLI_PACKAGE_SOURCE"])
        XCTAssertNil(runtime.commandEnvironment()["AGENT_CLI_CONFIG_HOME"])
        XCTAssertNil(runtime.commandEnvironment()["UV_TOOL_BIN_DIR"])
        XCTAssertEqual(runtime.commandEnvironment()["AGENTCLI_UV_PATH"], "/custom/uv")
        XCTAssertTrue(runtime.commandEnvironment()["PATH"]?.contains("/custom/bin") == true)
    }

    func testUserInstalledCLIPathUsesLoginShellPathAndCommonUvBins() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.user-runtime-path")!
        defaults.removePersistentDomain(forName: "AgentCLITests.user-runtime-path")
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        let runtime = AgentRuntime(
            environment: [
                "AGENTCLI_APP_SUPPORT_DIR": "/tmp/agentcli-test-support",
                "PATH": "/usr/bin:/bin",
                "SHELL": "/no/such/shell",
            ],
            userDefaults: defaults
        )

        let shellPath = "/Users/example/.dotbins/macos/arm64/bin:/usr/bin"
        let path = runtime.userInstalledCLIPath(
            existingPATH: "/usr/bin:/bin",
            loginShellPATH: shellPath
        )
        let components = path.split(separator: ":").map(String.init)
        let home = FileManager.default.homeDirectoryForCurrentUser.path

        XCTAssertEqual(components.first, "/Users/example/.dotbins/macos/arm64/bin")
        XCTAssertTrue(components.contains("\(home)/.local/bin"))
        XCTAssertTrue(components.contains("\(home)/.cargo/bin"))
        XCTAssertEqual(components.filter { $0 == "/usr/bin" }.count, 1)
    }

    func testTranscriptionBootstrapRepairsStaleWhisperDaemonMarker() throws {
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("AgentCLITests-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tempURL) }

        let binURL = tempURL.appendingPathComponent("bin", isDirectory: true)
        try FileManager.default.createDirectory(at: binURL, withIntermediateDirectories: true)
        let agentCLIURL = binURL.appendingPathComponent("agent-cli")
        _ = FileManager.default.createFile(atPath: agentCLIURL.path, contents: Data())
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: agentCLIURL.path)

        try """
        packageSource=agent-cli
        installRequirement=agent-cli[audio,llm]

        """.write(
            to: tempURL.appendingPathComponent(".agent-cli-installed"),
            atomically: true,
            encoding: .utf8
        )
        try """
        runtimeMode=bundled
        packageSource=agent-cli

        """.write(
            to: tempURL.appendingPathComponent(".whisper-daemon-installed"),
            atomically: true,
            encoding: .utf8
        )

        let defaults = UserDefaults(suiteName: "AgentCLITests.stale-whisper-marker")!
        defaults.removePersistentDomain(forName: "AgentCLITests.stale-whisper-marker")
        var installedWhisper = false
        var processArguments: [[String]] = []
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": tempURL.path],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                processArguments.append(arguments)
                if arguments == ["daemon", "ensure", "whisper", "--quiet"] {
                    installedWhisper = true
                    return CommandResult(exitCode: 0, output: "Installed and started")
                }
                XCTFail("Unexpected process arguments: \(arguments)")
                return CommandResult(exitCode: 1, output: "unexpected")
            },
            localhostConnector: { port in
                XCTAssertEqual(port, 10300)
                return installedWhisper
            },
            whisperReadyTimeout: 0.01
        )

        var phases: [BootstrapPhase] = []
        let result = runtime.ensureReady(for: .transcription) { phases.append($0) }

        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(
            processArguments,
            [
                ["daemon", "ensure", "whisper", "--quiet"],
            ]
        )
        XCTAssertEqual(phases, [.waitingForVoiceService, .installingVoiceService, .waitingForVoiceService])
    }

    @MainActor
    func testStartupWarmUpBootstrapsTranscriptionOnce() {
        let recorder = BootstrapRecorder()
        let runner = AgentCommandRunner(bootstrap: recorder.bootstrap)

        runner.warmUpTranscription()
        runner.warmUpTranscription()

        wait(for: [recorder.expectation], timeout: 2)

        XCTAssertEqual(recorder.calls, [.init(requirement: .transcriptionModel, force: false)])
    }

    func testPreparingStatusShowsFixedWidthSpinnerAndElapsedTime() {
        XCTAssertEqual(
            BootstrapPhase.checkingRuntime.statusMessage(animationTick: 0, elapsedSeconds: 0),
            "Checking CLI runtime ◐ (00:00)"
        )
        XCTAssertEqual(
            BootstrapPhase.installingRuntime.statusMessage(animationTick: 1, elapsedSeconds: 12),
            "Installing CLI runtime ◓ (00:12)"
        )
        XCTAssertEqual(
            BootstrapPhase.installingVoiceService.statusMessage(animationTick: 2, elapsedSeconds: 123),
            "Installing voice service ◑ (02:03)"
        )
        XCTAssertEqual(
            BootstrapPhase.waitingForVoiceService.statusMessage(animationTick: 0, elapsedSeconds: 0),
            "Waiting for voice service ◐ (00:00)"
        )
        XCTAssertEqual(
            BootstrapPhase.waitingForVoiceService.statusMessage(animationTick: 1, elapsedSeconds: 12),
            "Waiting for voice service ◓ (00:12)"
        )
        XCTAssertEqual(
            BootstrapPhase.waitingForVoiceService.statusMessage(animationTick: 2, elapsedSeconds: 123),
            "Waiting for voice service ◑ (02:03)"
        )
        XCTAssertEqual(
            BootstrapPhase.warmingWhisperModel.statusMessage(animationTick: 3, elapsedSeconds: 4),
            "Warming Whisper model ◒ (00:04)"
        )
    }

}

private struct BootstrapCall: Equatable {
    let requirement: AgentBootstrapRequirement
    let force: Bool
}

private final class BootstrapRecorder {
    let expectation = XCTestExpectation(description: "warm-up bootstrap called")
    private let lock = NSLock()
    private var storedCalls: [BootstrapCall] = []

    var calls: [BootstrapCall] {
        lock.withLock { storedCalls }
    }

    func bootstrap(
        requirement: AgentBootstrapRequirement,
        force: Bool,
        progress: AgentBootstrapProgress
    ) -> CommandResult {
        lock.withLock {
            storedCalls.append(.init(requirement: requirement, force: force))
        }
        expectation.fulfill()
        return CommandResult(exitCode: 0, output: "")
    }
}
#endif
