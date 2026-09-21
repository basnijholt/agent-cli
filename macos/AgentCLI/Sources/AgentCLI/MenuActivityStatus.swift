import Foundation

struct MenuActivityStatus: Equatable {
    let message: String
    let isActive: Bool

    static func active(title: String, startedAt: Date, now: Date) -> MenuActivityStatus {
        let elapsedSeconds = max(0, Int(now.timeIntervalSince(startedAt)))
        return active(title: title, animationTick: elapsedSeconds % spinnerFrames.count, elapsedSeconds: elapsedSeconds)
    }

    static func active(title: String, animationTick: Int, elapsedSeconds: Int) -> MenuActivityStatus {
        let spinner = spinnerFrames[animationTick % spinnerFrames.count]
        let minutes = elapsedSeconds / 60
        let seconds = elapsedSeconds % 60
        let elapsedTime = String(format: "%02d:%02d", minutes, seconds)
        return MenuActivityStatus(message: "\(title) \(spinner) (\(elapsedTime))", isActive: true)
    }

    static func completed(title: String) -> MenuActivityStatus {
        MenuActivityStatus(message: "\(title) ✓", isActive: false)
    }

    static func inactive(message: String) -> MenuActivityStatus {
        MenuActivityStatus(message: message, isActive: false)
    }

    private static let spinnerFrames = ["◐", "◓", "◑", "◒"]
}
