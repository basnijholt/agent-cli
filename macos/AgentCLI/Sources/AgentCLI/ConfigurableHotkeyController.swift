import ApplicationServices
import Carbon.HIToolbox
import Foundation
import KeyboardShortcuts

final class ConfigurableHotkeyController {
    static let shared = ConfigurableHotkeyController()

    private var registered = false
    private weak var runner: AgentCommandRunner?
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var functionKeyIsDown = false
    private var suppressNextFunctionKeyRelease = false
    private var holdToTranscribeIsRecording = false
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
            Task { @MainActor in
                _ = runner.beginHoldToTranscribe()
            }
        }
        KeyboardShortcuts.onKeyUp(for: .holdToTranscribe) {
            guard !ShortcutRecordingState.shared.isRecording,
                  let shortcut = KeyboardShortcuts.getShortcut(for: .holdToTranscribe),
                  !self.usesFunctionShortcut(shortcut) else {
                return
            }
            Task { @MainActor in runner.endHoldToTranscribe() }
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
        holdToTranscribeIsRecording = false
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

            if !isAutorepeat(event) && !holdToTranscribeIsRecording {
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
            if !isAutorepeat(event) && !holdToTranscribeIsRecording {
                Task { @MainActor in
                    guard let runner = self.runner else { return }
                    if runner.beginHoldToTranscribe() {
                        self.holdToTranscribeIsRecording = true
                    }
                }
            }
            return true
        }

        if type == .keyUp {
            if holdToTranscribeIsRecording {
                holdToTranscribeIsRecording = false
                Task { @MainActor in
                    guard let runner = self.runner else { return }
                    runner.endHoldToTranscribe()
                }
            }
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

        if holdToTranscribeIsRecording {
            holdToTranscribeIsRecording = false
            Task { @MainActor in
                guard let runner = self.runner else { return }
                runner.endHoldToTranscribe()
            }
        } else {
            Task { @MainActor in
                _ = self.runner?.stopTranscriptionFromFunctionKeyIfNeeded()
            }
        }

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
            Task { @MainActor in
                if self.runner?.stopTranscriptionFromFunctionKeyIfNeeded() == true {
                    return
                }

                guard let runner = self.runner else { return }
                if runner.beginHoldToTranscribe() {
                    self.holdToTranscribeIsRecording = true
                }
            }
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
