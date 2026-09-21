#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class TranscriptionResultTests: XCTestCase {
    func testEmptySuccessfulRecordingBecomesFailure() {
        for output in ["", " \n\t"] {
            let result = CommandResult(exitCode: 0, output: output).requiringTranscript()
            XCTAssertNotEqual(result.exitCode, 0)
            XCTAssertTrue(result.output.contains("No transcript"))
        }
    }

    func testTranscriptAndBackendFailureArePreserved() {
        let success = CommandResult(exitCode: 0, output: "Hello world").requiringTranscript()
        XCTAssertEqual(success.exitCode, 0)
        XCTAssertEqual(success.output, "Hello world")
        let failure = CommandResult(exitCode: 7, output: "Connection lost").requiringTranscript()
        XCTAssertEqual(failure.exitCode, 7)
        XCTAssertEqual(failure.output, "Connection lost")
    }
}
#endif
