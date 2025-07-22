# Using Built-in macOS Shortcuts App

This method uses only built-in macOS tools (Shortcuts.app is included in macOS Monterey+).

## Setup Instructions:

1. **Open Shortcuts App** (built into macOS Monterey and later)

2. **Create New Shortcut**:
   - Click the "+" to create a new shortcut
   - Name it "Toggle Transcription"

3. **Add Actions**:

   **Action 1: Run Shell Script**
   ```bash
   # Check if transcription is running
   if pgrep -f "agent-cli transcribe" > /dev/null; then
       echo "running"
   else
       echo "stopped"
   fi
   ```

   **Action 2: If Statement**
   - Condition: "If Text contains 'running'"

   **Inside If (transcription is running):**
   - **Run Shell Script**: `pkill -INT -f "agent-cli transcribe"`
   - **Show Notification**: Title "🛑 Transcription Stopped", Body "Processing results..."

   **Inside Otherwise (transcription is stopped):**
   - **Show Notification**: Title "🎙️ Transcription Started", Body "Listening in background..."
   - **Run Shell Script**:
     ```bash
     export PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin"
     OUTPUT=$(agent-cli transcribe --llm --quiet 2>/dev/null) && {
         echo "$OUTPUT" | pbcopy
         osascript -e "display notification \"$OUTPUT\" with title \"📄 Transcription Result\""
     }
     ```

4. **Set Keyboard Shortcut**:
   - In Shortcuts app, click the settings icon on your shortcut
   - Choose "Add Keyboard Shortcut"
   - Set your preferred key combination (e.g., ⌘⇧R)

5. **Enable in System Preferences**:
   - Go to System Preferences → Privacy & Security → Accessibility
   - Add and enable "Shortcuts" if not already enabled

## Alternative: Automator Quick Action

If you prefer Automator:

1. Open **Automator**
2. Create new **Quick Action**
3. Add **Run Shell Script** action
4. Paste the contents of `toggle-transcription-macos.sh`
5. Save as "Toggle Transcription"
6. Go to **System Preferences → Keyboard → Shortcuts → Services**
7. Find your Quick Action and assign a keyboard shortcut
