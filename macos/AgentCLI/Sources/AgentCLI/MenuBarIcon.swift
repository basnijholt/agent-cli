import AppKit
import Foundation
import SwiftUI

enum MenuBarIconState: Equatable {
    case idle
    case preparing
    case recording

    static func current(isPreparing: Bool, isRecording: Bool) -> Self {
        if isPreparing {
            return .preparing
        }
        if isRecording {
            return .recording
        }
        return .idle
    }
}

struct AgentCLIMenuBarIcon: View {
    let state: MenuBarIconState

    var body: some View {
        if let image = MenuBarIconImage.logoImage(state: state) {
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 22, height: 18)
                .id(state)
                .accessibilityLabel(accessibilityLabel)
        } else {
            Image(systemName: fallbackSystemImage)
                .id(state)
                .accessibilityLabel(accessibilityLabel)
        }
    }

    private var accessibilityLabel: Text {
        switch state {
        case .idle:
            return Text("Agent CLI")
        case .preparing:
            return Text("Agent CLI preparing")
        case .recording:
            return Text("Agent CLI recording")
        }
    }

    private var fallbackSystemImage: String {
        switch state {
        case .idle:
            return "person.crop.circle"
        case .preparing:
            return "arrow.triangle.2.circlepath.circle.fill"
        case .recording:
            return "record.circle.fill"
        }
    }
}

enum MenuBarIconImage {
    static func logoImage(state: MenuBarIconState) -> NSImage? {
        switch state {
        case .idle:
            return idleLogoImage
        case .preparing:
            return preparingLogoImage
        case .recording:
            return recordingLogoImage
        }
    }

    static func badgeColor(for state: MenuBarIconState) -> NSColor? {
        switch state {
        case .idle:
            return nil
        case .preparing:
            return .systemBlue
        case .recording:
            return .systemRed
        }
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
    private static let preparingLogoImage: NSImage? = makePreparingLogoImage()

    private static func makeRecordingLogoImage() -> NSImage? {
        makeBadgedLogoImage(badgeColor: badgeColor(for: .recording) ?? .systemRed, badgeDiameter: 7)
    }

    private static func makePreparingLogoImage() -> NSImage? {
        makeBadgedLogoImage(badgeColor: badgeColor(for: .preparing) ?? .systemBlue, badgeDiameter: 7)
    }

    private static func makeBadgedLogoImage(badgeColor: NSColor, badgeDiameter: CGFloat) -> NSImage? {
        guard let url = Bundle.main.url(forResource: "logo-avatar", withExtension: "svg"),
              let avatar = NSImage(contentsOf: url)
        else {
            return nil
        }

        avatar.size = NSSize(width: 18, height: 18)

        let image = NSImage(size: NSSize(width: 22, height: 18))
        image.lockFocus()
        let logoRect = NSRect(x: 0, y: 0, width: 18, height: 18)
        avatar.draw(
            in: logoRect,
            from: .zero,
            operation: .sourceOver,
            fraction: 1
        )
        NSColor.white.setFill()
        logoRect.fill(using: .sourceIn)

        NSColor.white.setFill()
        NSBezierPath(ovalIn: NSRect(x: 12.5, y: 0.5, width: 10, height: 10)).fill()
        badgeColor.setFill()
        NSBezierPath(ovalIn: NSRect(x: 14, y: 2, width: badgeDiameter, height: badgeDiameter)).fill()
        image.unlockFocus()

        image.isTemplate = false
        return image
    }
}
