import Darwin
import Foundation

struct AgentRuntime {
    static let shared = AgentRuntime()

    private static let bundledUVRelativePath = "Contents/Resources/bin/uv"
    private static let bundledWheelsRelativePath = "Contents/Resources/wheels"
    private static let appSupportDisplayName = "Application Support"
    private static let fallbackPackageSource = "agent-cli"
    private static let bootstrapQueue = DispatchQueue(label: "lt.nijho.agent-cli.bootstrap")
    private let fileManager = FileManager.default
    let appSupportURL: URL
    let bundledUVURL: URL
    let bundledWheelsURL: URL
    let agentCLIPackageSource: String
    let agentCLIInstallRequirement: String
    let binURL: URL
    let runtimeURL: URL
    let agentCLIURL: URL
    let agentCLIInstallMarkerURL: URL
    let whisperDaemonMarkerURL: URL
    let whisperWarmUpAudioURL: URL
    let accessibilityPromptMarkerURL: URL
    let notificationLogoURL: URL?
    let lastErrorURL: URL
    let logsURL: URL

    init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundle: Bundle = .main
    ) {
        if let override = environment["AGENTCLI_APP_SUPPORT_DIR"], !override.isEmpty {
            appSupportURL = URL(fileURLWithPath: override, isDirectory: true)
        } else {
            let baseURL = FileManager.default.urls(
                for: .applicationSupportDirectory,
                in: .userDomainMask
            )[0]
            appSupportURL = baseURL.appendingPathComponent("AgentCLI", isDirectory: true)
        }

        bundledUVURL = bundle.bundleURL.appendingPathComponent(Self.bundledUVRelativePath)
        bundledWheelsURL = bundle.bundleURL.appendingPathComponent(Self.bundledWheelsRelativePath)
        agentCLIPackageSource = Self.resolveBundledWheel(in: bundledWheelsURL) ?? Self.fallbackPackageSource
        agentCLIInstallRequirement = "\(agentCLIPackageSource)[audio,llm]"
        binURL = appSupportURL.appendingPathComponent("bin", isDirectory: true)
        runtimeURL = appSupportURL.appendingPathComponent("runtime", isDirectory: true)
        agentCLIURL = binURL.appendingPathComponent("agent-cli")
        agentCLIInstallMarkerURL = appSupportURL.appendingPathComponent(".agent-cli-installed")
        whisperDaemonMarkerURL = appSupportURL.appendingPathComponent(".whisper-daemon-installed")
        whisperWarmUpAudioURL = runtimeURL.appendingPathComponent("whisper-model-warmup.wav")
        accessibilityPromptMarkerURL = appSupportURL.appendingPathComponent(".accessibility-prompted")
        notificationLogoURL = bundle.url(forResource: "logo-avatar", withExtension: "png")
        lastErrorURL = appSupportURL.appendingPathComponent("last-error.txt")
        logsURL = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs", isDirectory: true)
    }

    private static func resolveBundledWheel(in wheelsURL: URL) -> String? {
        let wheelURLs = (try? FileManager.default.contentsOfDirectory(
            at: wheelsURL,
            includingPropertiesForKeys: nil
        )) ?? []

        return wheelURLs
            .filter {
                $0.lastPathComponent.hasPrefix("agent_cli-")
                    && $0.pathExtension == "whl"
            }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .last?
            .path
    }

    func runSelfTestIfRequested() {
        if CommandLine.arguments.contains("--agentcli-self-test") {
            do {
                try prepareDirectories()
                guard fileManager.isExecutableFile(atPath: bundledUVURL.path) else {
                    print("Bundled uv is missing or not executable: \(bundledUVURL.path)")
                    exit(1)
                }
                print("AgentCLI self-test ok")
                print("location=\(Self.appSupportDisplayName)")
                print("appSupport=\(appSupportURL.path)")
                print("uv=\(bundledUVURL.path)")
                print("packageSource=\(agentCLIPackageSource)")
                print("agentCLI=\(agentCLIURL.path)")
                print("notificationLogo=\(notificationLogoURL?.path ?? "missing")")
                exit(0)
            } catch {
                print("AgentCLI self-test failed: \(error.localizedDescription)")
                exit(1)
            }
        }

        guard CommandLine.arguments.contains("--agentcli-bootstrap-self-test") else { return }

        let bootstrap = ensureReady(for: .transcription, force: true)
        guard bootstrap.exitCode == 0 else {
            print("AgentCLI bootstrap self-test failed: \(bootstrap.output)")
            exit(1)
        }

        let transcription = runAgentCLI(arguments: AgentCommand.toggleTranscription.arguments)
        guard transcription.exitCode == 0 else {
            print("AgentCLI transcription self-test failed: \(transcription.output)")
            exit(1)
        }

        print("AgentCLI bootstrap self-test ok")
        if !bootstrap.output.isEmpty {
            print(bootstrap.output)
        }
        if !transcription.output.isEmpty {
            print(transcription.output)
        }
        exit(0)
    }

    func ensureInstalled(force: Bool = false) -> CommandResult {
        do {
            try prepareDirectories()
        } catch {
            return CommandResult(exitCode: 1, output: "Could not create app support directories: \(error.localizedDescription)")
        }

        if !force,
           fileManager.isExecutableFile(atPath: agentCLIURL.path),
           (try? String(contentsOf: agentCLIInstallMarkerURL)) == agentCLIInstallMarkerContents {
            return CommandResult(exitCode: 0, output: "")
        }

        guard fileManager.isExecutableFile(atPath: bundledUVURL.path) else {
            return CommandResult(
                exitCode: 127,
                output: "Bundled uv is missing or not executable: \(bundledUVURL.path)"
            )
        }

        let installDescription = "uv tool install agent-cli[audio,llm]"
        let result = Self.runProcess(
            executableURL: bundledUVURL,
            arguments: [
                "tool",
                "install",
                "--managed-python",
                "--python",
                "3.13",
                "--force",
                agentCLIInstallRequirement
            ],
            environment: commandEnvironment()
        )
        if result.exitCode != 0, result.output.isEmpty {
            return CommandResult(exitCode: result.exitCode, output: "\(installDescription) failed")
        }
        if result.exitCode == 0 {
            try? agentCLIInstallMarkerContents.write(
                to: agentCLIInstallMarkerURL,
                atomically: true,
                encoding: .utf8
            )
        }
        return result
    }

    private var agentCLIInstallMarkerContents: String {
        "packageSource=\(agentCLIPackageSource)\ninstallRequirement=\(agentCLIInstallRequirement)\n"
    }

    func ensureReady(for requirement: AgentBootstrapRequirement, force: Bool = false) -> CommandResult {
        Self.bootstrapQueue.sync {
            ensureReadyUnsynchronized(for: requirement, force: force)
        }
    }

    private func ensureReadyUnsynchronized(for requirement: AgentBootstrapRequirement, force: Bool = false) -> CommandResult {
        switch requirement {
        case .cliRuntime:
            return ensureInstalled(force: force)
        case .transcription:
            let installResult = ensureInstalled(force: force)
            guard installResult.exitCode == 0 else {
                return installResult
            }
            return ensureWhisperDaemon(force: force)
        case .transcriptionModel:
            let daemonResult = ensureReadyUnsynchronized(for: .transcription, force: force)
            guard daemonResult.exitCode == 0 else {
                return daemonResult
            }
            return warmUpWhisperModel()
        }
    }

    private func ensureWhisperDaemon(force: Bool = false) -> CommandResult {
        let whisperDaemonMarkerContents = "packageSource=\(agentCLIPackageSource)\n"
        if !force, (try? String(contentsOf: whisperDaemonMarkerURL)) == whisperDaemonMarkerContents {
            return waitForWhisperDaemonReady()
        }

        let result = runAgentCLI(arguments: ["daemon", "install", "whisper", "-y"])
        guard result.exitCode == 0 else {
            return result
        }

        try? whisperDaemonMarkerContents.write(
            to: whisperDaemonMarkerURL,
            atomically: true,
            encoding: .utf8
        )
        return waitForWhisperDaemonReady()
    }

    private func warmUpWhisperModel() -> CommandResult {
        let warmUpAudioURL: URL
        do {
            warmUpAudioURL = try writeWhisperWarmUpAudio()
        } catch {
            return CommandResult(
                exitCode: 1,
                output: "Could not prepare Whisper model warm-up audio: \(error.localizedDescription)"
            )
        }

        let result = runAgentCLI(arguments: [
            "transcribe",
            "--from-file",
            warmUpAudioURL.path,
            "--asr-provider",
            "wyoming",
            "--asr-wyoming-ip",
            "127.0.0.1",
            "--asr-wyoming-port",
            "10300",
            "--no-llm",
            "--no-clipboard",
            "--quiet"
        ])
        guard result.exitCode == 0 else {
            return result
        }
        return CommandResult(exitCode: 0, output: "")
    }

    private func writeWhisperWarmUpAudio() throws -> URL {
        let sampleRate: UInt32 = 16_000
        let channelCount: UInt16 = 1
        let bitsPerSample: UInt16 = 16
        let sampleCount: UInt32 = sampleRate / 4
        let bytesPerSample = bitsPerSample / 8
        let byteRate = sampleRate * UInt32(channelCount) * UInt32(bytesPerSample)
        let blockAlign = channelCount * bytesPerSample
        let dataSize = sampleCount * UInt32(blockAlign)
        let riffSize = 36 + dataSize

        var data = Data()
        appendASCII("RIFF", to: &data)
        appendUInt32(riffSize, to: &data)
        appendASCII("WAVE", to: &data)
        appendASCII("fmt ", to: &data)
        appendUInt32(16, to: &data)
        appendUInt16(1, to: &data)
        appendUInt16(channelCount, to: &data)
        appendUInt32(sampleRate, to: &data)
        appendUInt32(byteRate, to: &data)
        appendUInt16(blockAlign, to: &data)
        appendUInt16(bitsPerSample, to: &data)
        appendASCII("data", to: &data)
        appendUInt32(dataSize, to: &data)
        data.append(Data(repeating: 0, count: Int(dataSize)))

        try data.write(to: whisperWarmUpAudioURL, options: .atomic)
        return whisperWarmUpAudioURL
    }

    private func appendASCII(_ string: String, to data: inout Data) {
        data.append(string.data(using: .ascii) ?? Data())
    }

    private func appendUInt16(_ value: UInt16, to data: inout Data) {
        var littleEndianValue = value.littleEndian
        withUnsafeBytes(of: &littleEndianValue) { bytes in
            data.append(contentsOf: bytes)
        }
    }

    private func appendUInt32(_ value: UInt32, to data: inout Data) {
        var littleEndianValue = value.littleEndian
        withUnsafeBytes(of: &littleEndianValue) { bytes in
            data.append(contentsOf: bytes)
        }
    }

    private func waitForWhisperDaemonReady(timeout: TimeInterval = 180) -> CommandResult {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if Self.canConnectToLocalhost(port: 10300) {
                return CommandResult(exitCode: 0, output: "")
            }
            Thread.sleep(forTimeInterval: 0.5)
        }

        let status = runAgentCLI(arguments: ["daemon", "status", "whisper", "--logs", "80"])
        let statusOutput = status.output.trimmingCharacters(in: .whitespacesAndNewlines)
        let output = statusOutput.isEmpty
            ? "Whisper ASR service did not become ready at localhost:10300."
            : "Whisper ASR service did not become ready at localhost:10300.\n\n\(statusOutput)"
        return CommandResult(exitCode: 1, output: output)
    }

    private static func canConnectToLocalhost(port: UInt16) -> Bool {
        let socketFD = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else {
            return false
        }
        defer { close(socketFD) }

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian

        guard inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) == 1 else {
            return false
        }

        return withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                connect(socketFD, socketAddress, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }

    func commandEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["AGENTCLI_APP_SUPPORT_DIR"] = appSupportURL.path
        environment["AGENTCLI_AGENT_CLI"] = agentCLIURL.path
        environment["AGENTCLI_RUNTIME_DIR"] = runtimeURL.path
        environment["AGENTCLI_BUNDLED_UV"] = bundledUVURL.path
        environment["AGENTCLI_PACKAGE_SOURCE"] = agentCLIPackageSource
        environment["AGENT_CLI_CONFIG_HOME"] = appSupportURL.appendingPathComponent("config", isDirectory: true).path
        environment["UV_CACHE_DIR"] = appSupportURL.appendingPathComponent("cache/uv", isDirectory: true).path
        environment["UV_PYTHON_INSTALL_DIR"] = appSupportURL.appendingPathComponent("uv/python", isDirectory: true).path
        environment["UV_PYTHON_BIN_DIR"] = binURL.path
        environment["UV_TOOL_DIR"] = appSupportURL.appendingPathComponent("uv/tools", isDirectory: true).path
        environment["UV_TOOL_BIN_DIR"] = binURL.path
        environment["UV_NO_PROGRESS"] = "1"
        environment["NO_COLOR"] = "1"
        environment["TERM"] = "dumb"

        let resourceBinURL = bundledUVURL.deletingLastPathComponent()
        let existingPATH = environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        environment["PATH"] = [
            binURL.path,
            resourceBinURL.path,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            existingPATH
        ].joined(separator: ":")

        return environment
    }

    private func prepareDirectories() throws {
        try fileManager.createDirectory(at: binURL, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: runtimeURL, withIntermediateDirectories: true)
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("cache/uv", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("uv/python", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("uv/tools", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("config", isDirectory: true),
            withIntermediateDirectories: true
        )
    }

    func runShell(_ shell: String) -> CommandResult {
        Self.runProcess(
            executableURL: URL(fileURLWithPath: "/bin/zsh"),
            arguments: ["-lc", shell],
            environment: commandEnvironment()
        )
    }

    func runAgentCLI(arguments: [String]) -> CommandResult {
        Self.runProcess(
            executableURL: agentCLIURL,
            arguments: arguments,
            environment: commandEnvironment()
        )
    }

    static func runProcess(
        executableURL: URL,
        arguments: [String],
        environment: [String: String]
    ) -> CommandResult {
        let task = Process()
        let pipe = Pipe()

        task.executableURL = executableURL
        task.arguments = arguments
        task.environment = environment
        task.standardOutput = pipe
        task.standardError = pipe

        do {
            try task.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            task.waitUntilExit()
            return CommandResult(
                exitCode: task.terminationStatus,
                output: String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            )
        } catch {
            return CommandResult(exitCode: 127, output: error.localizedDescription)
        }
    }
}
