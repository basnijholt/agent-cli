#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class RecentTranscriptionReaderTests: XCTestCase {
    func testDefaultLogURLExpandsConfiguredTranscriptionLogPath() {
        XCTAssertEqual(
            RecentTranscriptionReader.defaultLogURL.path,
            NSString(string: "~/.config/agent-cli/transcriptions.jsonl").expandingTildeInPath
        )
    }

    func testRecentTranscriptionsPreferProcessedTextNewestFirst() throws {
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
        defer { try? FileManager.default.removeItem(at: logURL) }

        let log = """
        {"timestamp":"2026-05-28T10:00:00+00:00","raw_output":"first raw","processed_output":null}
        {"timestamp":"2026-05-28T10:01:00+00:00","raw":"server raw","processed":"server processed"}
        not json
        {"timestamp":"2026-05-28T10:02:00+00:00","raw_output":"new raw","processed_output":"new processed"}
        {"timestamp":"2026-05-28T10:03:00+00:00","raw_output":"   ","processed_output":""}
        """
        try log.write(to: logURL, atomically: true, encoding: .utf8)

        let entries = RecentTranscriptionReader.recentTranscriptions(from: logURL, limit: 3)

        XCTAssertEqual(entries.map(\.text), ["new processed", "server processed", "first raw"])
    }

    func testRecentTranscriptionsReturnEmptyForMissingFile() {
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")

        XCTAssertEqual(RecentTranscriptionReader.recentTranscriptions(from: logURL), [])
    }
}
#endif
