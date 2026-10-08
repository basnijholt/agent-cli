import Foundation

struct MenuActivityTracker {
    private struct Activity {
        let title: String
        let startedAt: Date
        var action: String?
    }

    /// Activities keyed by command; the most recently started one is shown.
    private struct ActivityGroup {
        private var activities: [String: Activity] = [:]
        private var order: [String] = []

        var latest: Activity? {
            order.last.flatMap { activities[$0] }
        }

        func startedAt(_ identifier: String) -> Date? {
            activities[identifier]?.startedAt
        }

        mutating func begin(_ identifier: String, _ activity: Activity) {
            if activities[identifier] == nil {
                order.append(identifier)
            }
            activities[identifier] = activity
        }

        mutating func finish(_ identifier: String) {
            activities.removeValue(forKey: identifier)
            order.removeAll { $0 == identifier }
        }
    }

    private var bootstrapActivity: Activity?
    private var recordingActivities = ActivityGroup()
    private var transcribingActivities = ActivityGroup()
    private var commandActivities = ActivityGroup()

    mutating func beginBootstrap(title: String, at startedAt: Date = Date()) {
        bootstrapActivity = Activity(title: title, startedAt: startedAt)
    }

    mutating func finishBootstrap() {
        bootstrapActivity = nil
    }

    /// Names the action that is recording; a running recording keeps its start time.
    mutating func beginRecording(identifier: String, action: String, at startedAt: Date = Date()) {
        recordingActivities.begin(identifier, Activity(
            title: "Recording",
            startedAt: recordingActivities.startedAt(identifier) ?? startedAt,
            action: action
        ))
    }

    mutating func finishRecording(identifier: String) {
        recordingActivities.finish(identifier)
    }

    mutating func beginTranscribing(identifier: String, action: String, at startedAt: Date = Date()) {
        transcribingActivities.begin(identifier, Activity(
            title: "Transcribing",
            startedAt: transcribingActivities.startedAt(identifier) ?? startedAt,
            action: action
        ))
    }

    mutating func finishTranscribing(identifier: String) {
        transcribingActivities.finish(identifier)
    }

    mutating func beginCommand(identifier: String, title: String, at startedAt: Date = Date()) {
        commandActivities.begin(identifier, Activity(title: title, startedAt: startedAt))
    }

    mutating func finishCommand(identifier: String) {
        commandActivities.finish(identifier)
    }

    func status(now: Date = Date(), fallback: MenuActivityStatus) -> MenuActivityStatus {
        guard let activity = currentActivity else { return fallback }
        let title = activity.action.map { "\($0) — \(activity.title)" } ?? activity.title
        return MenuActivityStatus.active(title: title, startedAt: activity.startedAt, now: now)
    }

    private var currentActivity: Activity? {
        bootstrapActivity
            ?? transcribingActivities.latest
            ?? recordingActivities.latest
            ?? commandActivities.latest
    }
}
