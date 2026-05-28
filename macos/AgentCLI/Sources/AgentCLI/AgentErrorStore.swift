import AppKit
import Foundation

struct AgentErrorStore {
    func hasLastError() -> Bool {
        FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path)
    }

    @discardableResult
    func recordFailure(title: String, result: CommandResult) -> String {
        let output = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
        let details = """
        Agent CLI Error
        Time: \(ISO8601DateFormatter().string(from: Date()))
        Context: \(title)
        Exit code: \(result.exitCode)

        Output:
        \(output.isEmpty ? "(no output)" : output)
        """

        do {
            try FileManager.default.createDirectory(
                at: AgentRuntime.shared.appSupportURL,
                withIntermediateDirectories: true
            )
            try details.write(to: AgentRuntime.shared.lastErrorURL, atomically: true, encoding: .utf8)
        } catch {
            return details
        }

        return details
    }

    func readLastError() -> String? {
        guard let details = try? String(contentsOf: AgentRuntime.shared.lastErrorURL),
              !details.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return details
    }

    func openLastError() -> Bool {
        guard hasLastError() else { return false }
        return NSWorkspace.shared.open(AgentRuntime.shared.lastErrorURL)
    }
}
