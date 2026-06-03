import Combine
import Foundation

final class LiveTranscriptionPreview: ObservableObject {
    static let shared = LiveTranscriptionPreview()
    static let defaultLogPath = "~/.config/agent-cli/live-preview.jsonl"
    static var defaultLogURL: URL {
        URL(fileURLWithPath: NSString(string: defaultLogPath).expandingTildeInPath)
    }

    @Published private(set) var text = ""

    private static let pollInterval: TimeInterval = 0.25
    private var timer: Timer?
    private var logURL: URL?

    private init() {}

    func start(logURL: URL = defaultLogURL) {
        stop()
        self.logURL = logURL
        text = ""
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? "".write(to: logURL, atomically: true, encoding: .utf8)
        poll()

        let timer = Timer(timeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.poll()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        logURL = nil
        text = ""
    }

    func poll() {
        guard let logURL,
              let contents = try? String(contentsOf: logURL, encoding: .utf8) else {
            return
        }

        let latestText = contents
            .components(separatedBy: .newlines)
            .compactMap(Self.previewText)
            .last ?? ""

        if latestText != text {
            text = latestText
        }
    }

    static func previewText(from line: String) -> String? {
        let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedLine.isEmpty,
              let data = trimmedLine.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String,
              type == "partial" || type == "final",
              let text = object["text"] as? String else {
            return nil
        }

        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedText.isEmpty ? nil : trimmedText
    }
}
