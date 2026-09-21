import Foundation

struct CommandResult {
    let exitCode: Int32
    let output: String
    /// Unmixed stdout for child processes; nil for synthetic results.
    let standardOutput: String?

    init(exitCode: Int32, output: String, standardOutput: String? = nil) {
        self.exitCode = exitCode
        self.output = output
        self.standardOutput = standardOutput
    }

    func requiringTranscript() -> CommandResult {
        guard exitCode == 0 else { return self }
        let transcript = (standardOutput ?? output).trimmingCharacters(in: .whitespacesAndNewlines)
        if !transcript.isEmpty {
            return CommandResult(exitCode: 0, output: transcript, standardOutput: transcript)
        }
        return CommandResult(
            exitCode: 1,
            output: "No transcript returned. Check the microphone and ASR server, then try again. "
                + "If a recording was saved, recover it with agent-cli transcribe --last-recording."
        )
    }
}
