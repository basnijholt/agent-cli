import Foundation
import UserNotifications

struct AgentNotificationPresenter {
    func notify(title: String, body: String) {
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

    func notifyStart(for command: AgentCommand) {
        guard let title = command.startNotificationTitle else { return }
        notify(title: title, body: command.startNotificationBody ?? "")
    }
}
