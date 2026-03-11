#!/usr/bin/env swift
// Minimal menu bar icon that shows while recording.
// Usage: menubar-icon [icon] [tooltip]
// Exits on SIGTERM or SIGINT. Kill the process to remove the icon.

import AppKit

let icon = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "🎙️"
let tooltip = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "agent-cli: recording"

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
statusItem.button?.title = icon
statusItem.button?.toolTip = tooltip

// Use DispatchSource for safe signal handling on the main queue
signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)

let sigterm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
sigterm.setEventHandler { NSApp.terminate(nil) }
sigterm.resume()

let sigint = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sigint.setEventHandler { NSApp.terminate(nil) }
sigint.resume()

app.run()
