#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class AgentCommandTests: XCTestCase {
    func testToggleTranscriptionUsesTypedArgumentsAndTranscriptionBootstrap() {
        XCTAssertEqual(AgentCommand.toggleTranscription.arguments, ["transcribe", "--toggle", "--quiet"])
        XCTAssertEqual(AgentCommand.toggleTranscription.bootstrapRequirement, .transcription)
    }

    func testAutocorrectOnlyRequiresCliRuntime() {
        XCTAssertEqual(AgentCommand.autocorrect.arguments, ["autocorrect", "--quiet"])
        XCTAssertEqual(AgentCommand.autocorrect.bootstrapRequirement, .cliRuntime)
    }

    @MainActor
    func testStartupWarmUpBootstrapsTranscriptionOnce() {
        let recorder = BootstrapRecorder()
        let runner = AgentCommandRunner(bootstrap: recorder.bootstrap)

        runner.warmUpTranscription()
        runner.warmUpTranscription()

        wait(for: [recorder.expectation], timeout: 2)

        XCTAssertEqual(recorder.calls, [.init(requirement: .transcription, force: false)])
    }
}

private struct BootstrapCall: Equatable {
    let requirement: AgentBootstrapRequirement
    let force: Bool
}

private final class BootstrapRecorder {
    let expectation = XCTestExpectation(description: "warm-up bootstrap called")
    private let lock = NSLock()
    private var storedCalls: [BootstrapCall] = []

    var calls: [BootstrapCall] {
        lock.withLock { storedCalls }
    }

    func bootstrap(requirement: AgentBootstrapRequirement, force: Bool) -> CommandResult {
        lock.withLock {
            storedCalls.append(.init(requirement: requirement, force: force))
        }
        expectation.fulfill()
        return CommandResult(exitCode: 0, output: "")
    }
}
#endif
