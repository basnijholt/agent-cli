import Foundation

final class AgentCommandExecutor: @unchecked Sendable {
    private let runtime: AgentRuntime

    init(runtime: AgentRuntime = .shared) {
        self.runtime = runtime
    }

    func prepare(_ command: AgentCommand) -> CommandResult {
        runtime.ensureReady(for: command.bootstrapRequirement, force: command.forceBootstrap)
    }

    func run(_ command: AgentCommand) -> CommandResult {
        runtime.runAgentCLI(arguments: command.arguments)
    }

    func stopHeldTranscription() -> CommandResult {
        runtime.runShell(Self.holdStopShell)
    }

    private static let holdStopShell = #""$AGENTCLI_AGENT_CLI" transcribe --stop --quiet --wait-for-start"#
}
