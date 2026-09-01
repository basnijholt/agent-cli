#if canImport(XCTest)
import XCTest
@testable import AgentCLI

final class LiveTranscriptionPreviewTests: XCTestCase {
    func testPreviewTextParsesPartialEvents() {
        let line = #"{"type":"partial","text":" hello world ","revision":1}"#

        XCTAssertEqual(LiveTranscriptionPreview.previewText(from: line), "hello world")
    }

    func testPreviewTextParsesFinalEvents() {
        let line = #"{"type":"final","text":"Final transcript","revision":2}"#

        XCTAssertEqual(LiveTranscriptionPreview.previewText(from: line), "Final transcript")
    }

    func testPreviewTextIgnoresMalformedAndEmptyEvents() {
        XCTAssertNil(LiveTranscriptionPreview.previewText(from: ""))
        XCTAssertNil(LiveTranscriptionPreview.previewText(from: #"{"type":"debug","text":"no"}"#))
        XCTAssertNil(LiveTranscriptionPreview.previewText(from: #"{"type":"partial","text":"  "}"#))
    }
}
#endif
