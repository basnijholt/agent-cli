import Foundation

struct MenuActivityTracker {
    private struct Activity {
        let title: String
        let startedAt: Date
        var action: String?
    }

    private var bootstrapActivity: Activity?
    private var recordingActivity: Activity?
    private var transcribingActivity: Activity?
    private var commandActivities: [String: Activity] = [:]
    private var commandActivityOrder: [String] = []

    mutating func beginBootstrap(title: String, at startedAt: Date = Date()) {
        bootstrapActivity = Activity(title: title, startedAt: startedAt)
    }

    mutating func finishBootstrap() {
        bootstrapActivity = nil
    }

    /// Names the action that is recording; a running recording keeps its start time.
    mutating func beginRecording(action: String, at startedAt: Date = Date()) {
        recordingActivity = Activity(
            title: "Recording",
            startedAt: recordingActivity?.startedAt ?? startedAt,
            action: action
        )
    }

    mutating func finishRecording() {
        recordingActivity = nil
    }

    mutating func beginTranscribing(action: String, at startedAt: Date = Date()) {
        transcribingActivity = Activity(
            title: "Transcribing",
            startedAt: transcribingActivity?.startedAt ?? startedAt,
            action: action
        )
    }

    mutating func finishTranscribing() {
        transcribingActivity = nil
    }

    mutating func beginCommand(identifier: String, title: String, at startedAt: Date = Date()) {
        if commandActivities[identifier] == nil {
            commandActivityOrder.append(identifier)
        }
        commandActivities[identifier] = Activity(title: title, startedAt: startedAt)
    }

    mutating func finishCommand(identifier: String) {
        commandActivities.removeValue(forKey: identifier)
        commandActivityOrder.removeAll { $0 == identifier }
    }

    func status(now: Date = Date(), fallback: MenuActivityStatus) -> MenuActivityStatus {
        guard let activity = currentActivity else { return fallback }
        let title = activity.action.map { "\($0) — \(activity.title)" } ?? activity.title
        return MenuActivityStatus.active(title: title, startedAt: activity.startedAt, now: now)
    }

    private var currentActivity: Activity? {
        bootstrapActivity
            ?? transcribingActivity
            ?? recordingActivity
            ?? commandActivityOrder.reversed().compactMap { commandActivities[$0] }.first
    }
}
