import AppKit

@MainActor
final class MenuActivityStatusRow {
    private let prefix: String
    private let item: NSMenuItem
    private let separator: NSMenuItem

    init(prefix: String) {
        self.prefix = prefix
        item = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        item.isEnabled = false
        separator = .separator()
    }

    func add(to menu: NSMenu) {
        menu.addItem(item)
        menu.addItem(separator)
    }

    func update(_ activityStatus: MenuActivityStatus) {
        item.title = "\(prefix)\(activityStatus.message)"
        item.isHidden = !activityStatus.isActive
        separator.isHidden = !activityStatus.isActive
    }
}
