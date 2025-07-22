-- Hammerspoon script for agent-cli transcription toggle
-- Save this to ~/.hammerspoon/init.lua (or add to existing config)
--
-- Installation:
-- 1. brew install --cask hammerspoon
-- 2. Launch Hammerspoon and enable accessibility permissions
-- 3. Add this script to ~/.hammerspoon/init.lua

local function isTranscriptionRunning()
    local output = hs.execute("pgrep -f 'agent-cli transcribe'")
    return output and output:len() > 0
end

local function toggleTranscription()
    if isTranscriptionRunning() then
        -- Stop transcription
        hs.execute("pkill -INT -f 'agent-cli transcribe'")
        hs.notify.new({
            title = "🛑 Transcription Stopped",
            informativeText = "Processing results...",
            withdrawAfter = 3
        }):send()
    else
        -- Start transcription
        hs.notify.new({
            title = "🎙️ Transcription Started",
            informativeText = "Listening in background...",
            withdrawAfter = 3
        }):send()

        -- Run in background with callback for results
        local task = hs.task.new("/usr/bin/env", function(exitCode, stdOut, stdErr)
            if exitCode == 0 and stdOut and stdOut:len() > 0 then
                -- Copy to clipboard and show result
                hs.pasteboard.setContents(stdOut)
                hs.notify.new({
                    title = "📄 Transcription Result",
                    informativeText = stdOut,
                    withdrawAfter = 5
                }):send()
            end
        end, {
            "bash", "-c",
            "export PATH=\"$PATH:$HOME/.local/bin:/opt/homebrew/bin\"; agent-cli transcribe --llm --quiet 2>/dev/null"
        })
        task:start()
    end
end

-- Bind to Cmd+Shift+R
hs.hotkey.bind({"cmd", "shift"}, "r", toggleTranscription)

-- Alternative key bindings (uncomment one you prefer):
-- hs.hotkey.bind({"cmd", "shift"}, "t", toggleTranscription)
-- hs.hotkey.bind({"alt", "shift"}, "r", toggleTranscription)
-- hs.hotkey.bind({"ctrl", "alt"}, "r", toggleTranscription)
