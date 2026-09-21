#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class TranscriptionResultTests: XCTestCase {
    func testShutdownWarningsAreNotPartOfTranscript() {
        let result = runShell("""
        printf '%s\\n' 'Timed out after 0.50s waiting for audio stream.abort(); continuing.' >&2
        printf '%s\\n' 'Timed out after 0.50s waiting for audio stream.close(); continuing.' >&2
        printf '%s\\n' 'CI is failing for the proxy. Fix it.'
        """).requiringTranscript()
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(result.output, "CI is failing for the proxy. Fix it.")
        XCTAssertEqual(result.pasteText, "CI is failing for the proxy. Fix it.")
    }

    func testWarningsAloneDoNotCountAsTranscript() {
        let result = runShell("printf 'Audio shutdown warning\\n' >&2").requiringTranscript()
        XCTAssertNotEqual(result.exitCode, 0)
        XCTAssertTrue(result.output.contains("No transcript"))
        XCTAssertEqual(result.pasteText, "Audio shutdown warning")
    }

    func testFailureKeepsStderrDiagnostics() {
        let result = runShell("printf 'ASR connection failed\\n' >&2; exit 7").requiringTranscript()
        XCTAssertEqual(result.exitCode, 7)
        XCTAssertTrue(result.output.contains("ASR connection failed"))
        XCTAssertEqual(result.pasteText, "ASR connection failed")
    }

    func testStdoutWinsOverStderrEvenWhenCommandFails() {
        let result = runShell("printf 'Recognized speech\\n'; printf 'Cleanup failed\\n' >&2; exit 7")
            .requiringTranscript()
        XCTAssertEqual(result.exitCode, 7)
        XCTAssertEqual(result.pasteText, "Recognized speech")
    }

    func testSilentProcessDoesNotPasteInventedTranscript() {
        let result = runShell("exit 0").requiringTranscript()
        XCTAssertNotEqual(result.exitCode, 0)
        XCTAssertNil(result.pasteText)
    }

    func testLargeDiagnosticsDoNotBlockTranscriptCapture() {
        let result = runShell("dd if=/dev/zero bs=65536 count=4 >&2 2>/dev/null; printf 'Hello\\n'")
            .requiringTranscript()
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(result.output, "Hello")
    }

    private func runShell(_ command: String) -> CommandResult {
        AgentRuntime.runProcess(
            executableURL: URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", command],
            environment: ["PATH": "/usr/bin:/bin"]
        )
    }

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
