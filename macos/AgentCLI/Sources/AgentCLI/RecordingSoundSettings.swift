import AppKit
import Foundation

enum RecordingSoundSettings {
    static let enabledKey = "recordingNotificationSoundsEnabled"

    static func isEnabled(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: enabledKey)
    }
}

enum RecordingSoundEvent: Hashable {
    case startedRecording
    case finishedRecording

    var soundName: NSSound.Name {
        switch self {
        case .startedRecording:
            return NSSound.Name("Frog")
        case .finishedRecording:
            return NSSound.Name("Funk")
        }
    }
}

protocol RecordingSoundPlaying: AnyObject {
    func play(_ event: RecordingSoundEvent)
}

final class NativeRecordingSoundPlayer: RecordingSoundPlaying {
    static let shared = NativeRecordingSoundPlayer()

    private var sounds: [RecordingSoundEvent: NSSound] = [:]

    private init() {}

    func play(_ event: RecordingSoundEvent) {
        guard let sound = sound(for: event) else { return }
        sound.stop()
        sound.currentTime = 0
        sound.play()
    }

    private func sound(for event: RecordingSoundEvent) -> NSSound? {
        if let sound = sounds[event] {
            return sound
        }
        guard let sound = NSSound(named: event.soundName) else {
            return nil
        }
        sounds[event] = sound
        return sound
    }
}
