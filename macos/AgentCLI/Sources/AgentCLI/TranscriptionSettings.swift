import Foundation

struct TranscriptionModelOption: Identifiable, Equatable {
    let id: String
    let title: String
}

enum TranscriptionBackend: String, CaseIterable, Identifiable {
    case whisper
    case nemo

    var id: String {
        rawValue
    }

    var title: String {
        switch self {
        case .whisper:
            return "Whisper"
        case .nemo:
            return "NeMo"
        }
    }

    var cliBackend: String {
        switch self {
        case .whisper:
            return "auto"
        case .nemo:
            return "nemo"
        }
    }

    var defaultModelName: String {
        modelOptions[0].id
    }

    var modelOptions: [TranscriptionModelOption] {
        switch self {
        case .whisper:
            return [
                TranscriptionModelOption(id: "large-v3", title: "Large v3"),
                TranscriptionModelOption(id: "large-v3-turbo", title: "Turbo"),
                TranscriptionModelOption(id: "small", title: "Small"),
            ]
        case .nemo:
            return [
                TranscriptionModelOption(id: "parakeet-unified-en-0.6b", title: "Parakeet Unified 0.6B"),
                TranscriptionModelOption(id: "parakeet-tdt-0.6b-v3", title: "Parakeet TDT 0.6B v3"),
                TranscriptionModelOption(id: "parakeet-tdt_ctc-110m", title: "Parakeet TDT CTC 110M"),
            ]
        }
    }

    func modelOption(named modelName: String) -> TranscriptionModelOption? {
        modelOptions.first { $0.id == modelName }
    }
}

enum TranscriptionSettings {
    static let transcriptionExtraInstructionsKey = "transcriptionExtraInstructions"
    static let transcriptionBackendKey = "transcriptionBackend"
    static let transcriptionModelKey = "transcriptionModel"
    static let transcriptionModelTTLSecondsKey = "transcriptionModelTTLSeconds"
    static let defaultModelTTLSeconds = 300

    static var extraInstructions: String {
        UserDefaults.standard.string(forKey: transcriptionExtraInstructionsKey) ?? ""
    }

    static func selectedBackend(userDefaults: UserDefaults = .standard) -> TranscriptionBackend {
        let rawValue = userDefaults.string(forKey: transcriptionBackendKey) ?? TranscriptionBackend.whisper.rawValue
        return TranscriptionBackend(rawValue: rawValue) ?? .whisper
    }

    static func selectedModelName(userDefaults: UserDefaults = .standard) -> String {
        let backend = selectedBackend(userDefaults: userDefaults)
        let storedModelName = userDefaults.string(forKey: transcriptionModelKey) ?? ""
        return backend.modelOption(named: storedModelName)?.id ?? backend.defaultModelName
    }

    static func selectedModelTTLSeconds(userDefaults: UserDefaults = .standard) -> Int {
        guard let storedValue = userDefaults.object(forKey: transcriptionModelTTLSecondsKey) as? NSNumber else {
            return defaultModelTTLSeconds
        }
        return max(0, storedValue.intValue)
    }

    static func whisperDaemonInstallArguments(userDefaults: UserDefaults = .standard) -> [String] {
        let backend = selectedBackend(userDefaults: userDefaults)
        return [
            "daemon",
            "install",
            "whisper",
            "-y",
            "--",
            "--backend",
            backend.cliBackend,
            "--model",
            selectedModelName(userDefaults: userDefaults),
            "--ttl",
            "\(selectedModelTTLSeconds(userDefaults: userDefaults))",
        ]
    }
}
