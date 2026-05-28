#if canImport(XCTest)
import Carbon.HIToolbox
import KeyboardShortcuts
import XCTest
@testable import AgentCLI

final class ShortcutDefaultsTests: XCTestCase {
    override func setUp() {
        super.setUp()
        clearShortcutDefaults()
    }

    override func tearDown() {
        clearShortcutDefaults()
        super.tearDown()
    }

    func testMigratesPlainSpaceToggleShortcutToFunctionSpace() {
        KeyboardShortcuts.setShortcut(
            KeyboardShortcuts.Shortcut(.space),
            for: .toggleTranscription
        )

        ShortcutDefaultsMigrator.migrate()

        let shortcut = KeyboardShortcuts.getShortcut(for: .toggleTranscription)
        XCTAssertEqual(shortcut?.carbonKeyCode, kVK_Space)
        XCTAssertEqual((shortcut?.carbonModifiers ?? 0) & kEventKeyModifierFnMask, kEventKeyModifierFnMask)
    }

    func testResetDefaultsRestoresFunctionSpaceToggleShortcut() {
        KeyboardShortcuts.setShortcut(
            KeyboardShortcuts.Shortcut(.space),
            for: .toggleTranscription
        )

        ShortcutSummaryState.shared.resetDefaults()

        let shortcut = KeyboardShortcuts.getShortcut(for: .toggleTranscription)
        XCTAssertEqual(shortcut?.carbonKeyCode, kVK_Space)
        XCTAssertEqual((shortcut?.carbonModifiers ?? 0) & kEventKeyModifierFnMask, kEventKeyModifierFnMask)
    }

    private func clearShortcutDefaults() {
        for name in [
            "toggleTranscription",
            "holdToTranscribe",
            "autocorrect",
            "voiceEdit",
        ] {
            UserDefaults.standard.removeObject(forKey: "KeyboardShortcuts_\(name)")
        }
    }
}
#endif
