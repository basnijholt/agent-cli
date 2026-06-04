import Foundation

private extension String {
    var isVisiblyBlank: Bool {
        unicodeScalars.allSatisfy { scalar in
            CharacterSet.whitespacesAndNewlines.contains(scalar)
                || scalar.properties.generalCategory == .format
                || scalar.properties.generalCategory == .control
        }
    }
}

struct AgentCommand {
    let identifier: String
    let title: String
    let arguments: [String]
    let appliesTranscriptionExtraInstructions: Bool
    let appliesTranscriptionDaemonSettings: Bool
    let forceBootstrap: Bool
    let bootstrapRequirement: AgentBootstrapRequirement
    let showsRecordingIndicator: Bool
    let supportsLivePreviewOverlay: Bool
    let startNotificationTitle: String?
    let startNotificationBody: String?
    let finishNotificationTitle: String?

    init(
        identifier: String,
        title: String,
        arguments: [String],
        appliesTranscriptionExtraInstructions: Bool = false,
        appliesTranscriptionDaemonSettings: Bool = false,
        forceBootstrap: Bool = false,
        bootstrapRequirement: AgentBootstrapRequirement = .cliRuntime,
        showsRecordingIndicator: Bool = false,
        supportsLivePreviewOverlay: Bool = false,
        startNotificationTitle: String? = nil,
        startNotificationBody: String? = nil,
        finishNotificationTitle: String? = nil
    ) {
        self.identifier = identifier
        self.title = title
        self.arguments = arguments
        self.appliesTranscriptionExtraInstructions = appliesTranscriptionExtraInstructions
        self.appliesTranscriptionDaemonSettings = appliesTranscriptionDaemonSettings
        self.forceBootstrap = forceBootstrap
        self.bootstrapRequirement = bootstrapRequirement
        self.showsRecordingIndicator = showsRecordingIndicator
        self.supportsLivePreviewOverlay = supportsLivePreviewOverlay
        self.startNotificationTitle = startNotificationTitle
        self.startNotificationBody = startNotificationBody
        self.finishNotificationTitle = finishNotificationTitle
    }

    func resolvedArguments(
        extraInstructions: String?,
        livePreviewOverlayEnabled: Bool = TranscriptionSettings.isLivePreviewOverlayEnabled(),
        transcriptionDaemonArguments: [String]? = nil
    ) -> [String] {
        if appliesTranscriptionDaemonSettings {
            return transcriptionDaemonArguments ?? arguments
        }

        var resolved = arguments

        if supportsLivePreviewOverlay && livePreviewOverlayEnabled {
            resolved += [
                "--live-preview-log",
                LiveTranscriptionPreview.defaultLogPath,
                "--live-preview-interval",
                "1",
                "--live-preview-window",
                "10",
            ]
        }

        guard appliesTranscriptionExtraInstructions else { return resolved }

        let trimmedInstructions = extraInstructions?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmedInstructions.isVisiblyBlank else { return resolved }

        return resolved + ["--extra-instructions", trimmedInstructions]
    }

    var menuActivityTitle: String {
        title
    }

    static let toggleTranscription = AgentCommand(
        identifier: "transcribe",
        title: "Toggle Transcription",
        arguments: [
            "transcribe",
            "--toggle",
            "--quiet",
            "--voice-level-log",
            VoiceLevelLog.defaultLogPath,
            "--transcription-log",
            RecentTranscriptionReader.defaultLogPath,
        ],
        appliesTranscriptionExtraInstructions: true,
        bootstrapRequirement: .transcription,
        showsRecordingIndicator: true,
        supportsLivePreviewOverlay: true,
        startNotificationTitle: "Transcription Started",
        startNotificationBody: "Recording audio. Toggle transcription again to stop and transcribe.",
        finishNotificationTitle: "Transcription Finished"
    )

    static let stopTranscription = AgentCommand(
        identifier: "transcribe-stop",
        title: "Stop Transcription",
        arguments: ["transcribe", "--stop", "--quiet", "--wait-for-start"],
        bootstrapRequirement: .transcription
    )

    static let voiceEdit = AgentCommand(
        identifier: "voice-edit",
        title: "Voice Edit Clipboard",
        arguments: [
            "voice-edit",
            "--toggle",
            "--quiet",
            "--voice-level-log",
            VoiceLevelLog.defaultLogPath,
        ],
        bootstrapRequirement: .transcription,
        showsRecordingIndicator: true,
        startNotificationTitle: "Voice Edit Started",
        startNotificationBody: "Recording audio. Toggle voice edit again to stop.",
        finishNotificationTitle: "Voice Edit Finished"
    )

    static let autocorrect = AgentCommand(
        identifier: "autocorrect",
        title: "Autocorrect Clipboard",
        arguments: ["autocorrect", "--quiet"]
    )

    static let voiceServiceStatus = AgentCommand(
        identifier: "voice-service-status",
        title: "Voice Service Status",
        arguments: ["daemon", "status", "whisper", "--logs", "0"]
    )

    static let installVoiceService = AgentCommand(
        identifier: "install-voice-service",
        title: "Install Voice Service",
        arguments: ["daemon", "install", "whisper", "-y"],
        appliesTranscriptionDaemonSettings: true
    )

    static let installOrUpdateCLI = AgentCommand(
        identifier: "install-or-update-cli",
        title: "Install or Update CLI",
        arguments: ["--version"],
        forceBootstrap: true
    )
}
