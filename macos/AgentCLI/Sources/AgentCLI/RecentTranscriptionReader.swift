import Foundation

struct RecentTranscription: Equatable, Identifiable {
    let id: String
    let timestamp: Date?
    let text: String

    var menuTitle: String {
        let snippet = Self.snippet(from: text, maxLength: 72)
        guard let timestamp else { return snippet }
        return "\(Self.menuDateFormatter.string(from: timestamp)) - \(snippet)"
    }

    private static let menuDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d HH:mm"
        return formatter
    }()

    private static func snippet(from text: String, maxLength: Int) -> String {
        let singleLine = text
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard singleLine.count > maxLength else { return singleLine }
        return String(singleLine.prefix(maxLength)).trimmingCharacters(in: .whitespacesAndNewlines) + "..."
    }
}

enum RecentTranscriptionReader {
    static let defaultLimit = 20
    static let defaultLogPath = "~/.config/agent-cli/transcriptions.jsonl"

    static func recentTranscriptions(limit: Int = defaultLimit) -> [RecentTranscription] {
        recentTranscriptions(from: defaultLogURL(), limit: limit)
    }

    static func recentTranscriptions(from logURL: URL, limit: Int = defaultLimit) -> [RecentTranscription] {
        guard limit > 0,
              let contents = try? String(contentsOf: logURL, encoding: .utf8) else {
            return []
        }

        var entries: [RecentTranscription] = []
        let lines = contents.components(separatedBy: .newlines)

        for (lineIndex, line) in lines.enumerated().reversed() {
            guard entries.count < limit,
                  let entry = parseLine(line, lineIndex: lineIndex) else {
                continue
            }
            entries.append(entry)
        }

        return entries
    }

    private static func defaultLogURL() -> URL {
        URL(fileURLWithPath: NSString(string: defaultLogPath).expandingTildeInPath)
    }

    private static func parseLine(_ line: String, lineIndex: Int) -> RecentTranscription? {
        let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedLine.isEmpty,
              let data = trimmedLine.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        guard let text = firstNonEmptyString(
            object["processed_output"],
            object["processed"],
            object["raw_output"],
            object["raw"]
        ) else {
            return nil
        }

        let timestampText = object["timestamp"] as? String
        return RecentTranscription(
            id: "\(lineIndex)-\(timestampText ?? "")",
            timestamp: timestampText.flatMap(parseTimestamp),
            text: text
        )
    }

    private static func firstNonEmptyString(_ values: Any?...) -> String? {
        for value in values {
            guard let string = value as? String else { continue }
            let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed
            }
        }
        return nil
    }

    private static func parseTimestamp(_ text: String) -> Date? {
        if let date = iso8601WithFractionalSeconds.date(from: text) {
            return date
        }
        return iso8601.date(from: text)
    }

    private static let iso8601WithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
