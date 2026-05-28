import AppKit
import Foundation
import SwiftUI

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
