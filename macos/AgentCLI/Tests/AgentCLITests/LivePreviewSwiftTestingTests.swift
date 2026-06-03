#if canImport(Testing)
import Foundation
import Testing
@testable import AgentCLI

@Test
func toggleTranscriptionEnablesLivePreviewArguments() {
    #expect(AgentCommand.toggleTranscription.arguments == [
        "transcribe",
        "--toggle",
        "--quiet",
        "--transcription-log",
        "~/.config/agent-cli/transcriptions.jsonl",
        "--live-preview-log",
        "~/.config/agent-cli/live-preview.jsonl",
        "--live-preview-interval",
        "1",
        "--live-preview-window",
        "10",
    ])
}

@Test
func livePreviewParsesLatestJsonlEvent() throws {
    let preview = LiveTranscriptionPreview.shared
    let logURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("agent-cli-live-preview-\(UUID().uuidString).jsonl")
    defer {
        preview.stop()
        try? FileManager.default.removeItem(at: logURL)
    }

    preview.start(logURL: logURL)
    try [
        #"{"type":"partial","text":"first guess","revision":1}"#,
        #"{"type":"partial","text":" corrected guess ","revision":2}"#,
    ].joined(separator: "\n").write(to: logURL, atomically: true, encoding: .utf8)

    preview.poll()

    #expect(preview.text == "corrected guess")
}

#endif
