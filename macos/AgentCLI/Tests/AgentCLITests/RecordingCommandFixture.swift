#if canImport(XCTest)
import Foundation
import XCTest
@testable import AgentCLI

/// Replace only the CLI process and paste boundaries; shortcut, runner and overlay state stay real.
/// Like `transcribe --toggle`, each call stops the running recording, or starts one that runs until stopped.
final class RecordingCommandFixture: TranscriptPasting {
    let started = XCTestExpectation(description: "recording process started")
    let stopped = XCTestExpectation(description: "recording process stopped")
    private let condition = NSCondition()
    private var calls = 0
    private var failsNextStart: Bool
    private var recording = false
    private var finished = false
    private var pasted: [String] = []

    init(failsFirstStart: Bool = false) {
        failsNextStart = failsFirstStart
        // Extra starts or stops must fail the count assertions, not crash the test run.
        started.assertForOverFulfill = false
        stopped.assertForOverFulfill = false
    }

    var commandCount: Int {
        condition.lock()
        defer { condition.unlock() }
        return calls
    }

    var pastedTranscripts: [String] {
        condition.lock()
        defer { condition.unlock() }
        return pasted
    }

    func run(_ arguments: [String]) -> CommandResult {
        XCTAssertEqual(arguments.first, "transcribe")
        condition.lock()
        calls += 1
        if recording {
            recording = false
            condition.broadcast()
            condition.unlock()
            stopped.fulfill()
            return CommandResult(exitCode: 0, output: "")
        }
        if failsNextStart {
            failsNextStart = false
            condition.unlock()
            return CommandResult(exitCode: 1, output: "", standardOutput: "", standardError: "")
        }
        recording = true
        condition.unlock()
        started.fulfill()
        condition.lock()
        while recording && !finished { condition.wait() }
        condition.unlock()
        return CommandResult(exitCode: 0, output: "Fixture transcript")
    }

    func pasteTranscriptIntoFocusedField(
        _ transcript: String,
        target: FocusedTextTarget?,
        onStatus: @escaping @MainActor (String) -> Void
    ) {
        condition.lock()
        pasted.append(transcript)
        condition.unlock()
    }

    func finish() {
        condition.lock()
        finished = true
        condition.broadcast()
        condition.unlock()
    }
}
#endif
