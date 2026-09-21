import Foundation

struct CommandResult {
    let exitCode: Int32
    let output: String
    /// Unmixed stdout for child processes; nil for synthetic results.
    let standardOutput: String?
    let standardError: String?

    init(exitCode: Int32, output: String, standardOutput: String? = nil, standardError: String? = nil) {
        self.exitCode = exitCode
        self.output = output
        self.standardOutput = standardOutput
        self.standardError = standardError
    }

    var pasteText: String? {
        let candidates = standardOutput == nil && standardError == nil
            ? [output] : [standardOutput ?? "", standardError ?? ""]
        return candidates
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
    }

    func requiringTranscript() -> CommandResult {
        guard exitCode == 0 else { return self }
        let transcript = (standardOutput ?? output).trimmingCharacters(in: .whitespacesAndNewlines)
        if !transcript.isEmpty {
            return CommandResult(exitCode: 0, output: transcript, standardOutput: transcript, standardError: standardError)
        }
        return CommandResult(
            exitCode: 1,
            output: "No transcript returned. Check the microphone and ASR server, then try again. "
                + "If a recording was saved, recover it with agent-cli transcribe --last-recording.",
            standardOutput: standardOutput,
            standardError: standardError
        )
    }
}
