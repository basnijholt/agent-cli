import AppKit
import ApplicationServices
import AVFoundation
import Carbon.HIToolbox
import Darwin
import Foundation
import KeyboardShortcuts
import SwiftUI
import UserNotifications

@main
struct AgentCLIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.openWindow) private var openWindow
    @StateObject private var runner = AgentCommandRunner.shared
    @StateObject private var shortcutSummary = ShortcutSummaryState.shared

    var body: some Scene {
        MenuBarExtra {
            Button {
                runner.run(.toggleTranscription)
            } label: {
                Label("Toggle Transcription", systemImage: "waveform")
            }

            Button {
                runner.run(.voiceEdit)
            } label: {
                Label("Voice Edit Clipboard", systemImage: "mic")
            }

            Button {
                runner.run(.autocorrect)
            } label: {
                Label("Autocorrect Clipboard", systemImage: "text.badge.checkmark")
            }

            Divider()

            Button {
                runner.run(.voiceServiceStatus)
            } label: {
                Label("Voice Service Status", systemImage: "waveform.path.ecg")
            }

            Menu("Setup") {
                Button {
                    runner.run(.installOrUpdateCLI)
                } label: {
                    Label("Install or Update CLI", systemImage: "arrow.down.circle")
                }

                Button {
                    runner.run(.installVoiceService)
                } label: {
                    Label("Install Voice Service", systemImage: "waveform.badge.plus")
                }
            }

            Divider()

            Button {
                openWindow(id: "settings")
                NSApp.activate(ignoringOtherApps: true)
            } label: {
                Label("Keyboard Shortcuts...", systemImage: "command")
            }

            Button {
                ShortcutSummaryState.shared.resetDefaults()
                runner.statusMessage = "Reset keyboard shortcuts to defaults"
            } label: {
                Label("Reset Keyboard Shortcuts", systemImage: "arrow.counterclockwise")
            }

            Divider()

            Text(shortcutSummary.summary)

            Divider()

            Text(runner.statusMessage)
                .lineLimit(3)

            Button {
                runner.copyLastOutput()
            } label: {
                Label("Copy Last Output", systemImage: "doc.on.doc")
            }
            .disabled(runner.lastOutput.isEmpty)

            Button {
                runner.openLastError()
            } label: {
                Label("Open Last Error", systemImage: "exclamationmark.triangle")
            }
            .disabled(!runner.hasLastError)

            Button {
                runner.copyLastError()
            } label: {
                Label("Copy Last Error", systemImage: "doc.on.doc")
            }
            .disabled(!runner.hasLastError)

            Button {
                runner.openLogsFolder()
            } label: {
                Label("Open Logs Folder", systemImage: "doc.text.magnifyingglass")
            }

            Button {
                runner.openConfigFolder()
            } label: {
                Label("Open Config Folder", systemImage: "folder")
            }

            Button {
                runner.openNotificationSettings()
            } label: {
                Label("Open Notification Settings", systemImage: "bell.badge")
            }

            Divider()

            Button {
                NSApp.terminate(nil)
            } label: {
                Label("Quit", systemImage: "power")
            }
        } label: {
            AgentCLIMenuBarIcon(isRecording: runner.isRecording)
        }
        .menuBarExtraStyle(.menu)

        Window("Agent CLI Settings", id: "settings") {
            SettingsView()
                .frame(width: 460)
        }
        .windowResizability(.contentSize)
    }
}

struct AgentCLIMenuBarIcon: View {
    let isRecording: Bool

    var body: some View {
        if let image = Self.logoImage(isRecording: isRecording) {
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 22, height: 18)
                .id(isRecording)
                .accessibilityLabel(Text(isRecording ? "Agent CLI recording" : "Agent CLI"))
        } else {
            Image(systemName: isRecording ? "record.circle.fill" : "person.crop.circle")
                .id(isRecording)
                .accessibilityLabel(Text(isRecording ? "Agent CLI recording" : "Agent CLI"))
        }
    }

    private static func logoImage(isRecording: Bool) -> NSImage? {
        isRecording ? recordingLogoImage : idleLogoImage
    }

    private static let idleLogoImage: NSImage? = {
        guard let url = Bundle.main.url(forResource: "logo-avatar", withExtension: "svg"),
              let image = NSImage(contentsOf: url)
        else {
            return nil
        }
        image.isTemplate = true
        image.size = NSSize(width: 18, height: 18)
        return image
    }()

    private static let recordingLogoImage: NSImage? = makeRecordingLogoImage()

    private static func makeRecordingLogoImage() -> NSImage? {
        guard let url = Bundle.main.url(forResource: "logo-avatar", withExtension: "svg"),
              let avatar = NSImage(contentsOf: url)
        else {
            return nil
        }

        avatar.size = NSSize(width: 18, height: 18)

        let image = NSImage(size: NSSize(width: 22, height: 18))
        image.lockFocus()
        avatar.draw(
            in: NSRect(x: 0, y: 0, width: 18, height: 18),
            from: .zero,
            operation: .sourceOver,
            fraction: 1
        )

        NSColor.white.setFill()
        NSBezierPath(ovalIn: NSRect(x: 12.5, y: 0.5, width: 10, height: 10)).fill()
        NSColor.systemRed.setFill()
        NSBezierPath(ovalIn: NSRect(x: 14, y: 2, width: 7, height: 7)).fill()
        image.unlockFocus()

        image.isTemplate = false
        return image
    }
}

struct VoiceLevelOverlayView: View {
    @ObservedObject var meter: VoiceLevelMeter

    var body: some View {
        HStack(alignment: .center, spacing: 3.5) {
            ForEach(Array(meter.amplitudes.enumerated()), id: \.offset) { _, amplitude in
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.18, green: 0.82, blue: 0.92),
                                Color(red: 0.64, green: 0.96, blue: 0.58)
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(width: 3.5, height: max(5, 25 * amplitude))
                    .animation(.easeOut(duration: 0.08), value: amplitude)
            }
        }
        .frame(width: 147, height: 38)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.white.opacity(0.22), lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(0.24), radius: 13, y: 6)
        .accessibilityLabel(Text("Voice level"))
    }
}

final class VoiceLevelOverlayController {
    static let shared = VoiceLevelOverlayController()

    private let panelSize = NSSize(width: 154, height: 41)
    private var panel: NSPanel?

    private init() {}

    func show() {
        let panel = panel ?? makePanel()
        self.panel = panel
        position(panel)
        VoiceLevelMeter.shared.start()
        panel.orderFrontRegardless()
    }

    func hide() {
        VoiceLevelMeter.shared.stop()
        panel?.orderOut(nil)
    }

    private func makePanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.contentView = NSHostingView(rootView: VoiceLevelOverlayView(meter: VoiceLevelMeter.shared))
        return panel
    }

    private func position(_ panel: NSPanel) {
        guard let screen = NSScreen.main ?? NSScreen.screens.first else { return }
        let frame = screen.visibleFrame
        panel.setFrameOrigin(
            NSPoint(
                x: frame.midX - panelSize.width / 2,
                y: frame.minY + 38
            )
        )
    }
}

final class VoiceLevelMeter: NSObject, ObservableObject {
    static let shared = VoiceLevelMeter()

    @Published private(set) var amplitudes = VoiceLevelMeter.idleAmplitudes

    private static let barCount = 16
    private static let idleAmplitudes = Array(repeating: CGFloat(0.16), count: barCount)
    private let minimumPower: Float = -55
    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private var phase = 0.0

    private override init() {}

    func start() {
        guard recorder == nil else { return }

        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            startMetering()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        self?.startMetering()
                    } else {
                        self?.amplitudes = Self.idleAmplitudes
                    }
                }
            }
        default:
            amplitudes = Self.idleAmplitudes
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        recorder?.stop()
        recorder = nil
        amplitudes = Self.idleAmplitudes
    }

    private func startMetering() {
        let url = URL(fileURLWithPath: "/dev/null")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatAppleLossless),
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.min.rawValue
        ]

        do {
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.isMeteringEnabled = true
            guard recorder.record() else {
                amplitudes = Self.idleAmplitudes
                return
            }
            self.recorder = recorder
            timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
                self?.updateMeter()
            }
        } catch {
            amplitudes = Self.idleAmplitudes
        }
    }

    private func updateMeter() {
        guard let recorder else { return }
        recorder.updateMeters()

        let power = recorder.averagePower(forChannel: 0)
        let normalized = Self.normalizedPower(power, minimumPower: minimumPower)
        phase += 0.32

        amplitudes = (0..<Self.barCount).map { index in
            let wave = 0.72 + 0.28 * sin(phase + Double(index) * 0.85)
            return max(0.12, min(1, normalized * CGFloat(wave)))
        }
    }

    private static func normalizedPower(_ power: Float, minimumPower: Float) -> CGFloat {
        guard power > minimumPower else { return 0.08 }
        return CGFloat((power - minimumPower) / abs(minimumPower))
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        AgentRuntime.shared.runSelfTestIfRequested()
        NSApp.setActivationPolicy(.accessory)
        UNUserNotificationCenter.current().delegate = self
        configureNotifications()
        ShortcutDefaultsMigrator.migrate()
        ConfigurableHotkeyController.shared.registerDefaultHotkeys(runner: AgentCommandRunner.shared)
        ShortcutSummaryState.shared.refresh()
    }

    func applicationWillTerminate(_ notification: Notification) {
        VoiceLevelOverlayController.shared.hide()
    }

    private func configureNotifications() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            switch settings.authorizationStatus {
            case .notDetermined:
                center.requestAuthorization(options: [.alert]) { granted, _ in
                    if !granted {
                        DispatchQueue.main.async {
                            AgentCommandRunner.shared.notificationsDisabled()
                        }
                    }
                }
            case .denied:
                DispatchQueue.main.async {
                    AgentCommandRunner.shared.notificationsDisabled()
                }
            default:
                break
            }
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list])
    }
}

extension KeyboardShortcuts.Name {
    static let toggleTranscription = Self(
        "toggleTranscription",
        default: KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)
    )
    static let holdToTranscribe = Self(
        "holdToTranscribe",
        default: KeyboardShortcuts.Shortcut(.function)
    )
    static let autocorrect = Self(
        "autocorrect",
        default: KeyboardShortcuts.Shortcut(.a, modifiers: [.command, .shift])
    )
    static let voiceEdit = Self(
        "voiceEdit",
        default: KeyboardShortcuts.Shortcut(.v, modifiers: [.command, .shift])
    )
}

final class ShortcutSummaryState: ObservableObject {
    static let shared = ShortcutSummaryState()

    @Published private(set) var summary = ""

    private init() {
        refresh()
    }

    func refresh() {
        summary = Self.makeSummary()
    }

    func resetDefaults() {
        KeyboardShortcuts.reset(
            .toggleTranscription,
            .holdToTranscribe,
            .autocorrect,
            .voiceEdit
        )
        refresh()
    }

    private static func makeSummary() -> String {
        let shortcuts: [(label: String, name: KeyboardShortcuts.Name)] = [
            ("Toggle", .toggleTranscription),
            ("Hold", .holdToTranscribe),
            ("Autocorrect", .autocorrect),
            ("Voice Edit", .voiceEdit)
        ]

        return "Hotkeys: " + shortcuts
            .map { "\($0.label) \(label(for: $0.name))" }
            .joined(separator: " / ")
    }

    private static func label(for name: KeyboardShortcuts.Name) -> String {
        ShortcutDisplay.label(for: name)
    }
}

private enum ShortcutDisplay {
    static func label(for name: KeyboardShortcuts.Name) -> String {
        guard let shortcut = KeyboardShortcuts.getShortcut(for: name) else {
            return "Not Set"
        }

        return label(
            for: shortcut,
            fallback: KeyboardShortcuts.getShortcut(for: name)?.description ?? "Not Set"
        )
    }

    static func shortcut(from event: NSEvent) -> KeyboardShortcuts.Shortcut? {
        if event.type == .flagsChanged,
           Int(event.keyCode) == kVK_Function,
           event.modifierFlags.contains(.function) {
            return KeyboardShortcuts.Shortcut(.function)
        }

        guard let shortcut = KeyboardShortcuts.Shortcut(event: event) else {
            return nil
        }

        var carbonModifiers = shortcut.carbonModifiers
        if event.modifierFlags.contains(.function) {
            carbonModifiers |= kEventKeyModifierFnMask
        }
        return KeyboardShortcuts.Shortcut(
            carbonKeyCode: shortcut.carbonKeyCode,
            carbonModifiers: carbonModifiers
        )
    }

    private static func label(for shortcut: KeyboardShortcuts.Shortcut, fallback: String) -> String {
        if shortcut.carbonKeyCode == kVK_Function, shortcut.carbonModifiers == 0 {
            return "Fn"
        }

        guard shortcut.carbonModifiers & kEventKeyModifierFnMask != 0 else {
            return fallback
        }

        let remainingModifiers = shortcut.carbonModifiers & ~kEventKeyModifierFnMask
        let displayShortcut = KeyboardShortcuts.Shortcut(
            carbonKeyCode: shortcut.carbonKeyCode,
            carbonModifiers: remainingModifiers
        )
        return "Fn+\(keyLabel(for: displayShortcut))"
    }

    private static func keyLabel(for shortcut: KeyboardShortcuts.Shortcut) -> String {
        if shortcut.carbonKeyCode == kVK_Space {
            return "Space"
        }
        return shortcut.description
    }
}

private enum ShortcutDefaultsMigrator {
    static func migrate() {
        migrateDefault(
            name: .toggleTranscription,
            from: KeyboardShortcuts.Shortcut(.r, modifiers: [.command, .shift]),
            to: KeyboardShortcuts.Shortcut(carbonKeyCode: kVK_Space, carbonModifiers: kEventKeyModifierFnMask)
        )
        migrateDefault(
            name: .holdToTranscribe,
            from: KeyboardShortcuts.Shortcut(.space, modifiers: [.control, .option]),
            to: KeyboardShortcuts.Shortcut(.function)
        )
    }

    private static func migrateDefault(
        name: KeyboardShortcuts.Name,
        from oldShortcut: KeyboardShortcuts.Shortcut,
        to newShortcut: KeyboardShortcuts.Shortcut
    ) {
        guard KeyboardShortcuts.getShortcut(for: name) == oldShortcut else {
            return
        }
        KeyboardShortcuts.setShortcut(newShortcut, for: name)
    }
}

struct SettingsView: View {
    @State private var shortcutRevision = 0

    var body: some View {
        Form {
            Section {
                ShortcutRecorderRow(
                    title: "Toggle Transcription",
                    name: .toggleTranscription,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Hold to Transcribe",
                    name: .holdToTranscribe,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Autocorrect Clipboard",
                    name: .autocorrect,
                    revision: shortcutRevision
                )
                ShortcutRecorderRow(
                    title: "Voice Edit Clipboard",
                    name: .voiceEdit,
                    revision: shortcutRevision
                )

                Button("Reset Defaults") {
                    ShortcutSummaryState.shared.resetDefaults()
                    shortcutRevision += 1
                }
            } header: {
                Text("Keyboard Shortcuts")
            } footer: {
                Text("Defaults: Fn+Space, Fn, Cmd+Shift+A, Cmd+Shift+V. Click a shortcut field and press a new key combination. Press Delete to clear it or Escape to cancel.")
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

struct ShortcutRecorderRow: View {
    let title: String
    let name: KeyboardShortcuts.Name
    let revision: Int

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            ShortcutRecorder(name: name, revision: revision)
                .frame(width: 150)
        }
    }
}

struct ShortcutRecorder: NSViewRepresentable {
    let name: KeyboardShortcuts.Name
    let revision: Int

    func makeNSView(context: Context) -> ShortcutRecorderButton {
        ShortcutRecorderButton(name: name)
    }

    func updateNSView(_ nsView: ShortcutRecorderButton, context: Context) {
        _ = revision
        nsView.shortcutName = name
        nsView.updateTitle()
    }
}

final class ShortcutRecorderButton: NSButton {
    var shortcutName: KeyboardShortcuts.Name {
        didSet {
            updateTitle()
        }
    }

    private var isRecording = false
    private var eventMonitor: Any?

    init(name: KeyboardShortcuts.Name) {
        self.shortcutName = name
        super.init(frame: .zero)
        bezelStyle = .rounded
        controlSize = .regular
        target = self
        action = #selector(startRecording)
        updateTitle()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        stopRecording()
    }

    override func viewWillMove(toWindow newWindow: NSWindow?) {
        super.viewWillMove(toWindow: newWindow)
        if newWindow == nil {
            stopRecording()
        }
    }

    func updateTitle() {
        guard !isRecording else { return }
        title = ShortcutDisplay.label(for: shortcutName)
    }

    @objc private func startRecording() {
        guard !isRecording else {
            stopRecording()
            return
        }

        isRecording = true
        title = "Press shortcut"
        window?.makeFirstResponder(self)

        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .flagsChanged]) { [weak self] event in
            guard let self, self.isRecording else {
                return event
            }
            self.capture(event)
            return nil
        }
    }

    private func capture(_ event: NSEvent) {
        switch Int(event.keyCode) {
        case kVK_Escape:
            stopRecording()
        case kVK_Delete, kVK_ForwardDelete:
            KeyboardShortcuts.setShortcut(nil, for: shortcutName)
            stopRecording()
        default:
            guard let shortcut = ShortcutDisplay.shortcut(from: event) else {
                NSSound.beep()
                return
            }
            KeyboardShortcuts.setShortcut(shortcut, for: shortcutName)
            stopRecording()
        }
    }

    private func stopRecording() {
        if let eventMonitor {
            NSEvent.removeMonitor(eventMonitor)
            self.eventMonitor = nil
        }
        isRecording = false
        updateTitle()
        ShortcutSummaryState.shared.refresh()
    }
}

struct AgentCommand {
    let identifier: String
    let title: String
    let shell: String
    let forceBootstrap: Bool
    let requiresWhisperDaemon: Bool
    let showsRecordingIndicator: Bool
    let startNotificationTitle: String?
    let startNotificationBody: String?
    let finishNotificationTitle: String?

    init(
        identifier: String,
        title: String,
        shell: String,
        forceBootstrap: Bool = false,
        requiresWhisperDaemon: Bool = false,
        showsRecordingIndicator: Bool = false,
        startNotificationTitle: String? = nil,
        startNotificationBody: String? = nil,
        finishNotificationTitle: String? = nil
    ) {
        self.identifier = identifier
        self.title = title
        self.shell = shell
        self.forceBootstrap = forceBootstrap
        self.requiresWhisperDaemon = requiresWhisperDaemon
        self.showsRecordingIndicator = showsRecordingIndicator
        self.startNotificationTitle = startNotificationTitle
        self.startNotificationBody = startNotificationBody
        self.finishNotificationTitle = finishNotificationTitle
    }

    static let toggleTranscription = AgentCommand(
        identifier: "transcribe",
        title: "Toggle Transcription",
        shell: #""$AGENTCLI_AGENT_CLI" transcribe --toggle --quiet"#,
        requiresWhisperDaemon: true,
        showsRecordingIndicator: true,
        startNotificationTitle: "Transcription Started",
        startNotificationBody: "Recording audio. Toggle transcription again to stop and transcribe.",
        finishNotificationTitle: "Transcription Finished"
    )

    static let voiceEdit = AgentCommand(
        identifier: "voice-edit",
        title: "Voice Edit Clipboard",
        shell: #""$AGENTCLI_AGENT_CLI" voice-edit --toggle --quiet"#,
        requiresWhisperDaemon: true,
        showsRecordingIndicator: true,
        startNotificationTitle: "Voice Edit Started",
        startNotificationBody: "Recording audio. Toggle voice edit again to stop.",
        finishNotificationTitle: "Voice Edit Finished"
    )

    static let autocorrect = AgentCommand(
        identifier: "autocorrect",
        title: "Autocorrect Clipboard",
        shell: #""$AGENTCLI_AGENT_CLI" autocorrect --quiet"#
    )

    static let voiceServiceStatus = AgentCommand(
        identifier: "voice-service-status",
        title: "Voice Service Status",
        shell: #""$AGENTCLI_AGENT_CLI" daemon status whisper --logs 0"#
    )

    static let installVoiceService = AgentCommand(
        identifier: "install-voice-service",
        title: "Install Voice Service",
        shell: #""$AGENTCLI_AGENT_CLI" daemon install whisper -y"#
    )

    static let installOrUpdateCLI = AgentCommand(
        identifier: "install-or-update-cli",
        title: "Install or Update CLI",
        shell: #""$AGENTCLI_AGENT_CLI" --version"#,
        forceBootstrap: true
    )
}

struct AgentRuntime {
    static let shared = AgentRuntime()

    private static let bundledUVRelativePath = "Contents/Resources/bin/uv"
    private static let bundledWheelsRelativePath = "Contents/Resources/wheels"
    private static let appSupportDisplayName = "Application Support"
    private static let fallbackPackageSource = "agent-cli"
    private let fileManager = FileManager.default
    let appSupportURL: URL
    let bundledUVURL: URL
    let bundledWheelsURL: URL
    let agentCLIPackageSource: String
    let agentCLIInstallRequirement: String
    let binURL: URL
    let agentCLIURL: URL
    let whisperDaemonMarkerURL: URL
    let notificationLogoURL: URL?
    let lastErrorURL: URL
    let logsURL: URL

    init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundle: Bundle = .main
    ) {
        if let override = environment["AGENTCLI_APP_SUPPORT_DIR"], !override.isEmpty {
            appSupportURL = URL(fileURLWithPath: override, isDirectory: true)
        } else {
            let baseURL = FileManager.default.urls(
                for: .applicationSupportDirectory,
                in: .userDomainMask
            )[0]
            appSupportURL = baseURL.appendingPathComponent("AgentCLI", isDirectory: true)
        }

        bundledUVURL = bundle.bundleURL.appendingPathComponent(Self.bundledUVRelativePath)
        bundledWheelsURL = bundle.bundleURL.appendingPathComponent(Self.bundledWheelsRelativePath)
        agentCLIPackageSource = Self.resolveBundledWheel(in: bundledWheelsURL) ?? Self.fallbackPackageSource
        agentCLIInstallRequirement = "\(agentCLIPackageSource)[audio,llm]"
        binURL = appSupportURL.appendingPathComponent("bin", isDirectory: true)
        agentCLIURL = binURL.appendingPathComponent("agent-cli")
        whisperDaemonMarkerURL = appSupportURL.appendingPathComponent(".whisper-daemon-installed")
        notificationLogoURL = bundle.url(forResource: "logo-avatar", withExtension: "png")
        lastErrorURL = appSupportURL.appendingPathComponent("last-error.txt")
        logsURL = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs", isDirectory: true)
    }

    private static func resolveBundledWheel(in wheelsURL: URL) -> String? {
        let wheelURLs = (try? FileManager.default.contentsOfDirectory(
            at: wheelsURL,
            includingPropertiesForKeys: nil
        )) ?? []

        return wheelURLs
            .filter {
                $0.lastPathComponent.hasPrefix("agent_cli-")
                    && $0.pathExtension == "whl"
            }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .last?
            .path
    }

    func runSelfTestIfRequested() {
        if CommandLine.arguments.contains("--agentcli-self-test") {
            do {
                try prepareDirectories()
                guard fileManager.isExecutableFile(atPath: bundledUVURL.path) else {
                    print("Bundled uv is missing or not executable: \(bundledUVURL.path)")
                    exit(1)
                }
                print("AgentCLI self-test ok")
                print("location=\(Self.appSupportDisplayName)")
                print("appSupport=\(appSupportURL.path)")
                print("uv=\(bundledUVURL.path)")
                print("packageSource=\(agentCLIPackageSource)")
                print("agentCLI=\(agentCLIURL.path)")
                print("notificationLogo=\(notificationLogoURL?.path ?? "missing")")
                exit(0)
            } catch {
                print("AgentCLI self-test failed: \(error.localizedDescription)")
                exit(1)
            }
        }

        guard CommandLine.arguments.contains("--agentcli-bootstrap-self-test") else { return }

        let bootstrap = ensureTranscriptionReady(force: true)
        guard bootstrap.exitCode == 0 else {
            print("AgentCLI bootstrap self-test failed: \(bootstrap.output)")
            exit(1)
        }

        let transcription = runShell(AgentCommand.toggleTranscription.shell)
        guard transcription.exitCode == 0 else {
            print("AgentCLI transcription self-test failed: \(transcription.output)")
            exit(1)
        }

        print("AgentCLI bootstrap self-test ok")
        if !bootstrap.output.isEmpty {
            print(bootstrap.output)
        }
        if !transcription.output.isEmpty {
            print(transcription.output)
        }
        exit(0)
    }

    func ensureInstalled(force: Bool = false) -> CommandResult {
        do {
            try prepareDirectories()
        } catch {
            return CommandResult(exitCode: 1, output: "Could not create app support directories: \(error.localizedDescription)")
        }

        if !force, fileManager.isExecutableFile(atPath: agentCLIURL.path) {
            return CommandResult(exitCode: 0, output: "")
        }

        guard fileManager.isExecutableFile(atPath: bundledUVURL.path) else {
            return CommandResult(
                exitCode: 127,
                output: "Bundled uv is missing or not executable: \(bundledUVURL.path)"
            )
        }

        let installDescription = "uv tool install agent-cli[audio,llm]"
        let result = Self.runProcess(
            executableURL: bundledUVURL,
            arguments: [
                "tool",
                "install",
                "--managed-python",
                "--python",
                "3.13",
                "--force",
                agentCLIInstallRequirement
            ],
            environment: commandEnvironment()
        )
        if result.exitCode != 0, result.output.isEmpty {
            return CommandResult(exitCode: result.exitCode, output: "\(installDescription) failed")
        }
        return result
    }

    func ensureTranscriptionReady(force: Bool = false) -> CommandResult {
        let installResult = ensureInstalled(force: force)
        guard installResult.exitCode == 0 else {
            return installResult
        }
        return ensureWhisperDaemon(force: force)
    }

    private func ensureWhisperDaemon(force: Bool = false) -> CommandResult {
        let whisperDaemonMarkerContents = "packageSource=\(agentCLIPackageSource)\n"
        if !force, (try? String(contentsOf: whisperDaemonMarkerURL)) == whisperDaemonMarkerContents {
            return waitForWhisperDaemonReady()
        }

        let result = runShell(#""$AGENTCLI_AGENT_CLI" daemon install whisper -y"#)
        guard result.exitCode == 0 else {
            return result
        }

        try? whisperDaemonMarkerContents.write(
            to: whisperDaemonMarkerURL,
            atomically: true,
            encoding: .utf8
        )
        return waitForWhisperDaemonReady()
    }

    private func waitForWhisperDaemonReady(timeout: TimeInterval = 180) -> CommandResult {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if Self.canConnectToLocalhost(port: 10300) {
                return CommandResult(exitCode: 0, output: "")
            }
            Thread.sleep(forTimeInterval: 0.5)
        }

        let status = runShell(#""$AGENTCLI_AGENT_CLI" daemon status whisper --logs 80"#)
        let statusOutput = status.output.trimmingCharacters(in: .whitespacesAndNewlines)
        let output = statusOutput.isEmpty
            ? "Whisper ASR service did not become ready at localhost:10300."
            : "Whisper ASR service did not become ready at localhost:10300.\n\n\(statusOutput)"
        return CommandResult(exitCode: 1, output: output)
    }

    private static func canConnectToLocalhost(port: UInt16) -> Bool {
        let socketFD = socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else {
            return false
        }
        defer { close(socketFD) }

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian

        guard inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) == 1 else {
            return false
        }

        return withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                connect(socketFD, socketAddress, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }

    func commandEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["AGENTCLI_APP_SUPPORT_DIR"] = appSupportURL.path
        environment["AGENTCLI_AGENT_CLI"] = agentCLIURL.path
        environment["AGENTCLI_BUNDLED_UV"] = bundledUVURL.path
        environment["AGENTCLI_PACKAGE_SOURCE"] = agentCLIPackageSource
        environment["AGENT_CLI_CONFIG_HOME"] = appSupportURL.appendingPathComponent("config", isDirectory: true).path
        environment["UV_CACHE_DIR"] = appSupportURL.appendingPathComponent("cache/uv", isDirectory: true).path
        environment["UV_PYTHON_INSTALL_DIR"] = appSupportURL.appendingPathComponent("uv/python", isDirectory: true).path
        environment["UV_PYTHON_BIN_DIR"] = binURL.path
        environment["UV_TOOL_DIR"] = appSupportURL.appendingPathComponent("uv/tools", isDirectory: true).path
        environment["UV_TOOL_BIN_DIR"] = binURL.path
        environment["UV_NO_PROGRESS"] = "1"
        environment["NO_COLOR"] = "1"
        environment["TERM"] = "dumb"

        let resourceBinURL = bundledUVURL.deletingLastPathComponent()
        let existingPATH = environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        environment["PATH"] = [
            binURL.path,
            resourceBinURL.path,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            existingPATH
        ].joined(separator: ":")

        return environment
    }

    private func prepareDirectories() throws {
        try fileManager.createDirectory(at: binURL, withIntermediateDirectories: true)
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("cache/uv", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("uv/python", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("uv/tools", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: appSupportURL.appendingPathComponent("config", isDirectory: true),
            withIntermediateDirectories: true
        )
    }

    func runShell(_ shell: String) -> CommandResult {
        Self.runProcess(
            executableURL: URL(fileURLWithPath: "/bin/zsh"),
            arguments: ["-lc", shell],
            environment: commandEnvironment()
        )
    }

    static func runProcess(
        executableURL: URL,
        arguments: [String],
        environment: [String: String]
    ) -> CommandResult {
        let task = Process()
        let pipe = Pipe()

        task.executableURL = executableURL
        task.arguments = arguments
        task.environment = environment
        task.standardOutput = pipe
        task.standardError = pipe

        do {
            try task.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            task.waitUntilExit()
            return CommandResult(
                exitCode: task.terminationStatus,
                output: String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            )
        } catch {
            return CommandResult(exitCode: 127, output: error.localizedDescription)
        }
    }
}

final class AgentCommandRunner: ObservableObject {
    static let shared = AgentCommandRunner()

    @Published var statusMessage = "Ready"
    @Published var lastOutput = ""
    @Published private(set) var hasLastError = false
    @Published private(set) var isRecording = false
    @Published private var activeCommandCount = 0
    private var recordingCommandCount = 0
    private var activeRecordingCommands: [String: Int] = [:]
    private var pendingStopRecordingCommands: Set<String> = []
    private var holdToTranscribeActive = false
    private var pendingHoldToTranscribeStop = false
    private var holdStopRequestActive = false
    private var holdToTranscribePasteTarget: FocusedTextTarget?
    private var pasteAfterRecordingCommands: Set<String> = []
    private var didRequestAccessibilityPermission = false

    var isRunning: Bool {
        activeCommandCount > 0
    }

    private init() {
        hasLastError = FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path)
    }

    private static let notificationSettingsURLs: [URL] = [
        URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!,
        URL(string: "x-apple.systempreferences:com.apple.preference.notifications")!
    ]
    private static let holdStopShell = #"for attempt in {1..3000}; do if [ -s "$HOME/.cache/agent-cli/transcribe.pid" ]; then "$AGENTCLI_AGENT_CLI" transcribe --stop --quiet; exit $?; fi; sleep 0.1; done; "$AGENTCLI_AGENT_CLI" transcribe --stop --quiet"#

    func beginHoldToTranscribe() {
        guard !holdToTranscribeActive else { return }
        guard !pendingHoldToTranscribeStop, !holdStopRequestActive else {
            statusMessage = "Finishing previous hold-to-transcribe request"
            return
        }
        guard !isRecordingCommand(.toggleTranscription), !isStopPending(for: .toggleTranscription) else {
            statusMessage = "Transcription is already recording"
            return
        }

        holdToTranscribeActive = true
        holdToTranscribePasteTarget = FocusedTextTarget.capture()
        pasteAfterRecordingCommands.insert(AgentCommand.toggleTranscription.identifier)
        run(.toggleTranscription)
    }

    func endHoldToTranscribe() {
        guard holdToTranscribeActive else { return }
        holdToTranscribeActive = false
        pendingHoldToTranscribeStop = true

        if isRecordingCommand(.toggleTranscription) {
            stopHeldTranscriptionWhenReady()
        } else {
            statusMessage = "Stopping transcription as soon as it starts..."
        }
    }

    func run(_ command: AgentCommand) {
        let isStopRequest = command.showsRecordingIndicator && isRecordingCommand(command)
        let shouldStartRecording = command.showsRecordingIndicator && !isStopRequest

        if isStopRequest && isStopPending(for: command) {
            statusMessage = "Stop already requested for \(command.title)"
            return
        }

        if isStopRequest {
            markStopRequested(for: command)
        }

        activeCommandCount += 1
        statusMessage = isStopRequest
            ? "Stopping \(command.title)..."
            : "Running \(command.title)..."

        DispatchQueue.global(qos: .userInitiated).async {
            let bootstrap = command.requiresWhisperDaemon
                ? AgentRuntime.shared.ensureTranscriptionReady(force: command.forceBootstrap)
                : AgentRuntime.shared.ensureInstalled(force: command.forceBootstrap)
            guard bootstrap.exitCode == 0 else {
                let message = Self.statusMessage(for: command, result: bootstrap)
                let notificationTitle = Self.notificationTitle(for: command, result: bootstrap)
                let notificationBody = Self.notificationBody(for: command, result: bootstrap, statusMessage: message)
                DispatchQueue.main.async {
                    if isStopRequest {
                        self.clearStopRequested(for: command)
                    }
                    if shouldStartRecording {
                        self.clearPasteAfterRecording(for: command)
                    }
                    self.pendingHoldToTranscribeStop = false
                    self.holdStopRequestActive = false
                    self.activeCommandCount = max(0, self.activeCommandCount - 1)
                    self.lastOutput = bootstrap.output
                    self.recordFailure(command: command, result: bootstrap)
                    self.statusMessage = message
                    self.notify(title: notificationTitle, body: notificationBody)
                }
                return
            }

            if shouldStartRecording {
                DispatchQueue.main.async {
                    self.beginRecordingIndicator(for: command)
                    self.notifyStart(for: command)
                }
            }

            let result = Self.execute(command.shell)
            let message = Self.statusMessage(for: command, result: result)
            let notificationTitle = Self.notificationTitle(for: command, result: result)
            let notificationBody = Self.notificationBody(for: command, result: result, statusMessage: message)

            DispatchQueue.main.async {
                if shouldStartRecording {
                    let shouldPaste = self.shouldPasteAfterRecording(for: command) && result.exitCode == 0
                    let pasteTarget = self.holdToTranscribePasteTarget
                    self.endRecordingIndicator(for: command)
                    self.clearStopRequested(for: command)
                    if shouldPaste {
                        self.pasteTranscriptIntoFocusedField(result.output, for: command, target: pasteTarget)
                    }
                    self.clearPasteAfterRecording(for: command)
                }
                self.activeCommandCount = max(0, self.activeCommandCount - 1)

                if isStopRequest && result.exitCode == 0 {
                    if !result.output.isEmpty {
                        self.lastOutput = result.output
                    }
                    self.statusMessage = "Stop requested for \(command.title)"
                    return
                }

                if isStopRequest {
                    self.clearStopRequested(for: command)
                }
                self.lastOutput = result.output
                if result.exitCode != 0 {
                    self.recordFailure(command: command, result: result)
                }
                self.statusMessage = message
                self.notify(title: notificationTitle, body: notificationBody)
            }
        }
    }

    private func notifyStart(for command: AgentCommand) {
        guard let title = command.startNotificationTitle else { return }
        notify(title: title, body: command.startNotificationBody ?? "")
    }

    private func stopHeldTranscriptionWhenReady() {
        guard pendingHoldToTranscribeStop, !holdStopRequestActive else { return }

        holdStopRequestActive = true
        statusMessage = "Stopping Toggle Transcription..."

        DispatchQueue.global(qos: .userInitiated).async {
            let result = Self.execute(Self.holdStopShell)

            DispatchQueue.main.async {
                self.pendingHoldToTranscribeStop = false
                self.holdStopRequestActive = false

                if result.exitCode == 0 {
                    self.statusMessage = "Stop requested for Toggle Transcription"
                    return
                }

                let message = result.output.isEmpty
                    ? "Toggle Transcription stop failed with exit code \(result.exitCode)"
                    : "Toggle Transcription stop failed: \(result.output)"
                self.lastOutput = result.output
                self.recordFailure(title: "Toggle Transcription Stop", result: result)
                self.statusMessage = message
                self.notify(title: "Toggle Transcription Failed", body: Self.errorNotificationBody(message))
            }
        }
    }

    private func isRecordingCommand(_ command: AgentCommand) -> Bool {
        activeRecordingCommands[command.identifier, default: 0] > 0
    }

    private func isStopPending(for command: AgentCommand) -> Bool {
        pendingStopRecordingCommands.contains(command.identifier)
    }

    private func markStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.insert(command.identifier)
    }

    private func clearStopRequested(for command: AgentCommand) {
        pendingStopRecordingCommands.remove(command.identifier)
    }

    private func shouldPasteAfterRecording(for command: AgentCommand) -> Bool {
        pasteAfterRecordingCommands.contains(command.identifier)
    }

    private func clearPasteAfterRecording(for command: AgentCommand) {
        pasteAfterRecordingCommands.remove(command.identifier)
        if command.identifier == AgentCommand.toggleTranscription.identifier {
            holdToTranscribePasteTarget = nil
        }
    }

    private func beginRecordingIndicator(for command: AgentCommand) {
        activeRecordingCommands[command.identifier, default: 0] += 1
        recordingCommandCount += 1
        isRecording = true
        VoiceLevelOverlayController.shared.show()
        if command.identifier == AgentCommand.toggleTranscription.identifier {
            stopHeldTranscriptionWhenReady()
        }
    }

    private func endRecordingIndicator(for command: AgentCommand) {
        let activeCommandCount = max(0, activeRecordingCommands[command.identifier, default: 0] - 1)
        if activeCommandCount > 0 {
            activeRecordingCommands[command.identifier] = activeCommandCount
        } else {
            activeRecordingCommands.removeValue(forKey: command.identifier)
        }
        recordingCommandCount = max(0, recordingCommandCount - 1)
        isRecording = recordingCommandCount > 0
        if !isRecording {
            VoiceLevelOverlayController.shared.hide()
        }
    }

    private func pasteTranscriptIntoFocusedField(
        _ transcript: String,
        for command: AgentCommand,
        target: FocusedTextTarget?
    ) {
        _ = command

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(transcript, forType: .string)

        guard AXIsProcessTrusted() else {
            requestAccessibilityPermissionIfNeeded()
            statusMessage = "Transcript copied. Allow Accessibility permission to auto-insert text."
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            if target?.insertText(transcript) == true {
                self.statusMessage = "Inserted transcript"
                return
            }
            self.postPasteShortcut(to: target?.pid)
        }
    }

    private func postPasteShortcut(to pid: pid_t?) {
        let source = CGEventSource(stateID: .hidSystemState)
        let commandDown = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_Command), keyDown: true)
        let commandUp = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_Command), keyDown: false)
        let keyDown = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_V), keyDown: true)
        let keyUp = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(kVK_ANSI_V), keyDown: false)
        commandDown?.flags = .maskCommand
        keyDown?.flags = .maskCommand
        keyUp?.flags = .maskCommand

        if let pid, pid > 0 {
            commandDown?.postToPid(pid)
            keyDown?.postToPid(pid)
            keyUp?.postToPid(pid)
            commandUp?.postToPid(pid)
        } else {
            commandDown?.post(tap: .cghidEventTap)
            keyDown?.post(tap: .cghidEventTap)
            keyUp?.post(tap: .cghidEventTap)
            commandUp?.post(tap: .cghidEventTap)
        }
    }

    private func requestAccessibilityPermissionIfNeeded() {
        guard !didRequestAccessibilityPermission else {
            return
        }
        didRequestAccessibilityPermission = true

        // Equivalent to kAXTrustedCheckOptionPrompt as String, but Swift exposes it unmanaged.
        let promptOption = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let options = [promptOption: true] as CFDictionary
        AXIsProcessTrustedWithOptions(options)
    }

    func copyLastOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(lastOutput, forType: .string)
        statusMessage = "Copied last output"
    }

    func openLastError() {
        guard FileManager.default.fileExists(atPath: AgentRuntime.shared.lastErrorURL.path) else {
            hasLastError = false
            statusMessage = "No last error recorded"
            return
        }

        if NSWorkspace.shared.open(AgentRuntime.shared.lastErrorURL) {
            statusMessage = "Opened last error"
        } else {
            statusMessage = "Could not open last error"
        }
    }

    func copyLastError() {
        guard let details = try? String(contentsOf: AgentRuntime.shared.lastErrorURL),
              !details.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            hasLastError = false
            statusMessage = "No last error recorded"
            return
        }

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(details, forType: .string)
        statusMessage = "Copied last error"
    }

    func openLogsFolder() {
        let url = AgentRuntime.shared.logsURL

        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            if NSWorkspace.shared.open(url) {
                statusMessage = "Opened logs folder"
            } else {
                statusMessage = "Could not open logs folder"
            }
        } catch {
            statusMessage = "Could not open logs folder: \(error.localizedDescription)"
        }
    }

    func openConfigFolder() {
        let url = AgentRuntime.shared.appSupportURL.appendingPathComponent("config", isDirectory: true)

        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            NSWorkspace.shared.open(url)
            statusMessage = "Opened config folder"
        } catch {
            statusMessage = "Could not open config folder: \(error.localizedDescription)"
        }
    }

    func notificationsDisabled() {
        statusMessage = "Notifications are disabled. Use Open Notification Settings to enable Agent CLI notifications."
    }

    func openNotificationSettings() {
        for url in Self.notificationSettingsURLs where NSWorkspace.shared.open(url) {
            statusMessage = "Opened Notification Settings"
            return
        }
        statusMessage = "Could not open Notification Settings"
    }

    private static func execute(_ shell: String) -> CommandResult {
        AgentRuntime.shared.runShell(shell)
    }

    @discardableResult
    private func recordFailure(command: AgentCommand, result: CommandResult) -> String {
        recordFailure(title: command.title, result: result)
    }

    @discardableResult
    private func recordFailure(title: String, result: CommandResult) -> String {
        let output = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
        let details = """
        Agent CLI Error
        Time: \(ISO8601DateFormatter().string(from: Date()))
        Context: \(title)
        Exit code: \(result.exitCode)

        Output:
        \(output.isEmpty ? "(no output)" : output)
        """

        do {
            try FileManager.default.createDirectory(
                at: AgentRuntime.shared.appSupportURL,
                withIntermediateDirectories: true
            )
            try details.write(to: AgentRuntime.shared.lastErrorURL, atomically: true, encoding: .utf8)
            hasLastError = true
        } catch {
            lastOutput = details
            hasLastError = false
        }

        return details
    }

    private static func statusMessage(for command: AgentCommand, result: CommandResult) -> String {
        let summary = summarize(result.output)
        if result.exitCode == 0 {
            return summary.isEmpty ? "\(command.title) finished" : summary
        }
        return summary.isEmpty
            ? "\(command.title) failed with exit code \(result.exitCode)"
            : "\(command.title) failed: \(summary)"
    }

    private static func notificationTitle(for command: AgentCommand, result: CommandResult) -> String {
        if result.exitCode == 0 {
            return command.finishNotificationTitle ?? command.title
        }
        return "\(command.title) Failed"
    }

    private static func notificationBody(
        for command: AgentCommand,
        result: CommandResult,
        statusMessage: String
    ) -> String {
        if result.exitCode != 0 {
            return errorNotificationBody(statusMessage)
        }

        if command.finishNotificationTitle != nil, result.exitCode == 0 {
            let transcript = result.output.trimmingCharacters(in: .whitespacesAndNewlines)
            if !transcript.isEmpty {
                return transcript
            }
        }
        return statusMessage
    }

    private static func errorNotificationBody(_ statusMessage: String) -> String {
        "\(statusMessage)\nFull error saved. Open Agent CLI > Open Last Error for details."
    }

    private static func summarize(_ output: String) -> String {
        output
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .suffix(4)
            .joined(separator: " ")
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body

        if let logoURL = AgentRuntime.shared.notificationLogoURL,
           let attachment = try? UNNotificationAttachment(
               identifier: "agentcli-logo",
               url: logoURL
           ) {
            content.attachments = [attachment]
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }
}

struct CommandResult {
    let exitCode: Int32
    let output: String
}

struct FocusedTextTarget {
    let element: AXUIElement
    let pid: pid_t

    static func capture() -> FocusedTextTarget? {
        guard AXIsProcessTrusted() else {
            return nil
        }

        let systemWideElement = AXUIElementCreateSystemWide()
        var focusedValue: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            systemWideElement,
            kAXFocusedUIElementAttribute as CFString,
            &focusedValue
        ) == .success, let focusedValue else {
            return nil
        }

        let element = focusedValue as! AXUIElement
        var pid = pid_t(0)
        guard AXUIElementGetPid(element, &pid) == .success else {
            return nil
        }

        return FocusedTextTarget(element: element, pid: pid)
    }

    func insertText(_ text: String) -> Bool {
        AXUIElementSetAttributeValue(
            element,
            kAXSelectedTextAttribute as CFString,
            text as CFString
        ) == .success
    }
}

final class ConfigurableHotkeyController {
    static let shared = ConfigurableHotkeyController()

    private var registered = false

    private init() {}

    func registerDefaultHotkeys(runner: AgentCommandRunner) {
        guard !registered else { return }

        KeyboardShortcuts.onKeyUp(for: .toggleTranscription) {
            runner.run(.toggleTranscription)
        }
        KeyboardShortcuts.onKeyDown(for: .holdToTranscribe) {
            runner.beginHoldToTranscribe()
        }
        KeyboardShortcuts.onKeyUp(for: .holdToTranscribe) {
            runner.endHoldToTranscribe()
        }
        KeyboardShortcuts.onKeyUp(for: .autocorrect) {
            runner.run(.autocorrect)
        }
        KeyboardShortcuts.onKeyUp(for: .voiceEdit) {
            runner.run(.voiceEdit)
        }

        registered = true
    }
}
