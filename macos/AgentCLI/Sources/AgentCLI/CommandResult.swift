import Foundation

struct CommandResult {
    let exitCode: Int32
    let output: String

    func requiringTranscript() -> CommandResult {
        guard exitCode == 0, output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return self
        }
        return CommandResult(
            exitCode: 1,
            output: "No transcript returned. Check the microphone and ASR server, then try again. "
                + "If a recording was saved, recover it with agent-cli transcribe --last-recording."
        )
    }
}
