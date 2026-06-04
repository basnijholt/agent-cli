import Darwin
import Foundation

private enum AgentCLIRuntimeMode: Equatable {
    case bundled
    case userInstalled

    init(userDefaults: UserDefaults) {
        self = userDefaults.bool(forKey: RuntimeSettings.useUserInstalledAgentCLIKey)
            ? .userInstalled
            : .bundled
    }
}

private final class UserInstalledCLICheckCache {
    private let lock = NSLock()
    private var isAvailable = false

    func hasSuccessfulCheck() -> Bool {
        lock.withLock { isAvailable }
    }

    func update(with result: CommandResult) {
        lock.withLock {
            isAvailable = result.exitCode == 0
        }
    }
}

typealias AgentProcessRunner = (URL, [String], [String: String]) -> CommandResult
typealias LocalhostConnector = (UInt16) -> Bool

struct AgentRuntime {
    static let shared = AgentRuntime()

    private static let bundledUVRelativePath = "Contents/Resources/bin/uv"
    private static let bundledWheelsRelativePath = "Contents/Resources/wheels"
    private static let appSupportDisplayName = "Application Support"
    private static let fallbackPackageSource = "agent-cli"
    private static let bootstrapQueue = DispatchQueue(label: "lt.nijho.agent-cli.bootstrap")
    private static let appPrivateEnvironmentKeys = [
        "AGENTCLI_APP_SUPPORT_DIR",
        "AGENTCLI_RUNTIME_DIR",
        "AGENTCLI_BUNDLED_UV",
        "AGENTCLI_PACKAGE_SOURCE",
        "AGENTCLI_AGENT_CLI",
        "AGENT_CLI_CONFIG_HOME",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_BIN_DIR",
        "UV_TOOL_DIR",
        "UV_TOOL_BIN_DIR",
        "UV_NO_PROGRESS",
    ]
    private let fileManager = FileManager.default
    private let baseEnvironment: [String: String]
    private let userDefaults: UserDefaults
    private let processRunner: AgentProcessRunner
    private let localhostConnector: LocalhostConnector
    private let userInstalledCLICheckCache: UserInstalledCLICheckCache
    private let whisperReadyTimeout: TimeInterval
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
        bundle: Bundle = .main,
        userDefaults: UserDefaults = .standard,
        processRunner: @escaping AgentProcessRunner = {
            AgentRuntime.runProcess(executableURL: $0, arguments: $1, environment: $2)
        },
        localhostConnector: @escaping LocalhostConnector = AgentRuntime.canConnectToLocalhost,
        whisperReadyTimeout: TimeInterval = 180
    ) {
        self.baseEnvironment = environment
        self.userDefaults = userDefaults
        self.processRunner = processRunner
        self.localhostConnector = localhostConnector
        self.userInstalledCLICheckCache = UserInstalledCLICheckCache()
        self.whisperReadyTimeout = whisperReadyTimeout

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

    var usesUserInstalledAgentCLI: Bool {
        runtimeMode == .userInstalled
    }

    private var runtimeMode: AgentCLIRuntimeMode {
        AgentCLIRuntimeMode(userDefaults: userDefaults)
    }

    var agentCLIExecutableURL: URL {
        usesUserInstalledAgentCLI
            ? URL(fileURLWithPath: "/usr/bin/env")
            : agentCLIURL
    }

    func agentCLIProcessArguments(_ arguments: [String]) -> [String] {
        usesUserInstalledAgentCLI
            ? ["agent-cli"] + arguments
            : arguments
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

        if CommandLine.arguments.contains("--agentcli-voice-level-self-test") {
            do {
                try Self.runVoiceLevelSelfTest()
                print("AgentCLI voice-level self-test ok")
                exit(0)
            } catch {
                print("AgentCLI voice-level self-test failed: \(error.localizedDescription)")
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

    private static func runVoiceLevelSelfTest() throws {
        guard argumentValue(AgentCommand.toggleTranscription.arguments, for: "--voice-level-log") == VoiceLevelLog.defaultLogPath else {
            throw SelfTestError("Toggle Transcription does not pass --voice-level-log")
        }
        guard argumentValue(AgentCommand.voiceEdit.arguments, for: "--voice-level-log") == VoiceLevelLog.defaultLogPath else {
            throw SelfTestError("Voice Edit does not pass --voice-level-log")
        }

        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
        defer { try? FileManager.default.removeItem(at: logURL) }

        try """
        {"timestamp":"2026-06-04T12:00:00Z","level":0.25}
        {"timestamp":"2026-06-04T12:00:01Z","level":0.75}
        """.write(to: logURL, atomically: true, encoding: .utf8)

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        guard let now = formatter.date(from: "2026-06-04T12:00:01Z") else {
            throw SelfTestError("Could not construct voice-level test timestamp")
        }
        guard VoiceLevelLog.latestLevel(from: logURL, now: now) == CGFloat(0.75) else {
            throw SelfTestError("VoiceLevelLog did not read latest fresh level")
        }
    }

    private static func argumentValue(_ arguments: [String], for option: String) -> String? {
        guard let index = arguments.firstIndex(of: option),
              arguments.indices.contains(index + 1) else {
            return nil
        }
        return arguments[index + 1]
    }

    private struct SelfTestError: LocalizedError {
        let message: String

        init(_ message: String) {
            self.message = message
        }

        var errorDescription: String? {
            message
        }
    }

    func ensureInstalled(
        force: Bool = false,
        progress: AgentBootstrapProgress = { _ in }
    ) -> CommandResult {
        let mode = runtimeMode
        do {
            try prepareDirectories(for: mode)
        } catch {
            return CommandResult(exitCode: 1, output: "Could not create app support directories: \(error.localizedDescription)")
        }

        if mode == .userInstalled {
            if !force, userInstalledCLICheckCache.hasSuccessfulCheck() {
                return CommandResult(exitCode: 0, output: "")
            }
            progress(.checkingRuntime)
            let result = ensureUserInstalledCLIAvailable()
            userInstalledCLICheckCache.update(with: result)
            return result
        }

        if !force,
           fileManager.isExecutableFile(atPath: agentCLIURL.path),
           (try? String(contentsOf: agentCLIInstallMarkerURL)) == agentCLIInstallMarkerContents {
            return CommandResult(exitCode: 0, output: "")
        }

        progress(.installingRuntime)
        guard fileManager.isExecutableFile(atPath: bundledUVURL.path) else {
            return CommandResult(
                exitCode: 127,
                output: "Bundled uv is missing or not executable: \(bundledUVURL.path)"
            )
        }

        let installDescription = "uv tool install agent-cli[audio,llm]"
        let result = processRunner(
            bundledUVURL,
            [
                "tool",
                "install",
                "--managed-python",
                "--python",
                "3.13",
                "--force",
                agentCLIInstallRequirement
            ],
            commandEnvironment()
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

    private func ensureUserInstalledCLIAvailable() -> CommandResult {
        let result = processRunner(
            agentCLIExecutableURL,
            agentCLIProcessArguments(["--version"]),
            commandEnvironment()
        )
        guard result.exitCode != 127 else {
            return CommandResult(
                exitCode: 127,
                output: "User-installed agent-cli was not found on PATH. Install it with uv, or disable Use User-Installed agent-cli in Settings."
            )
        }
        return result.exitCode == 0
            ? CommandResult(exitCode: 0, output: "")
            : result
    }

    private var agentCLIInstallMarkerContents: String {
        "packageSource=\(agentCLIPackageSource)\ninstallRequirement=\(agentCLIInstallRequirement)\n"
    }

    func ensureReady(
        for requirement: AgentBootstrapRequirement,
        force: Bool = false,
        progress: AgentBootstrapProgress = { _ in }
    ) -> CommandResult {
        Self.bootstrapQueue.sync {
            ensureReadyUnsynchronized(for: requirement, force: force, progress: progress)
        }
    }

    private func ensureReadyUnsynchronized(
        for requirement: AgentBootstrapRequirement,
        force: Bool = false,
        progress: AgentBootstrapProgress
    ) -> CommandResult {
        switch requirement {
        case .cliRuntime:
            return ensureInstalled(force: force, progress: progress)
        case .transcription:
            let installResult = ensureInstalled(force: force, progress: progress)
            guard installResult.exitCode == 0 else {
                return installResult
            }
            return ensureWhisperDaemon(force: force, progress: progress)
        case .transcriptionModel:
            let daemonResult = ensureReadyUnsynchronized(
                for: .transcription,
                force: force,
                progress: progress
            )
            guard daemonResult.exitCode == 0 else {
                return daemonResult
            }
            progress(.warmingWhisperModel)
            return warmUpWhisperModel()
        }
    }

    private func ensureWhisperDaemon(
        force: Bool = false,
        progress: AgentBootstrapProgress
    ) -> CommandResult {
        if !force, (try? String(contentsOf: whisperDaemonMarkerURL)) == whisperDaemonMarkerContents {
            progress(.waitingForVoiceService)
            if localhostConnector(10300) {
                return CommandResult(exitCode: 0, output: "")
            }
        }

        return installWhisperDaemon(progress: progress)
    }

    private func installWhisperDaemon(progress: AgentBootstrapProgress) -> CommandResult {
        progress(.installingVoiceService)
        let arguments = runtimeMode == .bundled
            ? TranscriptionSettings.whisperDaemonInstallArguments(userDefaults: userDefaults)
            : ["daemon", "ensure", "whisper", "--quiet"]
        let result = runAgentCLI(arguments: arguments)
        guard result.exitCode == 0 else {
            return result
        }

        try? whisperDaemonMarkerContents.write(
            to: whisperDaemonMarkerURL,
            atomically: true,
            encoding: .utf8
        )
        progress(.waitingForVoiceService)
        return waitForWhisperDaemonReady()
    }

    private var whisperDaemonMarkerContents: String {
        let modeName = runtimeMode == .userInstalled ? "user-installed" : "bundled"
        var contents = "runtimeMode=\(modeName)\npackageSource=\(agentCLIPackageSource)\n"
        if runtimeMode == .bundled {
            let backend = TranscriptionSettings.selectedBackend(userDefaults: userDefaults)
            let ttlSeconds = TranscriptionSettings.selectedModelTTLSeconds(userDefaults: userDefaults)
            contents += "transcriptionBackend=\(backend.rawValue)\n"
            contents += "transcriptionModel=\(TranscriptionSettings.selectedModelName(userDefaults: userDefaults))\n"
            contents += "transcriptionModelTTLSeconds=\(ttlSeconds)\n"
        }
        return contents
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

    private func waitForWhisperDaemonReady() -> CommandResult {
        waitForWhisperDaemonReady(timeout: whisperReadyTimeout)
    }

    private func waitForWhisperDaemonReady(timeout: TimeInterval) -> CommandResult {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if localhostConnector(10300) {
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
        switch runtimeMode {
        case .userInstalled:
            return userInstalledCLIEnvironment()
        case .bundled:
            return bundledCLIEnvironment()
        }
    }

    private func userInstalledCLIEnvironment() -> [String: String] {
        var environment = baseEnvironment
        for key in Self.appPrivateEnvironmentKeys {
            environment.removeValue(forKey: key)
        }
        // Preserve AGENTCLI_UV_PATH so GUI launches can point at a user-managed uv.
        let existingPATH = environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        environment["PATH"] = userInstalledCLIPath(
            existingPATH: existingPATH,
            loginShellPATH: Self.loginShellPATH(environment: baseEnvironment)
        )
        return environment
    }

    private func bundledCLIEnvironment() -> [String: String] {
        var environment = baseEnvironment
        let existingPATH = environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        environment["AGENTCLI_APP_SUPPORT_DIR"] = appSupportURL.path
        environment["AGENTCLI_RUNTIME_DIR"] = runtimeURL.path
        environment["AGENTCLI_BUNDLED_UV"] = bundledUVURL.path
        environment["AGENTCLI_PACKAGE_SOURCE"] = agentCLIPackageSource
        environment["AGENTCLI_AGENT_CLI"] = agentCLIURL.path
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
        environment["PATH"] = [
            binURL.path,
            resourceBinURL.path,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            existingPATH
        ].joined(separator: ":")

        return environment
    }

    func userInstalledCLIPath(existingPATH: String, loginShellPATH: String? = nil) -> String {
        let homeURL = FileManager.default.homeDirectoryForCurrentUser
        var pathValues: [String] = []
        if let loginShellPATH {
            pathValues.append(loginShellPATH)
        }
        pathValues.append(contentsOf: [
            homeURL
                .appendingPathComponent(".local/bin", isDirectory: true)
                .path,
            homeURL
                .appendingPathComponent(".cargo/bin", isDirectory: true)
                .path,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            existingPATH
        ])

        var seen = Set<String>()
        return pathValues
            .flatMap { $0.split(separator: ":").map(String.init) }
            .filter { !$0.isEmpty }
            .filter { seen.insert($0).inserted }
            .joined(separator: ":")
    }

    private static func loginShellPATH(environment: [String: String]) -> String? {
        let shellPath = environment["SHELL"].flatMap { $0.isEmpty ? nil : $0 } ?? "/bin/zsh"
        guard FileManager.default.isExecutableFile(atPath: shellPath) else { return nil }

        let result = runProcess(
            executableURL: URL(fileURLWithPath: shellPath),
            arguments: ["-lic", "printf '%s\\n' \"$PATH\""],
            environment: environment
        )
        guard result.exitCode == 0 else { return nil }

        return result.output
            .split(separator: "\n")
            .last
            .map(String.init)
    }

    private func prepareDirectories(for mode: AgentCLIRuntimeMode = .bundled) throws {
        try fileManager.createDirectory(at: runtimeURL, withIntermediateDirectories: true)
        guard mode == .bundled else { return }

        try fileManager.createDirectory(at: binURL, withIntermediateDirectories: true)
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
        processRunner(
            URL(fileURLWithPath: "/bin/zsh"),
            ["-lc", shell],
            commandEnvironment()
        )
    }

    func runAgentCLI(arguments: [String]) -> CommandResult {
        processRunner(
            agentCLIExecutableURL,
            agentCLIProcessArguments(arguments),
            commandEnvironment()
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
