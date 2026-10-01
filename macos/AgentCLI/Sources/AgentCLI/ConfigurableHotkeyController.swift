import ApplicationServices
import Carbon.HIToolbox
import Foundation
import KeyboardShortcuts

enum HoldToTranscribeStopDecision: Equatable {
    case none
    case deferUntilStartCompletes
    case stopNow
}

enum HoldToTranscribeStartDecision: Equatable {
    case none
    case stopNow
    case stopExistingFunctionRecording
    case promoteToToggle
    case toggleNormally
}

struct HoldToTranscribeKeyState {
    private enum State {
        case idle
        case startPending(releaseRequested: Bool, toggleRequested: Bool, stopExistingOnFailure: Bool)
        case recording
    }

    private var state: State = .idle

    mutating func requestStart() -> Bool {
        guard case .idle = state else { return false }
        state = .startPending(releaseRequested: false, toggleRequested: false, stopExistingOnFailure: false)
        return true
    }

    mutating func releaseKey(stopExistingFunctionRecordingIfIdle: Bool = false) -> HoldToTranscribeStopDecision {
        switch state {
        case .idle:
            return .none
        case let .startPending(_, toggleRequested, stopExistingOnFailure):
            state = .startPending(
                releaseRequested: true,
                toggleRequested: toggleRequested,
                stopExistingOnFailure: stopExistingOnFailure || stopExistingFunctionRecordingIfIdle
            )
            return .deferUntilStartCompletes
        case .recording:
            state = .idle
            return .stopNow
        }
    }

    mutating func requestToggle() -> HoldToTranscribeStartDecision {
        switch state {
        case .idle:
            return .toggleNormally
        case let .startPending(releaseRequested, _, stopExistingOnFailure):
            state = .startPending(
                releaseRequested: releaseRequested,
                toggleRequested: true,
                stopExistingOnFailure: stopExistingOnFailure
            )
            return .none
        case .recording:
            state = .idle
            return .promoteToToggle
        }
    }

    mutating func completeStart(started: Bool) -> HoldToTranscribeStartDecision {
        guard case let .startPending(releaseRequested, toggleRequested, stopExistingOnFailure) = state else { return .none }
        if toggleRequested {
            state = .idle
            return started ? .promoteToToggle : .toggleNormally
        }
        guard started else {
            state = .idle
            return stopExistingOnFailure ? .stopExistingFunctionRecording : .none
        }

        if releaseRequested {
            state = .idle
            return .stopNow
        }

        state = .recording
        return .none
    }

    mutating func reset() {
        state = .idle
    }
}

final class ConfigurableHotkeyController {
    static let shared = ConfigurableHotkeyController()

    private var registered = false
    private weak var runner: AgentCommandRunner?
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var functionKeyIsDown = false
    private var suppressNextFunctionKeyRelease = false
    private var holdToTranscribeKeyState = HoldToTranscribeKeyState()
    private var pendingHoldToTranscribeWorkItem: DispatchWorkItem?
    private var accessibilityRetryWorkItem: DispatchWorkItem?
    private let holdToTranscribeDelay: TimeInterval = 0.16
    private let accessibilityRetryInterval: TimeInterval = 1
    private let accessibilityRetryTimeout: TimeInterval = 120

    init(runner: AgentCommandRunner? = nil) {
        self.runner = runner
    }

    func registerDefaultHotkeys(runner: AgentCommandRunner) {
        guard !registered else { return }

        self.runner = runner
        registerStandardTranscriptionHotkeys(runner: runner)
        registerFunctionAwareTranscriptionHotkeys(runner: runner)

        KeyboardShortcuts.onKeyUp(for: .autocorrect) {
            guard !ShortcutRecordingState.shared.isRecording else { return }
            Task { @MainActor in runner.run(.autocorrect) }
        }
        KeyboardShortcuts.onKeyUp(for: .voiceEdit) {
            guard !ShortcutRecordingState.shared.isRecording else { return }
            Task { @MainActor in runner.run(.voiceEdit) }
        }

        registered = true
    }

    private func registerStandardTranscriptionHotkeys(runner: AgentCommandRunner) {
        KeyboardShortcuts.onKeyUp(for: .toggleTranscription) {
            guard !ShortcutRecordingState.shared.isRecording,
                  let shortcut = KeyboardShortcuts.getShortcut(for: .toggleTranscription),
                  !self.usesFunctionShortcut(shortcut) else {
                return
            }
            Task { @MainActor in runner.run(.toggleTranscription) }
        }
        KeyboardShortcuts.onKeyDown(for: .holdToTranscribe) {
            guard !ShortcutRecordingState.shared.isRecording,
                  let shortcut = KeyboardShortcuts.getShortcut(for: .holdToTranscribe),
                  !self.usesFunctionShortcut(shortcut) else {
                return
            }
            self.requestHoldToTranscribeStart(preferredRunner: runner)
        }
        KeyboardShortcuts.onKeyUp(for: .holdToTranscribe) {
            guard !ShortcutRecordingState.shared.isRecording,
                  let shortcut = KeyboardShortcuts.getShortcut(for: .holdToTranscribe),
                  !self.usesFunctionShortcut(shortcut) else {
                return
            }
            self.releaseHoldToTranscribeKey()
        }
    }

    private func registerFunctionAwareTranscriptionHotkeys(runner: AgentCommandRunner) {
        cancelAccessibilityRetry()
        guard eventTap == nil else { return }
        guard AXIsProcessTrusted() else {
            scheduleAccessibilityRetry(runner: runner, deadline: Date().addingTimeInterval(accessibilityRetryTimeout))
            return
        }

        let eventMask =
            CGEventMask(1 << CGEventType.keyDown.rawValue) |
            CGEventMask(1 << CGEventType.keyUp.rawValue) |
            CGEventMask(1 << CGEventType.flagsChanged.rawValue)

        let userInfo = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: eventMask,
            callback: { _, type, event, userInfo in
                guard let userInfo else {
                    return Unmanaged.passUnretained(event)
                }

                let controller = Unmanaged<ConfigurableHotkeyController>
                    .fromOpaque(userInfo)
                    .takeUnretainedValue()
                return controller.handleFunctionAwareHotkey(type: type, event: event)
            },
            userInfo: userInfo
        ) else {
            Task { @MainActor in
                runner.statusMessage = "Fn shortcuts unavailable. Check Permissions in Settings, then quit and reopen Agent CLI."
            }
            return
        }

        eventTap = tap
        runLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        if let runLoopSource {
            CFRunLoopAddSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }
        CGEvent.tapEnable(tap: tap, enable: true)
    }

    func suspendFunctionAwareHotkeysForAccessibilityReset() {
        cancelPendingHoldToTranscribe()
        cancelAccessibilityRetry()

        if let tap = eventTap {
            CGEvent.tapEnable(tap: tap, enable: false)
            CFMachPortInvalidate(tap)
        }
        if let runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }

        eventTap = nil
        runLoopSource = nil
        functionKeyIsDown = false
        suppressNextFunctionKeyRelease = false
        holdToTranscribeKeyState.reset()
    }

    func resumeFunctionAwareHotkeysAfterAccessibilityReset(runner: AgentCommandRunner) {
        guard registered, eventTap == nil else { return }
        self.runner = runner
        registerFunctionAwareTranscriptionHotkeys(runner: runner)
    }

    func retryFunctionAwareHotkeysIfTrusted(runner: AgentCommandRunner) {
        guard registered, eventTap == nil, AXIsProcessTrusted() else { return }
        self.runner = runner
        registerFunctionAwareTranscriptionHotkeys(runner: runner)
    }

    func handleFunctionAwareHotkey(type: CGEventType, event: CGEvent) -> Unmanaged<CGEvent>? {
        switch type {
        case .tapDisabledByTimeout, .tapDisabledByUserInput:
            if let eventTap {
                CGEvent.tapEnable(tap: eventTap, enable: true)
            }
            return Unmanaged.passUnretained(event)
        default:
            break
        }

        if ShortcutRecordingState.shared.isRecording {
            cancelPendingHoldToTranscribe()
            return Unmanaged.passUnretained(event)
        }

        if handleToggleTranscriptionShortcut(type: type, event: event) {
            return nil
        }
        if handleHoldToTranscribeShortcut(type: type, event: event) {
            return nil
        }
        if handleFunctionKeyChanged(type: type, event: event) {
            return nil
        }

        return Unmanaged.passUnretained(event)
    }

    private func handleToggleTranscriptionShortcut(type: CGEventType, event: CGEvent) -> Bool {
        guard let shortcut = KeyboardShortcuts.getShortcut(for: .toggleTranscription),
              usesFunctionShortcut(shortcut),
              shortcutMatches(type: type, event: event, shortcut: shortcut) else {
            return false
        }

        if type == .keyDown {
            cancelPendingHoldToTranscribe()

            if !isAutorepeat(event) {
                suppressNextFunctionKeyRelease = true
                let action = holdToTranscribeKeyState.requestToggle()
                Task { @MainActor in
                    guard let runner = self.runner else { return }
                    self.applyHoldStartDecision(action, runner: runner)
                }
            }
        }

        return true
    }

    private func handleHoldToTranscribeShortcut(type: CGEventType, event: CGEvent) -> Bool {
        guard let shortcut = KeyboardShortcuts.getShortcut(for: .holdToTranscribe) else {
            return false
        }
        guard !isBareFunctionShortcut(shortcut),
              usesFunctionShortcut(shortcut),
              shortcutMatches(type: type, event: event, shortcut: shortcut) else {
            return false
        }

        if type == .keyDown {
            if !isAutorepeat(event) {
                requestHoldToTranscribeStart()
            }
            return true
        }

        if type == .keyUp {
            releaseHoldToTranscribeKey()
            return true
        }

        return false
    }

    private func handleFunctionKeyChanged(type: CGEventType, event: CGEvent) -> Bool {
        guard type == .flagsChanged,
              let shortcut = KeyboardShortcuts.getShortcut(for: .holdToTranscribe),
              isBareFunctionShortcut(shortcut) else {
            return false
        }

        let isFunctionDown = event.flags.contains(CGEventFlags.maskSecondaryFn)
        if isFunctionDown {
            guard !functionKeyIsDown else { return false }
            functionKeyIsDown = true
            schedulePendingHoldToTranscribe()
            return true
        }

        guard functionKeyIsDown else { return false }
        functionKeyIsDown = false
        cancelPendingHoldToTranscribe()
        guard !suppressNextFunctionKeyRelease else {
            suppressNextFunctionKeyRelease = false
            return true
        }

        releaseHoldToTranscribeKey(stopExistingFunctionRecordingIfIdle: true)

        return true
    }

    private func schedulePendingHoldToTranscribe() {
        cancelPendingHoldToTranscribe()

        var workItem: DispatchWorkItem?
        workItem = DispatchWorkItem { [weak self] in
            guard let self,
                  workItem?.isCancelled == false else {
                return
            }

            self.pendingHoldToTranscribeWorkItem = nil
            // A following Space may still turn this Fn press into a toggle chord.
            // Stop an existing toggle recording only on bare Fn release.
            self.requestHoldToTranscribeStart()
        }

        pendingHoldToTranscribeWorkItem = workItem
        if let workItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + holdToTranscribeDelay, execute: workItem)
        }
    }

    private func cancelPendingHoldToTranscribe() {
        pendingHoldToTranscribeWorkItem?.cancel()
        pendingHoldToTranscribeWorkItem = nil
    }

    private func scheduleAccessibilityRetry(runner: AgentCommandRunner, deadline: Date) {
        guard Date() < deadline else { return }

        var workItem: DispatchWorkItem?
        workItem = DispatchWorkItem { [weak self] in
            guard let self,
                  workItem?.isCancelled == false else {
                return
            }

            self.accessibilityRetryWorkItem = nil
            guard self.eventTap == nil else { return }

            guard AXIsProcessTrusted() else {
                self.scheduleAccessibilityRetry(runner: runner, deadline: deadline)
                return
            }

            self.runner = runner
            self.registerFunctionAwareTranscriptionHotkeys(runner: runner)
            if self.eventTap != nil {
                Task { @MainActor in
                    runner.statusMessage = "Accessibility permission enabled"
                }
            }
        }

        accessibilityRetryWorkItem = workItem
        if let workItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + accessibilityRetryInterval, execute: workItem)
        }
    }

    private func cancelAccessibilityRetry() {
        accessibilityRetryWorkItem?.cancel()
        accessibilityRetryWorkItem = nil
    }

    private func requestHoldToTranscribeStart(
        preferredRunner: AgentCommandRunner? = nil
    ) {
        guard holdToTranscribeKeyState.requestStart() else { return }
        Task { @MainActor in
            guard let runner = preferredRunner ?? self.runner else {
                _ = self.holdToTranscribeKeyState.completeStart(started: false)
                return
            }
            self.finishHoldToTranscribeStart(runner: runner)
        }
    }

    @MainActor
    private func finishHoldToTranscribeStart(runner: AgentCommandRunner) {
        let started = runner.beginHoldToTranscribe()
        let action = holdToTranscribeKeyState.completeStart(started: started)
        applyHoldStartDecision(action, runner: runner)
    }

    @MainActor
    private func applyHoldStartDecision(_ action: HoldToTranscribeStartDecision, runner: AgentCommandRunner) {
        switch action {
        case .none:
            break
        case .stopNow:
            runner.endHoldToTranscribe()
        case .stopExistingFunctionRecording:
            _ = runner.stopTranscriptionFromFunctionKeyIfNeeded()
        case .promoteToToggle:
            runner.latchHoldToTranscribe()
        case .toggleNormally:
            runner.run(.toggleTranscription)
        }
    }

    private func releaseHoldToTranscribeKey(stopExistingFunctionRecordingIfIdle: Bool = false) {
        switch holdToTranscribeKeyState.releaseKey(
            stopExistingFunctionRecordingIfIdle: stopExistingFunctionRecordingIfIdle
        ) {
        case .stopNow:
            stopHoldToTranscribe()
        case .none:
            if stopExistingFunctionRecordingIfIdle {
                Task { @MainActor in
                    _ = self.runner?.stopTranscriptionFromFunctionKeyIfNeeded()
                }
            }
        case .deferUntilStartCompletes:
            break
        }
    }

    private func stopHoldToTranscribe() {
        Task { @MainActor in
            guard let runner = self.runner else { return }
            runner.endHoldToTranscribe()
        }
    }

    private func shortcutMatches(type: CGEventType, event: CGEvent, shortcut: KeyboardShortcuts.Shortcut) -> Bool {
        guard type == .keyDown || type == .keyUp else {
            return false
        }

        let keyCode = Int(event.getIntegerValueField(.keyboardEventKeycode))
        guard keyCode == shortcut.carbonKeyCode else {
            return false
        }

        return carbonModifiers(from: event.flags) == shortcut.carbonModifiers
    }

    private func usesFunctionShortcut(_ shortcut: KeyboardShortcuts.Shortcut) -> Bool {
        isBareFunctionShortcut(shortcut) || shortcut.carbonModifiers & kEventKeyModifierFnMask != 0
    }

    private func isBareFunctionShortcut(_ shortcut: KeyboardShortcuts.Shortcut) -> Bool {
        shortcut.carbonKeyCode == kVK_Function && shortcut.carbonModifiers == 0
    }

    private func carbonModifiers(from flags: CGEventFlags) -> Int {
        var modifiers = 0
        if flags.contains(.maskCommand) {
            modifiers |= cmdKey
        }
        if flags.contains(.maskShift) {
            modifiers |= shiftKey
        }
        if flags.contains(.maskAlternate) {
            modifiers |= optionKey
        }
        if flags.contains(.maskControl) {
            modifiers |= controlKey
        }
        if flags.contains(.maskAlphaShift) {
            modifiers |= alphaLock
        }
        if flags.contains(CGEventFlags.maskSecondaryFn) {
            modifiers |= kEventKeyModifierFnMask
        }
        return modifiers
    }

    private func isAutorepeat(_ event: CGEvent) -> Bool {
        event.getIntegerValueField(.keyboardEventAutorepeat) != 0
    }

}
