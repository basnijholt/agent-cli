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
}
#endif
