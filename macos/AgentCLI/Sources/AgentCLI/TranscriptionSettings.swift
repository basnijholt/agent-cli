import Foundation

enum TranscriptionSettings {
    static let transcriptionExtraInstructionsKey = "transcriptionExtraInstructions"

    static var extraInstructions: String {
        UserDefaults.standard.string(forKey: transcriptionExtraInstructionsKey) ?? ""
    }
}
