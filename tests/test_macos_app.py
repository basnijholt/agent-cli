"""Tests for the native macOS menu bar wrapper packaging."""

from __future__ import annotations

import plistlib
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACOS_APP = ROOT / "macos" / "AgentCLI"
SWIFT_SOURCE_DIR = MACOS_APP / "Sources" / "AgentCLI"
BUILD_SCRIPT = ROOT / "macos" / "build-macos-app.sh"
E2E_SCRIPT = ROOT / "macos" / "test-macos-app-e2e.sh"
LOGO_SVG = ROOT / "docs" / "logo-clean.svg"
MENU_BAR_LOGO_SVG = ROOT / "docs" / "logo-avatar.svg"


def swift_source() -> str:
    """Return all AgentCLI Swift source for source-shape assertions."""
    return "\n".join(path.read_text() for path in sorted(SWIFT_SOURCE_DIR.glob("*.swift")))


def assert_script_executable(path: Path) -> None:
    """Assert shell scripts are executable, allowing Windows checkout mode loss."""
    if path.stat().st_mode & stat.S_IXUSR:
        return

    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "ls-files", "-s", "--", path.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.startswith("100755 ")


def test_macos_app_package_files_exist() -> None:
    """The menu bar wrapper should live in a self-contained Swift package."""
    assert (MACOS_APP / "Package.swift").is_file()
    for filename in (
        "AgentCLIApp.swift",
        "AgentCommand.swift",
        "AgentCommandRunner.swift",
        "AgentRuntime.swift",
        "AppDelegate.swift",
        "CommandResult.swift",
        "ConfigurableHotkeyController.swift",
        "FocusedTextTarget.swift",
        "MenuBarIcon.swift",
        "Shortcuts.swift",
        "VoiceLevelOverlay.swift",
    ):
        assert (SWIFT_SOURCE_DIR / filename).is_file()
    assert (MACOS_APP / "Resources" / "Info.plist").is_file()
    assert (MACOS_APP / "README.md").is_file()
    assert LOGO_SVG.is_file()
    assert MENU_BAR_LOGO_SVG.is_file()


def test_macos_app_depends_on_keyboardshortcuts_package() -> None:
    """KeyboardShortcuts README documents SPM install from this URL."""
    package = (MACOS_APP / "Package.swift").read_text()

    assert "https://github.com/sindresorhus/KeyboardShortcuts" in package
    assert 'exact: "1.10.0"' in package
    assert '.product(name: "KeyboardShortcuts", package: "KeyboardShortcuts")' in package


def test_macos_info_plist_declares_menu_bar_agent_app() -> None:
    """The app bundle should be installable and hidden from the Dock."""
    with (MACOS_APP / "Resources" / "Info.plist").open("rb") as f:
        plist = plistlib.load(f)

    assert plist["CFBundleExecutable"] == "AgentCLI"
    assert plist["CFBundleIdentifier"] == "lt.nijho.agent-cli.menubar"
    assert plist["CFBundleIconFile"] == "AgentCLI"
    assert plist["CFBundlePackageType"] == "APPL"
    assert plist["LSUIElement"] is True
    assert "microphone" in plist["NSMicrophoneUsageDescription"].lower()


def test_macos_app_source_exposes_expected_agent_cli_actions() -> None:
    """The wrapper should invoke the existing CLI surface through its private runtime."""
    source = swift_source()

    assert "MenuBarExtra" in source
    assert '"$AGENTCLI_AGENT_CLI" transcribe --toggle --quiet' in source
    assert "transcribe --toggle --llm --quiet" not in source
    assert '"$AGENTCLI_AGENT_CLI" voice-edit --toggle --quiet' in source
    assert '"$AGENTCLI_AGENT_CLI" autocorrect --quiet' in source
    assert '"$AGENTCLI_AGENT_CLI" daemon status whisper --logs 0' in source
    assert '"$AGENTCLI_AGENT_CLI" daemon install whisper -y' in source
    assert "install-hotkeys" not in source
    assert "Install skhd Hotkeys" not in source
    assert '"$AGENTCLI_AGENT_CLI" install-services' not in source
    assert '"$AGENTCLI_AGENT_CLI" start-services --no-attach' not in source
    assert "daemon install --all" not in source
    assert "daemon install memory" not in source
    assert "daemon install rag" not in source


def test_macos_app_menu_prioritizes_daily_voice_actions() -> None:
    """Daily actions should stay top-level; diagnostics belong in troubleshooting."""
    source = swift_source()

    record_index = source.index('Label("Record to Clipboard", systemImage: "waveform")')
    voice_edit_index = source.index('Label("Voice Edit Clipboard", systemImage: "mic")')
    autocorrect_index = source.index(
        'Label("Autocorrect Clipboard", systemImage: "text.badge.checkmark")',
    )
    troubleshooting_menu_index = source.index("            Menu {", autocorrect_index)
    troubleshooting_label_index = source.index(
        'Label("Troubleshooting", systemImage: "wrench.and.screwdriver")',
    )
    copy_output_index = source.index('Label("Copy Last Output", systemImage: "doc.on.doc")')

    assert record_index < voice_edit_index < autocorrect_index < troubleshooting_menu_index
    assert troubleshooting_menu_index < copy_output_index < troubleshooting_label_index
    assert 'Menu("Setup")' not in source
    assert 'Text("Voice: \\(runner.menuStatusMessage)")' in source
    assert "var menuStatusMessage: String" in source
    assert "menuStatusMaxLength" in source
    assert "Text(runner.statusMessage)" not in source
    assert "if !runner.lastOutput.isEmpty" in source
    assert "if runner.hasLastError" in source
    assert 'Label("Update CLI Runtime", systemImage: "arrow.down.circle")' in source
    assert 'Label("Reinstall Voice Service", systemImage: "waveform.badge.plus")' in source
    assert 'Label("Voice Service Status", systemImage: "waveform.path.ecg")' in source
    assert 'identifier: "voice-service-status"' in source
    assert 'identifier: "install-voice-service"' in source
    assert 'Label("Daemon Status", systemImage: "server.rack")' not in source
    assert 'Label("Install Services", systemImage: "square.and.arrow.down")' not in source
    assert 'Label("Start Services", systemImage: "play.circle")' not in source
    assert 'identifier: "install-services"' not in source
    assert 'identifier: "start-services"' not in source


def test_macos_app_formats_voice_service_status_for_notifications() -> None:
    """Voice status notifications should be app copy, not raw CLI terminal output."""
    source = swift_source()

    assert "voiceServiceStatusMessage" in source
    assert 'command.identifier == "voice-service-status"' in source
    assert "Whisper is running" in source
    assert "Whisper is not installed" in source
    assert "Whisper is installed but not running" in source
    assert '"~/Library/Logs/agent-cli-whisper/"' in source
    assert 'return "Service Status' not in source


def test_macos_app_uses_avatar_svg_as_menu_bar_icon() -> None:
    """The menu bar icon should use the checked-in avatar-only AgentCLI SVG."""
    source = swift_source()
    build_script = BUILD_SCRIPT.read_text()
    e2e_script = E2E_SCRIPT.read_text()
    assert MENU_BAR_LOGO_SVG.is_file()
    avatar_svg = MENU_BAR_LOGO_SVG.read_text()

    assert "AgentCLIMenuBarIcon(isRecording: runner.isRecording)" in source
    assert "Self.logoImage(isRecording: isRecording)" in source
    assert "Image(nsImage: image)" in source
    assert ".id(isRecording)" in source
    assert "private static func logoImage(isRecording: Bool) -> NSImage?" in source
    assert "private static let idleLogoImage" in source
    assert "private static let recordingLogoImage" in source
    assert "makeRecordingLogoImage" in source
    assert 'forResource: "logo-avatar", withExtension: "svg"' in source
    assert "NSImage(contentsOf:" in source
    assert "image.isTemplate = true" in source
    assert "NSColor.systemRed.setFill()" in source
    assert 'MENU_BAR_LOGO_SVG="$ROOT_DIR/docs/logo-avatar.svg"' in build_script
    assert "Contents/Resources/logo-avatar.svg" in build_script
    assert 'test -f "$APP/Contents/Resources/logo-avatar.svg"' in e2e_script
    assert 'id="path2"' not in avatar_svg
    assert 'id="path18"' not in avatar_svg
    assert 'id="path19"' not in avatar_svg
    assert 'id="path5"' in avatar_svg
    assert 'id="path13"' in avatar_svg


def test_macos_app_menu_bar_icon_changes_while_transcribing() -> None:
    """Only recording-style commands should hold the red recording indicator."""
    source = swift_source()

    assert "let showsRecordingIndicator: Bool" in source
    assert "@Published private(set) var isRecording = false" in source
    assert "private var recordingCommandCount = 0" in source
    assert "private var activeRecordingCommands: [String: Int] = [:]" in source
    assert "recordingCommandCount > 0" in source
    assert "let shouldStartRecording = command.showsRecordingIndicator && !isStopRequest" in source
    assert "beginRecordingIndicator(for: command)" in source
    assert "endRecordingIndicator(for: command)" in source
    assert "isRecording = recordingCommandCount > 0" in source
    assert 'title: "Toggle Transcription"' in source
    assert "showsRecordingIndicator: true" in source


def test_macos_app_exits_duplicate_menu_bar_instances() -> None:
    """Only one menu bar process should own the icon and voice level overlay."""
    source = swift_source()

    assert (
        "AgentRuntime.shared.runSelfTestIfRequested()\n"
        "        guard !terminateIfAnotherInstanceIsRunning() else { return }" in source
    )
    assert "private var instanceLockFD: Int32 = -1" in source
    assert "terminateIfAnotherInstanceIsRunning()" in source
    assert "AGENTCLI_INSTANCE_LOCK_PATH" in source
    assert "private static func instanceLockURL() -> URL" in source
    assert 'appendingPathComponent("lt.nijho.agent-cli.menubar.lock")' in source
    assert "Darwin.open(lockURL.path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)" in source
    assert "flock(instanceLockFD, LOCK_EX | LOCK_NB) == 0" in source
    assert 'AgentCommandRunner.shared.statusMessage = "Agent CLI is already running"' in source
    assert "flock(instanceLockFD, LOCK_UN)" in source
    assert "close(instanceLockFD)" in source
    assert "NSApp.terminate(nil)" in source


def test_macos_app_shows_bottom_voice_level_overlay_while_recording() -> None:
    """Recording should show a small non-activating loudness meter overlay."""
    source = swift_source()

    assert "import AVFoundation" in source
    assert "VoiceLevelOverlayController.shared.show()" in source
    assert "VoiceLevelOverlayController.shared.hide()" in source
    assert "final class VoiceLevelOverlayController" in source
    assert "NSPanel" in source
    assert ".nonactivatingPanel" in source
    assert "panel.ignoresMouseEvents = true" in source
    assert (
        "panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]"
        in source
    )
    assert "screen.visibleFrame" in source
    assert "frame.minY + 38" in source
    assert "VoiceLevelOverlayView(meter: VoiceLevelMeter.shared)" in source
    assert ".frame(width: 147, height: 38)" in source
    assert "private let panelSize = NSSize(width: 154, height: 41)" in source
    assert ".frame(width: 3.5, height: max(5, 25 * amplitude))" in source


def test_macos_app_voice_level_meter_uses_live_microphone_power_without_saving_audio() -> None:
    """The overlay bars should come from live mic metering and release capture afterward."""
    source = swift_source()

    assert "final class VoiceLevelMeter" in source
    assert "@Published private(set) var amplitudes" in source
    assert "AVCaptureDevice.authorizationStatus(for: .audio)" in source
    assert "AVCaptureDevice.requestAccess(for: .audio)" in source
    assert 'URL(fileURLWithPath: "/dev/null")' in source
    assert "AVAudioRecorder(url: url, settings: settings)" in source
    assert "recorder.isMeteringEnabled = true" in source
    assert "recorder.record()" in source
    assert "recorder.updateMeters()" in source
    assert "averagePower(forChannel: 0)" in source
    assert "Timer.scheduledTimer" in source
    assert "timer?.invalidate()" in source
    assert "recorder?.stop()" in source


def test_macos_app_voice_level_meter_smooths_fast_meter_changes() -> None:
    """The voice overlay should respond to loudness without jittering too quickly."""
    source = swift_source()

    assert ".animation(.easeOut(duration: 0.11), value: amplitude)" in source
    assert "private var smoothedLevel = CGFloat(0.16)" in source
    assert "withTimeInterval: 0.06" in source
    assert "phase += 0.22" in source
    assert "smoothedLevel = (smoothedLevel * 0.55) + (normalized * 0.45)" in source
    assert "let displayLevel = smoothedLevel" in source


def test_macos_app_supports_configurable_hold_to_transcribe_shortcut() -> None:
    """A hold shortcut should start on key-down and stop on key-up."""
    source = swift_source()

    assert "static let holdToTranscribe" in source
    assert '"holdToTranscribe"' in source
    assert "KeyboardShortcuts.Shortcut(.function)" in source
    assert "default: KeyboardShortcuts.Shortcut(.function)" in source
    assert 'title: "Hold to Transcribe"' in source
    assert "name: .holdToTranscribe" in source
    assert "KeyboardShortcuts.onKeyDown(for: .holdToTranscribe)" in source
    assert "runner.beginHoldToTranscribe()" in source
    assert "KeyboardShortcuts.onKeyUp(for: .holdToTranscribe)" in source
    assert "runner.endHoldToTranscribe()" in source
    assert "func beginHoldToTranscribe()" in source
    assert "func endHoldToTranscribe()" in source
    assert "private var holdTranscriptionState: HoldTranscriptionState = .idle" in source
    assert "private var pasteAfterRecordingCommands: Set<String> = []" in source


def test_macos_app_hides_hold_recording_ui_immediately_on_key_release() -> None:
    """Hold-to-type should stop looking like it is recording as soon as the key is released."""
    source = swift_source()

    assert "let wasRecording = isRecordingCommand(.toggleTranscription)" in source
    assert "holdTranscriptionState = .awaitingPid" in source
    assert (
        "if wasRecording {\n"
        "            endRecordingIndicator(for: .toggleTranscription)\n"
        '            statusMessage = "Transcribing..."\n'
        "            stopHeldTranscriptionWhenReady()" in source
    )
    assert (
        "holdTranscriptionState == .awaitingPid {\n"
        "            endRecordingIndicator(for: command)\n"
        "            stopHeldTranscriptionWhenReady()" in source
    )
    assert (
        "if shouldStartRecording {\n"
        "                    self.clearHoldTranscriptionState(for: command)" in source
    )
    assert (
        "if result.exitCode == 0 {\n"
        "                    if self.holdTranscriptionState == .stopping {\n"
        '                        self.statusMessage = "Transcribing..."' in source
    )


def test_macos_app_clears_hold_stop_state_before_showing_finished_transcript() -> None:
    """Hold-to-type should not leave the menu stuck on Transcribing after output is ready."""
    source = swift_source()

    assert "private func clearHoldTranscriptionState(for command: AgentCommand)" in source
    assert (
        "private func clearHoldTranscriptionState(for command: AgentCommand) {\n"
        "        guard command.identifier == AgentCommand.toggleTranscription.identifier else { return }\n"
        "        holdTranscriptionState = .idle\n"
        "    }" in source
    )
    assert "self.clearHoldTranscriptionState(for: command)" in source
    assert (
        "if result.exitCode == 0 {\n"
        "                    if self.holdTranscriptionState == .stopping {\n"
        '                        self.statusMessage = "Transcribing..."\n'
        "                    }\n"
        "                    return" in source
    )


def test_macos_app_models_hold_to_transcribe_as_explicit_state() -> None:
    """Hold-to-type coordination should use one state machine instead of boolean soup."""
    source = swift_source()

    assert "private enum HoldTranscriptionState" in source
    assert "case idle" in source
    assert "case recording" in source
    assert "case awaitingPid" in source
    assert "case stopping" in source
    assert "private var holdTranscriptionState: HoldTranscriptionState = .idle" in source
    assert "holdTranscriptionState.isFinishing" in source
    assert "holdToTranscribeActive" not in source
    assert "pendingHoldToTranscribeStop" not in source
    assert "holdStopRequestActive" not in source


def test_macos_app_uses_private_runtime_dir_for_hold_to_transcribe_stop() -> None:
    """Hold-to-type stop should watch the same PID dir that the app passes to agent-cli."""
    source = swift_source()
    launchd = (ROOT / "agent_cli" / "install" / "launchd.py").read_text()

    assert "let runtimeURL: URL" in source
    assert 'appendingPathComponent("runtime", isDirectory: true)' in source
    assert 'environment["AGENTCLI_RUNTIME_DIR"] = runtimeURL.path' in source
    assert (
        "try fileManager.createDirectory(at: runtimeURL, withIntermediateDirectories: true)"
        in source
    )
    assert '"$AGENTCLI_RUNTIME_DIR/transcribe.pid"' in source
    assert '"$HOME/.cache/agent-cli/transcribe.pid"' not in source
    assert '"AGENTCLI_RUNTIME_DIR"' in launchd


def test_macos_app_defaults_clipboard_transcription_to_fn_space() -> None:
    """The regular clipboard transcription toggle should default to Fn+Space."""
    source = swift_source()

    assert "kEventKeyModifierFnMask" in source
    assert (
        "KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)"
        in source
    )
    assert "event.modifierFlags.contains(.function)" in source
    assert "carbonModifiers |= kEventKeyModifierFnMask" in source
    assert ".flagsChanged" in source
    assert "Fn+Space" in source


def test_macos_app_migrates_old_default_shortcuts_to_fn_defaults() -> None:
    """Existing installs with old built-in defaults should get the new defaults."""
    source = swift_source()

    assert "ShortcutDefaultsMigrator.migrate()" in source
    assert "migrateDefault(" in source
    assert "from: KeyboardShortcuts.Shortcut(.r, modifiers: [.command, .shift])" in source
    assert (
        "to: KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)"
        in source
    )
    assert "from: KeyboardShortcuts.Shortcut(.space, modifiers: [.control, .option])" in source
    assert "to: KeyboardShortcuts.Shortcut(.function)" in source
    assert "KeyboardShortcuts.getShortcut(for: name) == oldShortcut" in source
    assert "KeyboardShortcuts.setShortcut(newShortcut, for: name)" in source


def test_macos_app_pastes_hold_transcription_into_focused_field() -> None:
    """Push-to-talk should paste the completed transcript when macOS allows it."""
    source = swift_source()

    assert "import ApplicationServices" in source
    assert "shouldPasteAfterRecording(for: command) && result.exitCode == 0" in source
    assert (
        "pasteTranscriptIntoFocusedField(result.output, for: command, target: pasteTarget)"
        in source
    )
    assert "NSPasteboard.general.clearContents()" in source
    assert "NSPasteboard.general.setString(transcript, forType: .string)" in source
    assert "AXIsProcessTrusted()" in source
    assert "requestAccessibilityPermissionIfNeeded()" in source
    assert "AXIsProcessTrustedWithOptions(options)" in source
    assert "kAXTrustedCheckOptionPrompt as String" in source
    assert (
        'statusMessage = "Transcript copied. Allow Accessibility permission to auto-insert text."'
        in source
    )
    assert "DispatchQueue.main.asyncAfter(deadline: .now() + 0.20)" in source
    assert "target?.refocus()" in source
    assert "CGEventSource(stateID: .hidSystemState)" in source
    assert (
        "CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_Command), keyDown: true)"
        in source
    )
    assert (
        "CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_V), keyDown: true)"
        in source
    )
    assert "keyDown?.flags = .maskCommand" in source
    assert "keyDown?.post(tap: .cghidEventTap)" in source
    assert "keyUp?.post(tap: .cghidEventTap)" in source
    assert "postToPid" not in source


def test_macos_app_refocuses_original_app_for_hold_to_type() -> None:
    """Hold-to-type should restore the original focused app before pasting."""
    source = swift_source()

    assert "private var holdToTranscribePasteTarget: FocusedTextTarget?" in source
    assert "holdToTranscribePasteTarget = FocusedTextTarget.capture()" in source
    assert "let pasteTarget = self.holdToTranscribePasteTarget" in source
    assert (
        "pasteTranscriptIntoFocusedField(result.output, for: command, target: pasteTarget)"
        in source
    )
    assert "holdToTranscribePasteTarget = nil" in source
    assert "struct FocusedTextTarget" in source
    assert "AXUIElementCreateSystemWide()" in source
    assert "kAXFocusedUIElementAttribute as CFString" in source
    assert "CFGetTypeID(focusedValue) == AXUIElementGetTypeID()" in source
    assert "AXUIElementGetPid(element, &pid)" in source
    assert "func refocus()" in source
    assert (
        "NSRunningApplication(processIdentifier: pid)?.activate(options: [.activateIgnoringOtherApps])"
        in source
    )
    assert (
        "AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)"
        in source
    )
    assert "self.postPasteShortcut()" in source
    assert "kAXSelectedTextAttribute as CFString" not in source
    assert "func insertText(_ text: String)" not in source


def test_macos_app_throttles_accessibility_prompt_per_installed_build() -> None:
    """An untrusted paste should prompt when needed but not repeatedly for one build."""
    source = swift_source()

    assert "accessibilityPromptMarkerURL" in source
    assert 'appendingPathComponent(".accessibility-prompted")' in source
    assert "accessibilityPromptMarkerContents" in source
    assert "Bundle.main.executableURL ?? Bundle.main.bundleURL" in source
    assert "contentModificationDateKey" in source
    assert "packageSource=\\(AgentRuntime.shared.agentCLIPackageSource)" in source
    assert (
        "guard (try? String(contentsOf: AgentRuntime.shared.accessibilityPromptMarkerURL))"
        in source
    )
    assert "try? accessibilityPromptMarkerContents.write(" in source
    assert "AXIsProcessTrustedWithOptions(options)" in source
    assert (
        'statusMessage = "Transcript copied. Allow Accessibility permission to auto-insert text."'
        in source
    )


def test_macos_app_suppresses_start_notification_for_recording_stop_toggle() -> None:
    """The second toggle should request stop, not announce a fresh recording start."""
    source = swift_source()

    assert (
        "let isStopRequest = command.showsRecordingIndicator && isRecordingCommand(command)"
        in source
    )
    assert "let shouldStartRecording = command.showsRecordingIndicator && !isStopRequest" in source
    assert "if shouldStartRecording" in source
    assert "self.notifyStart(for: command)" in source
    assert "if isStopRequest && result.exitCode == 0" in source
    assert 'self.statusMessage = "Stop requested for \\(command.title)"' in source
    assert "private func isRecordingCommand(_ command: AgentCommand) -> Bool" in source
    assert 'identifier: "transcribe"' in source
    assert 'identifier: "voice-edit"' in source
    assert "self.notify(title: notificationTitle, body: notificationBody)" in source
    assert (
        "if command.showsRecordingIndicator {\n"
        "                DispatchQueue.main.async {\n"
        "                    self.beginRecordingIndicator()\n"
        "                    self.notifyStart(for: command)"
    ) not in source


def test_macos_app_makes_recording_stop_requests_idempotent() -> None:
    """Repeated stop shortcut presses should not escalate the CLI process to SIGKILL."""
    source = swift_source()

    assert "private var pendingStopRecordingCommands: Set<String> = []" in source
    assert "if isStopRequest && isStopPending(for: command)" in source
    assert 'statusMessage = "Stop already requested for \\(command.title)"' in source
    assert "markStopRequested(for: command)" in source
    assert "clearStopRequested(for: command)" in source
    assert "private func isStopPending(for command: AgentCommand) -> Bool" in source
    assert "private func markStopRequested(for command: AgentCommand)" in source
    assert "private func clearStopRequested(for command: AgentCommand)" in source


def test_macos_app_sends_visible_transcription_notifications() -> None:
    """Transcription should notify on start and finish, with the transcript in the body."""
    source = swift_source()

    assert "UNUserNotificationCenter.current().delegate = self" in source
    assert "configureNotifications()" in source
    assert "getNotificationSettings" in source
    assert ".notDetermined" in source
    assert "requestAuthorization(options: [.alert])" in source
    assert "notificationsDisabled()" in source
    assert "UNUserNotificationCenterDelegate" in source
    assert "willPresent notification: UNNotification" in source
    assert ".banner" in source
    assert ".list" in source
    assert ".sound" not in source
    assert "content.sound" not in source
    assert 'startNotificationTitle: "Transcription Started"' in source
    assert 'finishNotificationTitle: "Transcription Finished"' in source
    assert "notifyStart(for: command)" in source
    assert "notificationBody(for: command, result: result, statusMessage: message)" in source
    assert "result.output.trimmingCharacters" in source
    assert "notificationLogoURL" in source
    assert 'forResource: "logo-avatar", withExtension: "png"' in source
    assert "UNNotificationAttachment" in source
    assert "content.attachments = [attachment]" in source


def test_macos_app_can_open_notification_settings() -> None:
    """Users should get an in-app path to fix previously denied notification permission."""
    source = swift_source()

    assert 'Label("Open Notification Settings", systemImage: "bell.badge")' in source
    assert "openNotificationSettings()" in source
    assert "notificationSettingsURLs" in source
    assert "x-apple.systempreferences:com.apple.Notifications-Settings.extension" in source
    assert "x-apple.systempreferences:com.apple.preference.notifications" in source
    assert "Notifications are disabled" in source


def test_macos_app_can_open_accessibility_settings() -> None:
    """Users should get an explicit path to grant paste insertion permission."""
    source = swift_source()

    assert 'Label("Open Accessibility Settings", systemImage: "figure.wave")' in source
    assert "openAccessibilitySettings()" in source
    assert "accessibilitySettingsURLs" in source
    assert "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" in source
    assert "Accessibility permission controls auto-inserting transcripts" in source


def test_macos_app_makes_command_errors_discoverable() -> None:
    """Failures should persist full details and expose obvious menu actions."""
    source = swift_source()

    assert "@Published private(set) var hasLastError = false" in source
    assert 'Label("Open Last Error", systemImage: "exclamationmark.triangle")' in source
    assert 'Label("Copy Last Error", systemImage: "doc.on.doc")' in source
    assert 'Label("Open Logs Folder", systemImage: "doc.text.magnifyingglass")' in source
    assert "lastErrorURL" in source
    assert 'appendingPathComponent("last-error.txt")' in source
    assert "logsURL" in source
    assert 'appendingPathComponent("Logs"' in source
    assert "recordFailure(command: command, result: result)" in source
    assert "recordFailure(command: command, result: bootstrap)" in source
    assert 'recordFailure(title: "Toggle Transcription Stop", result: result)' in source
    assert "try details.write(to: AgentRuntime.shared.lastErrorURL" in source
    assert "openLastError()" in source
    assert "copyLastError()" in source
    assert "openLogsFolder()" in source
    assert "Full error saved. Open Agent CLI > Open Last Error for details." in source


def test_macos_app_registers_configurable_native_global_hotkeys() -> None:
    """KeyboardShortcuts source documents setShortcut/getShortcut and onKeyUp handlers."""
    source = swift_source()

    assert "import KeyboardShortcuts" in source
    assert "KeyboardShortcuts.Name" in source
    assert "KeyboardShortcuts.Shortcut(event:" in source
    assert "KeyboardShortcuts.setShortcut" in source
    assert "KeyboardShortcuts.getShortcut" in source
    assert "KeyboardShortcuts.onKeyDown" in source
    assert "KeyboardShortcuts.onKeyUp" in source
    assert "ShortcutRecorderButton" in source
    assert "Fn+Space" in source
    assert "Cmd+Shift+A" in source
    assert "Cmd+Shift+V" in source
    assert "Fn" in source
    assert ".toggleTranscription" in source
    assert ".holdToTranscribe" in source
    assert ".autocorrect" in source
    assert ".voiceEdit" in source


def test_macos_app_shows_actual_persisted_shortcuts_and_can_reset_them() -> None:
    """The menu should reflect stored shortcuts instead of claiming static defaults."""
    source = swift_source()
    readme = (MACOS_APP / "README.md").read_text()

    assert "ShortcutSummaryState" in source
    assert "@StateObject private var shortcutSummary = ShortcutSummaryState.shared" in source
    assert "Text(shortcutSummary.summary)" in source
    assert "KeyboardShortcuts.getShortcut(for: name)?.description" in source
    assert 'Label("Reset Keyboard Shortcuts", systemImage: "arrow.counterclockwise")' in source
    assert "ShortcutSummaryState.shared.resetDefaults()" in source
    assert 'statusMessage = "Reset keyboard shortcuts to defaults"' in source
    assert "ShortcutSummaryState.shared.refresh()" in source
    assert 'Text("Hotkeys: Cmd+Shift+R / Cmd+Shift+A / Cmd+Shift+V")' not in source
    assert "`Fn+Space` toggles transcription" in readme
    assert "`Fn` records while held" in readme
    assert "`Cmd+Shift+R` toggles transcription" not in readme


def test_macos_build_script_creates_signed_app_bundle() -> None:
    """The build script should produce a Finder-installable .app bundle."""
    script = BUILD_SCRIPT.read_text()

    assert_script_executable(BUILD_SCRIPT)
    assert "swift build" in script
    assert "Contents/MacOS" in script
    assert "Contents/Info.plist" in script
    assert "CFBundleIconFile" not in script
    assert "Contents/Resources/AgentCLI.icns" in script
    assert "Contents/Resources/logo-avatar.png" in script
    assert "iconutil" in script
    assert "qlmanage" in script
    assert "sips" in script
    assert "Contents/Resources/bin/uv" in script
    assert "Contents/Resources/wheels" in script
    assert "uv build --wheel" in script
    assert "agent_cli-*.whl" in script
    assert "command -v uv" in script
    assert "INSTALL_DIR" in script
    assert "AGENTCLI_SKIP_OPEN" in script
    assert "quit_running_app" in script
    assert 'pgrep -x "$APP_NAME"' in script
    assert 'osascript -e "quit app \\"$APP_NAME\\""' in script
    assert 'ditto "$APP_DIR" "$INSTALL_PATH"' in script
    assert "Installed AgentCLI notification logo is missing" in script
    assert "codesign" in script
    assert "--deep" in script
    assert "--install" in script
    assert "--dmg" in script
    assert "hdiutil create" in script


def test_macos_app_bootstraps_private_uv_runtime() -> None:
    """Drag-and-drop app installs Python dependencies into user app support."""
    source = swift_source()

    assert "AgentRuntime" in source
    assert "Application Support" in source
    assert "AGENTCLI_APP_SUPPORT_DIR" in source
    assert "Contents/Resources/bin/uv" in source
    assert "Contents/Resources/wheels" in source
    assert "UV_CACHE_DIR" in source
    assert "UV_PYTHON_INSTALL_DIR" in source
    assert "UV_TOOL_DIR" in source
    assert "UV_TOOL_BIN_DIR" in source
    assert "AGENTCLI_BUNDLED_UV" in source
    assert "AGENTCLI_PACKAGE_SOURCE" in source
    assert "AGENT_CLI_CONFIG_HOME" in source
    assert 'appSupportURL.appendingPathComponent("config"' in source
    assert 'appendingPathComponent(".config")' not in source
    assert "agentCLIInstallMarkerURL" in source
    assert 'appendingPathComponent(".agent-cli-installed")' in source
    assert "agentCLIInstallMarkerContents" in source
    assert "fileManager.isExecutableFile(atPath: agentCLIURL.path)" in source
    assert (
        "(try? String(contentsOf: agentCLIInstallMarkerURL)) == agentCLIInstallMarkerContents"
        in source
    )
    assert "try? agentCLIInstallMarkerContents.write(" in source
    assert "uv tool install" in source
    assert "agent-cli[audio,llm]" in source
    assert "agentCLIInstallRequirement" in source
    assert "ensureTranscriptionReady" in source
    assert "whisperDaemonMarkerURL" in source
    assert "whisperDaemonMarkerContents" in source
    assert "packageSource=" in source
    assert '"$AGENTCLI_AGENT_CLI" daemon install whisper -y' in source
    assert "--agentcli-bootstrap-self-test" in source


def test_macos_app_waits_for_whisper_daemon_readiness() -> None:
    """Transcription should not start before the local Wyoming port is listening."""
    source = swift_source()

    assert "waitForWhisperDaemonReady()" in source
    assert "return waitForWhisperDaemonReady()" in source
    assert "canConnectToLocalhost(port: 10300)" in source
    assert "Thread.sleep(forTimeInterval: 0.5)" in source
    assert "socket(AF_INET, SOCK_STREAM, 0)" in source
    assert "connect(socketFD" in source
    assert '"$AGENTCLI_AGENT_CLI" daemon status whisper --logs 80' in source
    assert "Whisper ASR service did not become ready at localhost:10300" in source


def test_macos_app_has_end_to_end_packaging_test() -> None:
    """The installable artifact should have a repeatable local E2E gate."""
    script = E2E_SCRIPT.read_text()

    assert_script_executable(E2E_SCRIPT)
    assert "build-macos-app.sh --dmg" in script
    assert "INSTALL_DIR=" in script
    assert "AGENTCLI_SKIP_OPEN=1" in script
    assert "codesign --verify" in script
    assert "hdiutil verify" in script
    assert "Contents/Resources/bin/uv" in script
    assert "Contents/Resources/wheels" in script
    assert "Contents/Resources/AgentCLI.icns" in script
    assert "Contents/Resources/logo-avatar.png" in script
    assert "AGENTCLI_TEST_COMMAND_LOG" in script
    assert "AGENTCLI_INSTANCE_LOCK_PATH" in script
    assert "UV_BINARY=" in script
    assert "uv build --wheel" in script
    assert "--agentcli-bootstrap-self-test" in script
    assert "daemon install whisper -y" in script
    assert "transcribe --toggle --quiet" in script
    assert "open -n" in script or "Contents/MacOS/AgentCLI" in script
