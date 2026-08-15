import AVFoundation

enum MicrophonePermissionStatus {
    case authorized
    case denied
    case notDetermined
}

struct MicrophonePermissionPresentation {
    let status: MicrophonePermissionStatus

    var canRecord: Bool {
        status == .authorized
    }

    var statusMessage: String? {
        switch status {
        case .authorized:
            return nil
        case .denied:
            return "Allow Microphone permission for Agent CLI in System Settings."
        case .notDetermined:
            return "Approve Microphone permission for Agent CLI, then try recording again."
        }
    }
}

protocol MicrophonePermissionControlling {
    func currentStatus() -> MicrophonePermissionStatus
    func requestAccessIfNeeded(completion: @escaping (Bool) -> Void)
}

final class MicrophonePermissionController: MicrophonePermissionControlling {
    static let shared = MicrophonePermissionController()

    private init() {}

    func currentStatus() -> MicrophonePermissionStatus {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return .authorized
        case .notDetermined:
            return .notDetermined
        case .denied, .restricted:
            return .denied
        @unknown default:
            return .denied
        }
    }

    func requestAccessIfNeeded(completion: @escaping (Bool) -> Void) {
        guard currentStatus() == .notDetermined else {
            completion(currentStatus() == .authorized)
            return
        }
        AVCaptureDevice.requestAccess(for: .audio, completionHandler: completion)
    }
}
