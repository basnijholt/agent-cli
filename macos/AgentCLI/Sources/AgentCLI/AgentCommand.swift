import Foundation

struct AgentCommand {
    let identifier: String
    let title: String
    let shell: String
    let forceBootstrap: Bool
    let requiresWhisperDaemon: Bool
    let showsRecordingIndicator: Bool
    let startNotificationTitle: String?
    let startNotificationBody: String?
    let finishNotificationTitle: String?

    init(
        identifier: String,
        title: String,
        shell: String,
        forceBootstrap: Bool = false,
        requiresWhisperDaemon: Bool = false,
        showsRecordingIndicator: Bool = false,
        startNotificationTitle: String? = nil,
        startNotificationBody: String? = nil,
        finishNotificationTitle: String? = nil
    ) {
        self.identifier = identifier
        self.title = title
        self.shell = shell
        self.forceBootstrap = forceBootstrap
        self.requiresWhisperDaemon = requiresWhisperDaemon
        self.showsRecordingIndicator = showsRecordingIndicator
        self.startNotificationTitle = startNotificationTitle
        self.startNotificationBody = startNotificationBody
        self.finishNotificationTitle = finishNotificationTitle
    }

    static let toggleTranscription = AgentCommand(
        identifier: "transcribe",
        title: "Toggle Transcription",
        shell: #""$AGENTCLI_AGENT_CLI" transcribe --toggle --quiet"#,
        requiresWhisperDaemon: true,
        showsRecordingIndicator: true,
        startNotificationTitle: "Transcription Started",
        startNotificationBody: "Recording audio. Toggle transcription again to stop and transcribe.",
        finishNotificationTitle: "Transcription Finished"
    )

    static let voiceEdit = AgentCommand(
        identifier: "voice-edit",
        title: "Voice Edit Clipboard",
        shell: #""$AGENTCLI_AGENT_CLI" voice-edit --toggle --quiet"#,
        requiresWhisperDaemon: true,
        showsRecordingIndicator: true,
        startNotificationTitle: "Voice Edit Started",
        startNotificationBody: "Recording audio. Toggle voice edit again to stop.",
        finishNotificationTitle: "Voice Edit Finished"
    )

    static let autocorrect = AgentCommand(
        identifier: "autocorrect",
        title: "Autocorrect Clipboard",
        shell: #""$AGENTCLI_AGENT_CLI" autocorrect --quiet"#
    )

    static let voiceServiceStatus = AgentCommand(
        identifier: "voice-service-status",
        title: "Voice Service Status",
        shell: #""$AGENTCLI_AGENT_CLI" daemon status whisper --logs 0"#
    )

    static let installVoiceService = AgentCommand(
        identifier: "install-voice-service",
        title: "Install Voice Service",
        shell: #""$AGENTCLI_AGENT_CLI" daemon install whisper -y"#
    )

    static let installOrUpdateCLI = AgentCommand(
        identifier: "install-or-update-cli",
        title: "Install or Update CLI",
        shell: #""$AGENTCLI_AGENT_CLI" --version"#,
        forceBootstrap: true
    )
}
