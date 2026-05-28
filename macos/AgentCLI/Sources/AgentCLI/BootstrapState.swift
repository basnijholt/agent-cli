import Foundation

enum AgentBootstrapRequirement: Equatable {
    case cliRuntime
    case transcription
    case transcriptionModel
}

enum BootstrapPhase: Equatable {
    case idle
    case checkingRuntime
    case installingRuntime
    case installingVoiceService
    case waitingForVoiceService
    case warmingWhisperModel
    case failed

    var isPreparing: Bool {
        switch self {
        case .idle, .failed:
            return false
        case .checkingRuntime, .installingRuntime, .installingVoiceService, .waitingForVoiceService, .warmingWhisperModel:
            return true
        }
    }

    var statusMessage: String {
        switch self {
        case .idle:
            return "Ready"
        case .checkingRuntime:
            return "Checking CLI runtime..."
        case .installingRuntime:
            return "Installing CLI runtime..."
        case .installingVoiceService:
            return "Installing voice service..."
        case .waitingForVoiceService:
            return "Waiting for voice service..."
        case .warmingWhisperModel:
            return "Warming Whisper model..."
        case .failed:
            return "Voice service warm-up failed"
        }
    }

    func statusMessage(animationTick: Int, elapsedSeconds: Int) -> String {
        switch self {
        case .waitingForVoiceService:
            let periodCount = (animationTick % 3) + 1
            return "Waiting for voice service\(String(repeating: ".", count: periodCount)) (\(elapsedSeconds)s)"
        case .idle, .checkingRuntime, .installingRuntime, .installingVoiceService, .warmingWhisperModel, .failed:
            return statusMessage
        }
    }
}

typealias AgentBootstrapProgress = (BootstrapPhase) -> Void
typealias AgentBootstrap = (AgentBootstrapRequirement, Bool, @escaping AgentBootstrapProgress) -> CommandResult
