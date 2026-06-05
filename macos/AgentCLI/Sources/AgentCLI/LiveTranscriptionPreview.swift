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
    private var readOffset: UInt64 = 0
    private var pendingLine = ""

    private init() {}

    func start(logURL: URL = defaultLogURL) {
        stop()
        self.logURL = logURL
        readOffset = 0
        pendingLine = ""
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
        readOffset = 0
        pendingLine = ""
        text = ""
    }

    func poll() {
        guard let logURL,
              let contents = readNewContents(from: logURL) else {
            return
        }

        let completeText = pendingLine + contents
        let lines = completeText.components(separatedBy: .newlines)
        pendingLine = completeText.hasSuffix("\n") || completeText.hasSuffix("\r") ? "" : (lines.last ?? "")

        guard let latestText = lines
            .compactMap(Self.previewText)
            .last else {
            return
        }

        if latestText != text {
            text = latestText
        }
    }

    private func readNewContents(from logURL: URL) -> String? {
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: logURL.path)
            let fileSize = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
            if readOffset > fileSize {
                readOffset = 0
                pendingLine = ""
            }
            guard fileSize > readOffset else { return nil }

            let handle = try FileHandle(forReadingFrom: logURL)
            defer {
                try? handle.close()
            }
            try handle.seek(toOffset: readOffset)
            guard let data = try handle.readToEnd(), !data.isEmpty else { return nil }
            readOffset += UInt64(data.count)
            return String(data: data, encoding: .utf8)
        } catch {
            return nil
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
