import Foundation

struct MenuActivityTracker {
    private struct Activity {
        let title: String
        let startedAt: Date
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

    mutating func beginRecording(at startedAt: Date = Date()) {
        guard recordingActivity == nil else { return }
        recordingActivity = Activity(title: "Recording", startedAt: startedAt)
    }

    mutating func finishRecording() {
        recordingActivity = nil
    }

    mutating func beginTranscribing(at startedAt: Date = Date()) {
        guard transcribingActivity == nil else { return }
        transcribingActivity = Activity(title: "Transcribing", startedAt: startedAt)
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
        return MenuActivityStatus.active(title: activity.title, startedAt: activity.startedAt, now: now)
    }

    private var currentActivity: Activity? {
        bootstrapActivity
            ?? transcribingActivity
            ?? recordingActivity
            ?? commandActivityOrder.reversed().compactMap { commandActivities[$0] }.first
    }
}
