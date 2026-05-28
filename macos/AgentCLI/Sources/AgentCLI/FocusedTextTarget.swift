import AppKit
import ApplicationServices
import Foundation

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

        guard CFGetTypeID(focusedValue) == AXUIElementGetTypeID() else {
            return nil
        }
        let element = focusedValue as! AXUIElement
        var pid = pid_t(0)
        guard AXUIElementGetPid(element, &pid) == .success else {
            return nil
        }

        return FocusedTextTarget(element: element, pid: pid)
    }

    func refocus() {
        NSRunningApplication(processIdentifier: pid)?.activate(options: [.activateIgnoringOtherApps])
        _ = AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
    }
}
