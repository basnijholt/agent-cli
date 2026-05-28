cask "agent-cli" do
  version "0.95.7"
  sha256 "9db4a8d9f44765e1197d687a46e4cde041ada2d5284e6a22324c706d2a40848e"

  url "https://github.com/basnijholt/agent-cli/releases/download/v#{version}/AgentCLI.dmg"
  name "Agent CLI"
  desc "Local-first AI voice and text tools with menu bar integration"
  homepage "https://github.com/basnijholt/agent-cli"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on arch: :arm64
  depends_on macos: :ventura

  app "AgentCLI.app"

  uninstall launchctl: "com.agent_cli.whisper",
            quit:      "lt.nijho.agent-cli.menubar"

  zap trash: [
    "~/Library/Application Support/AgentCLI",
    "~/Library/LaunchAgents/com.agent_cli.whisper.plist",
    "~/Library/Logs/agent-cli-whisper",
    "~/Library/Preferences/lt.nijho.agent-cli.menubar.plist",
  ]
end
