-- AppleScript for agent-cli transcription toggle
-- Save as Application in Script Editor, then bind with Karabiner-Elements
--
-- Installation:
-- 1. brew install --cask karabiner-elements
-- 2. Open Script Editor, paste this script, save as Application
-- 3. Use Karabiner-Elements to bind key to open this app

on run
    set isRunning to false

    -- Check if transcription is running
    try
        do shell script "pgrep -f 'agent-cli transcribe'"
        set isRunning to true
    on error
        set isRunning to false
    end try

    if isRunning then
        -- Stop transcription
        do shell script "pkill -INT -f 'agent-cli transcribe'"
        display notification "Processing results..." with title "🛑 Transcription Stopped"
    else
        -- Start transcription
        display notification "Listening in background..." with title "🎙️ Transcription Started"

        -- Start transcription in background
        set transcriptCommand to "export PATH=\"$PATH:$HOME/.local/bin:/opt/homebrew/bin\"; agent-cli transcribe --llm --quiet 2>/dev/null"

        -- Run in background and wait for result
        try
            set transcriptResult to do shell script transcriptCommand
            -- Copy to clipboard
            set the clipboard to transcriptResult
            display notification transcriptResult with title "📄 Transcription Result"
        on error errorMessage
            display notification errorMessage with title "❌ Transcription Error"
        end try
    end if
end run
