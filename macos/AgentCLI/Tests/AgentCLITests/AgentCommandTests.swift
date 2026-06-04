#if canImport(XCTest)
import AppKit
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
                "--voice-level-log",
                "~/.config/agent-cli/voice-levels.jsonl",
                "--transcription-log",
                "~/.config/agent-cli/transcriptions.jsonl",
            ]
        )
        XCTAssertEqual(AgentCommand.toggleTranscription.bootstrapRequirement, .transcription)
    }

    func testToggleTranscriptionAddsLivePreviewArgumentsWhenEnabled() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(
                extraInstructions: nil,
                livePreviewOverlayEnabled: true
            ),
            [
                "transcribe",
                "--toggle",
                "--quiet",
                "--transcription-log",
                "~/.config/agent-cli/transcriptions.jsonl",
                "--live-preview-log",
                "~/.config/agent-cli/live-preview.jsonl",
                "--live-preview-interval",
                "1",
                "--live-preview-window",
                "10",
            ]
        )
    }

    func testToggleTranscriptionAppendsConfiguredExtraInstructions() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(
                extraInstructions: "  Remember Bas and Henk.\nPrefer project names.  ",
                livePreviewOverlayEnabled: true
            ),
            [
                "transcribe",
                "--toggle",
                "--quiet",
                "--voice-level-log",
                "~/.config/agent-cli/voice-levels.jsonl",
                "--transcription-log",
                "~/.config/agent-cli/transcriptions.jsonl",
                "--live-preview-log",
                "~/.config/agent-cli/live-preview.jsonl",
                "--live-preview-interval",
                "1",
                "--live-preview-window",
                "10",
                "--extra-instructions",
                "Remember Bas and Henk.\nPrefer project names.",
            ]
        )
    }

    func testBlankExtraInstructionsAreIgnored() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(
                extraInstructions: "  \n\t  ",
                livePreviewOverlayEnabled: false
            ),
            AgentCommand.toggleTranscription.arguments
        )
    }

    func testVisuallyBlankExtraInstructionsAreIgnored() {
        XCTAssertEqual(
            AgentCommand.toggleTranscription.resolvedArguments(
                extraInstructions: "\u{2060}\u{FEFF}",
                livePreviewOverlayEnabled: false
            ),
            AgentCommand.toggleTranscription.arguments
        )
    }

    func testExtraInstructionsOnlyApplyToTranscription() {
        XCTAssertEqual(
            AgentCommand.autocorrect.resolvedArguments(extraInstructions: "Remember Bas."),
            AgentCommand.autocorrect.arguments
        )
    }

    func testInstallVoiceServiceUsesResolvedTranscriptionDaemonArguments() {
        XCTAssertEqual(
            AgentCommand.installVoiceService.resolvedArguments(
                extraInstructions: nil,
                transcriptionDaemonArguments: [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "nemo",
                    "--model", "parakeet-tdt-0.6b-v3",
                    "--ttl", "86400",
                ]
            ),
            [
                "daemon", "install", "whisper", "-y", "--",
                "--backend", "nemo",
                "--model", "parakeet-tdt-0.6b-v3",
                "--ttl", "86400",
            ]
        )
    }

    func testTranscriptionDaemonArgumentsIncludeConfiguredTTL() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.transcription-ttl")!
        defaults.removePersistentDomain(forName: "AgentCLITests.transcription-ttl")
        defaults.set("nemo", forKey: TranscriptionSettings.transcriptionBackendKey)
        defaults.set("parakeet-unified-en-0.6b", forKey: TranscriptionSettings.transcriptionModelKey)
        defaults.set(86400, forKey: TranscriptionSettings.transcriptionModelTTLSecondsKey)

        XCTAssertEqual(
            TranscriptionSettings.whisperDaemonInstallArguments(userDefaults: defaults),
            [
                "daemon", "install", "whisper", "-y", "--",
                "--backend", "nemo",
                "--model", "parakeet-unified-en-0.6b",
                "--ttl", "86400",
            ]
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

    func testUserInstalledRuntimeCachesSuccessfulCLIAvailabilityCheck() {
        let defaults = UserDefaults(suiteName: "AgentCLITests.user-runtime-cache")!
        defaults.removePersistentDomain(forName: "AgentCLITests.user-runtime-cache")
        defaults.set(true, forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
        var processArguments: [[String]] = []
        let runtime = AgentRuntime(
            environment: [
                "AGENTCLI_APP_SUPPORT_DIR": "/tmp/agentcli-test-support",
                "PATH": "/custom/bin",
                "SHELL": "/no/such/shell",
            ],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                processArguments.append(arguments)
                return CommandResult(exitCode: 0, output: "agent-cli 1.2.3")
            }
        )

        var phases: [BootstrapPhase] = []
        XCTAssertEqual(runtime.ensureReady(for: .cliRuntime) { phases.append($0) }.exitCode, 0)
        XCTAssertEqual(runtime.ensureReady(for: .cliRuntime) { phases.append($0) }.exitCode, 0)
        XCTAssertEqual(runtime.ensureReady(for: .cliRuntime, force: true) { phases.append($0) }.exitCode, 0)

        XCTAssertEqual(processArguments, [["agent-cli", "--version"], ["agent-cli", "--version"]])
        XCTAssertEqual(phases, [.checkingRuntime, .checkingRuntime])
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
                if arguments == [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "auto",
                    "--model", "large-v3",
                    "--ttl", "300",
                ] {
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
                [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "auto",
                    "--model", "large-v3",
                    "--ttl", "300",
                ],
            ]
        )
        XCTAssertEqual(phases, [.installingVoiceService, .waitingForVoiceService])
    }

    func testTranscriptionBootstrapInstallsDefaultWhisperModel() throws {
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

        let defaults = UserDefaults(suiteName: "AgentCLITests.default-whisper-model")!
        defaults.removePersistentDomain(forName: "AgentCLITests.default-whisper-model")
        var installedWhisper = false
        var processArguments: [[String]] = []
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": tempURL.path],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                processArguments.append(arguments)
                if arguments == [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "auto",
                    "--model", "large-v3",
                    "--ttl", "300",
                ] {
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

        let result = runtime.ensureReady(for: .transcription)

        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(
            processArguments,
            [
                [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "auto",
                    "--model", "large-v3",
                    "--ttl", "300",
                ],
            ]
        )
    }

    func testTranscriptionBootstrapInstallsSelectedNemoModel() throws {
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

        let defaults = UserDefaults(suiteName: "AgentCLITests.nemo-model")!
        defaults.removePersistentDomain(forName: "AgentCLITests.nemo-model")
        defaults.set("nemo", forKey: "transcriptionBackend")
        defaults.set("parakeet-tdt-0.6b-v3", forKey: "transcriptionModel")

        var installedWhisper = false
        var processArguments: [[String]] = []
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": tempURL.path],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                processArguments.append(arguments)
                if arguments == [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "nemo",
                    "--model", "parakeet-tdt-0.6b-v3",
                    "--ttl", "300",
                ] {
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

        let result = runtime.ensureReady(for: .transcription)

        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(
            processArguments,
            [
                [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "nemo",
                    "--model", "parakeet-tdt-0.6b-v3",
                    "--ttl", "300",
                ],
            ]
        )
    }

    func testSelectedWhisperModelInvalidatesBundledDaemonMarker() throws {
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

        let defaults = UserDefaults(suiteName: "AgentCLITests.whisper-marker")!
        defaults.removePersistentDomain(forName: "AgentCLITests.whisper-marker")
        defaults.set("nemo", forKey: "transcriptionBackend")
        defaults.set("parakeet-tdt-0.6b-v3", forKey: "transcriptionModel")
        var installedWhisper = false
        var processArguments: [[String]] = []
        let runtime = AgentRuntime(
            environment: ["AGENTCLI_APP_SUPPORT_DIR": tempURL.path],
            userDefaults: defaults,
            processRunner: { _, arguments, _ in
                processArguments.append(arguments)
                if arguments == [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "nemo",
                    "--model", "parakeet-tdt-0.6b-v3",
                    "--ttl", "300",
                ] {
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

        XCTAssertEqual(
            runtime.ensureReady(for: .transcription).exitCode,
            0
        )
        XCTAssertEqual(
            processArguments,
            [
                [
                    "daemon", "install", "whisper", "-y", "--",
                    "--backend", "nemo",
                    "--model", "parakeet-tdt-0.6b-v3",
                    "--ttl", "300",
                ],
            ]
        )
    }

    func testAppVersionDisplayIncludesShortVersionAndBuild() {
        XCTAssertEqual(
            AppMetadata.versionDisplayString(infoDictionary: [
                "CFBundleShortVersionString": "0.95.9",
                "CFBundleVersion": "528",
            ]),
            "0.95.9 (528)"
        )
    }

    func testAppVersionDisplayOmitsDuplicateBuildVersion() {
        XCTAssertEqual(
            AppMetadata.versionDisplayString(infoDictionary: [
                "CFBundleShortVersionString": "0.95.9",
                "CFBundleVersion": "0.95.9",
            ]),
            "0.95.9"
        )
    }

    func testSparkleConfigurationRequiresFeedURLAndPublicKey() {
        XCTAssertFalse(AppMetadata.sparkleConfiguration(infoDictionary: [:]).isConfigured)
        XCTAssertFalse(
            AppMetadata.sparkleConfiguration(infoDictionary: [
                "SUFeedURL": "https://raw.githubusercontent.com/basnijholt/agent-cli/main/macos/appcast.xml",
            ]).isConfigured
        )
        XCTAssertTrue(
            AppMetadata.sparkleConfiguration(infoDictionary: [
                "SUFeedURL": "https://raw.githubusercontent.com/basnijholt/agent-cli/main/macos/appcast.xml",
                "SUPublicEDKey": "base64-public-key",
            ]).isConfigured
        )
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

    func testMenuBarIconShowsPreparingBeforeRecording() {
        XCTAssertEqual(MenuBarIconState.current(isPreparing: false, isRecording: false), .idle)
        XCTAssertEqual(MenuBarIconState.current(isPreparing: false, isRecording: true), .recording)
        XCTAssertEqual(MenuBarIconState.current(isPreparing: true, isRecording: false), .preparing)
        XCTAssertEqual(MenuBarIconState.current(isPreparing: true, isRecording: true), .preparing)
    }

    func testMenuBarIconUsesFixedSetupAndRecordingBadgeColors() {
        XCTAssertNil(MenuBarIconImage.badgeColor(for: .idle))
        XCTAssertEqual(MenuBarIconImage.badgeColor(for: .preparing), .systemBlue)
        XCTAssertEqual(MenuBarIconImage.badgeColor(for: .recording), .systemRed)
    }

    func testMenuActivityStatusFormatsActiveWorkWithSpinnerAndElapsedCounter() {
        let startedAt = Date(timeIntervalSinceReferenceDate: 1_000)
        let now = Date(timeIntervalSinceReferenceDate: 1_125)

        XCTAssertEqual(
            MenuActivityStatus.active(title: "Recording", startedAt: startedAt, now: now).message,
            "Recording ◓ (02:05)"
        )
        XCTAssertTrue(MenuActivityStatus.active(title: "Recording", startedAt: startedAt, now: now).isActive)
    }

    func testMenuActivityStatusFormatsCompletedWorkWithCheckmark() {
        XCTAssertEqual(MenuActivityStatus.completed(title: "Ready").message, "Ready ✓")
        XCTAssertEqual(MenuActivityStatus.completed(title: "Text inserted").message, "Text inserted ✓")
        XCTAssertFalse(MenuActivityStatus.completed(title: "Ready").isActive)
    }

    func testMenuActivityTrackerPrioritizesAndRestoresActivities() {
        var tracker = MenuActivityTracker()
        let startedAt = Date(timeIntervalSinceReferenceDate: 1_000)
        let now = Date(timeIntervalSinceReferenceDate: 1_065)
        let fallback = MenuActivityStatus.completed(title: "Ready")

        tracker.beginCommand(identifier: "autocorrect", title: "Autocorrect Clipboard", at: startedAt)
        XCTAssertEqual(
            tracker.status(now: now, fallback: fallback),
            MenuActivityStatus.active(title: "Autocorrect Clipboard", startedAt: startedAt, now: now)
        )

        tracker.beginRecording(at: startedAt.addingTimeInterval(10))
        XCTAssertEqual(
            tracker.status(now: now, fallback: fallback),
            MenuActivityStatus.active(title: "Recording", startedAt: startedAt.addingTimeInterval(10), now: now)
        )

        tracker.beginTranscribing(at: startedAt.addingTimeInterval(20))
        XCTAssertEqual(
            tracker.status(now: now, fallback: fallback),
            MenuActivityStatus.active(title: "Transcribing", startedAt: startedAt.addingTimeInterval(20), now: now)
        )

        tracker.beginBootstrap(title: "Installing CLI runtime", at: startedAt.addingTimeInterval(30))
        XCTAssertEqual(
            tracker.status(now: now, fallback: fallback),
            MenuActivityStatus.active(
                title: "Installing CLI runtime",
                startedAt: startedAt.addingTimeInterval(30),
                now: now
            )
        )

        tracker.finishBootstrap()
        XCTAssertEqual(
            tracker.status(now: now, fallback: fallback),
            MenuActivityStatus.active(title: "Transcribing", startedAt: startedAt.addingTimeInterval(20), now: now)
        )

        tracker.finishTranscribing()
        tracker.finishRecording()
        tracker.finishCommand(identifier: "autocorrect")

        XCTAssertEqual(tracker.status(now: now, fallback: fallback), fallback)
    }

    func testMenuActivityTrackerRestoresPreviousCommandWhenLatestFinishes() {
        var tracker = MenuActivityTracker()
        let startedAt = Date(timeIntervalSinceReferenceDate: 2_000)
        let fallback = MenuActivityStatus.completed(title: "Ready")

        tracker.beginCommand(identifier: "first", title: "First Command", at: startedAt)
        tracker.beginCommand(identifier: "second", title: "Second Command", at: startedAt.addingTimeInterval(4))
        tracker.finishCommand(identifier: "second")

        XCTAssertEqual(
            tracker.status(now: startedAt.addingTimeInterval(12), fallback: fallback),
            MenuActivityStatus.active(title: "First Command", startedAt: startedAt, now: startedAt.addingTimeInterval(12))
        )
    }

    @MainActor
    func testIdleMenuStatusUsesCompletedCheckmark() {
        let runner = AgentCommandRunner { _, _, _ in
            CommandResult(exitCode: 0, output: "")
        }

        XCTAssertEqual(runner.menuStatusMessage, "Ready ✓")

        runner.statusMessage = "Text inserted"

        XCTAssertEqual(runner.menuStatusMessage, "Text inserted ✓")
    }

    @MainActor
    func testMenuStatusComputesElapsedPreparationTimeWhenRead() {
        let bootstrapStarted = expectation(description: "bootstrap started")
        let releaseBootstrap = DispatchSemaphore(value: 0)
        let runner = AgentCommandRunner { _, _, _ in
            bootstrapStarted.fulfill()
            releaseBootstrap.wait()
            return CommandResult(exitCode: 0, output: "")
        }

        runner.warmUpTranscription()
        defer { releaseBootstrap.signal() }

        XCTAssertEqual(runner.menuStatusMessage, "Checking CLI runtime ◐ (00:00)")
        wait(for: [bootstrapStarted], timeout: 2)
        RunLoop.current.run(until: Date().addingTimeInterval(1.1))

        let elapsedStatus = runner.menuStatusMessage
        XCTAssertTrue(
            elapsedStatus.contains("Checking CLI runtime"),
            "Expected checking status, got: \(elapsedStatus)"
        )
        XCTAssertTrue(
            elapsedStatus.contains("(00:01)") || elapsedStatus.contains("(00:02)"),
            "Expected elapsed counter, got: \(elapsedStatus)"
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
