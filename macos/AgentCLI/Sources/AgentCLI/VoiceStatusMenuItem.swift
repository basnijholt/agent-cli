import SwiftUI

struct VoiceStatusMenuItem: View {
    let runner: AgentCommandRunner

    var body: some View {
        Text("Voice: \(runner.menuStatusMessage)")
            .lineLimit(1)
    }
}
