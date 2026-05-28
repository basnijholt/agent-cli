import Foundation
import SwiftUI

struct VoiceStatusMenuItem: View {
    let runner: AgentCommandRunner

    @State private var statusMessage: String
    private let statusRefreshTimer = Timer.publish(every: 0.8, on: .main, in: .common).autoconnect()

    init(runner: AgentCommandRunner) {
        self.runner = runner
        _statusMessage = State(initialValue: runner.menuStatusMessage)
    }

    var body: some View {
        Text("Voice: \(statusMessage)")
            .lineLimit(1)
            .onAppear(perform: refreshStatusMessage)
            .onReceive(statusRefreshTimer) { _ in
                refreshStatusMessage()
            }
    }

    private func refreshStatusMessage() {
        statusMessage = runner.menuStatusMessage
    }
}
