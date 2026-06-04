import ApplicationServices
import Carbon.HIToolbox
import Foundation
import KeyboardShortcuts

enum HoldToTranscribeStopDecision: Equatable {
    case none
    case deferUntilStartCompletes
    case stopNow
}

struct HoldToTranscribeKeyState {
    private enum State {
        case idle
        case startPending(releaseRequested: Bool)
        case recording
    }

    private var state: State = .idle

    var isStartPendingOrRecording: Bool {
        switch state {
        case .idle:
            return false
        case .startPending, .recording:
            return true
        }
    }

    mutating func requestStart() -> Bool {
        guard case .idle = state else { return false }
        state = .startPending(releaseRequested: false)
        return true
    }

    mutating func releaseKey() -> HoldToTranscribeStopDecision {
        switch state {
        case .idle:
            return .none
        case .startPending:
            state = .startPending(releaseRequested: true)
            return .deferUntilStartCompletes
        case .recording:
            state = .idle
            return .stopNow
        }
    }

    mutating func completeStart(started: Bool) -> HoldToTranscribeStopDecision {
        guard case let .startPending(releaseRequested) = state else { return .none }
        guard started else {
            state = .idle
            return .none
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
    private let holdToTranscribeDelay: TimeInterval = 0.16

    private init() {}

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
            requestAccessibilityPermissionForFunctionHotkeys()
            Task { @MainActor in
                runner.statusMessage = "Allow Accessibility permission for Fn transcription shortcuts"
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

    private func handleFunctionAwareHotkey(type: CGEventType, event: CGEvent) -> Unmanaged<CGEvent>? {
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
            suppressNextFunctionKeyRelease = usesFunctionShortcut(shortcut)

            if !isAutorepeat(event) && !holdToTranscribeKeyState.isStartPendingOrRecording {
                Task { @MainActor in
                    self.runner?.run(.toggleTranscription)
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
            self.requestHoldToTranscribeStart(stopExistingFunctionRecordingFirst: true)
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

    private func requestHoldToTranscribeStart(
        preferredRunner: AgentCommandRunner? = nil,
        stopExistingFunctionRecordingFirst: Bool = false
    ) {
        guard holdToTranscribeKeyState.requestStart() else { return }
        Task { @MainActor in
            if stopExistingFunctionRecordingFirst,
               self.runner?.stopTranscriptionFromFunctionKeyIfNeeded() == true {
                _ = self.holdToTranscribeKeyState.completeStart(started: false)
                return
            }

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
        if action == .stopNow {
            runner.endHoldToTranscribe()
        }
    }

    private func releaseHoldToTranscribeKey(stopExistingFunctionRecordingIfIdle: Bool = false) {
        switch holdToTranscribeKeyState.releaseKey() {
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

    private func requestAccessibilityPermissionForFunctionHotkeys() {
        guard !AXIsProcessTrusted() else { return }

        // Equivalent to kAXTrustedCheckOptionPrompt as String, but Swift exposes it unmanaged.
        let promptOption = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let options = [promptOption: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
    }
}
