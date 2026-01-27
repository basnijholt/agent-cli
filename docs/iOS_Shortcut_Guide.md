# iOS Shortcut Setup for Agent CLI Transcription

This guide shows how to create an iOS Shortcut that records audio, sends it to your Agent CLI web service, and puts the cleaned transcription in your clipboard.

## Prerequisites

1. **Agent CLI Server Running**: Your Agent CLI server must be running and accessible
2. **FFmpeg Installed**: For local ASR with audio conversion (iOS uses m4a format)
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg` (Ubuntu/Debian)
   - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)
3. **OpenAI API Key**: Configure your OpenAI API key in Agent CLI (if using OpenAI)
4. **Network Access**: Your iPhone needs network access to reach the server

## Setup Agent CLI Server

1. Install dependencies:
   ```bash
   pip install "agent-cli[server]"
   ```

2. Start the server:
   ```bash
   agent-cli server transcribe-proxy --host 0.0.0.0 --port 61337
   ```

3. Test the server is working:
   ```bash
   curl http://your-server-ip:61337/health
   ```

## Create iOS Shortcut

### Step 1: Open Shortcuts App
- Open the **Shortcuts** app on your iPhone
- Tap the **+** button to create a new shortcut

### Step 2: Add Actions

**Action 1: Record Audio**
1. Search for and add **"Record Audio"** action
2. Configure:
   - **Start Recording**: Immediately
   - **Stop Recording**: When shortcut is run again (or set a time limit)
   - **Audio Quality**: Choose based on your preference (Higher = Better quality, Larger files)

**Action 2: Get Contents of URL**
1. Search for and add **"Get Contents of URL"** action
2. Configure:
   - **URL**: `http://YOUR_SERVER_IP:61337/transcribe`
   - **Method**: POST
   - **Headers**: Leave empty
   - **Request Body**: Form

**Action 3: Get Dictionary Value**
1. Search for and add **"Get Dictionary Value"** action
2. Configure:
   - **Dictionary**: Output from Get Contents of URL
   - **Get Value for**: `cleaned_transcript` (or `raw_transcript` if you prefer unprocessed)

**Action 4: Copy to Clipboard**
1. Search for and add **"Copy to Clipboard"** action
2. Input: Use the text from the previous step

**Action 5 (Optional): Show Notification**
1. Search for and add **"Show Notification"** action
2. Configure:
   - **Title**: "Transcription Complete"
   - **Body**: Use the transcribed text

### Step 3: Configure Request Details

In the **Get Contents of URL** action, tap **"Show More"** and configure:

**Critical: Configure Form Data**
1. In the **Get Contents of URL** action, tap **"Show More"**
2. Set **Request Body** to **"Form"**
3. Tap **"Add new field"** to add the audio file:
   - **Key**: `audio` (exactly, lowercase)
   - **Value**: Select the "Audio" output from your Record Audio action
   - **Type**: Make sure it's set to "File" (not "Text")

**Optional Form Fields:**
Add these fields if needed by tapping "Add new field":
- **Key**: `cleanup`, **Value**: `true` (enables AI text cleanup)
- **Key**: `extra_instructions`, **Value**: Custom instructions for processing

**⚠️ CRITICAL SETUP REQUIREMENTS:**

- The audio field name must be exactly `audio` (lowercase, case-sensitive)
- Audio field type must be set to "File" (not "Text")
- Form fields must be configured manually - iOS doesn't add them automatically

**Common Issues:**

- ❌ Field named "Audio" (uppercase) - won't work
- ❌ Field type set to "Text" - won't work
- ❌ No form fields configured - will give 422 error
- ✅ Field named "audio" with type "File" - works correctly

### Step 4: Test the Shortcut

1. Name your shortcut (e.g., "Voice to Text")
2. Tap **"Done"** to save
3. Run the shortcut to test it
4. Grant microphone permissions when prompted

### Step 5: Add to Home Screen or Control Center

**Add to Home Screen:**

1. Go to Settings > Shortcuts
2. Find your shortcut and tap the settings icon
3. Tap **"Add to Home Screen"**

**Add to Control Center:**

1. Go to Settings > Control Center
2. Add **"Shortcuts"** if not already added
3. Your shortcut will be available in Control Center

## Troubleshooting

### Common Issues

**"Could not connect to server"**
- Verify server is running: `curl http://your-server-ip:61337/health`
- Check firewall settings on server
- Ensure iPhone and server are on same network (or server is publicly accessible)

**"No audio recorded"**
- Grant microphone permissions to Shortcuts app
- Check audio recording settings in the Record Audio action

**"Get Contents of File not available"**
- This action was removed in newer iOS versions
- The recorded audio is automatically passed between actions as a variable
- Simply use the output from "Record Audio" directly in "Get Contents of URL"

**"Transcription failed"**
- Verify OpenAI API key is configured in Agent CLI
- Check server logs for error messages
- Ensure audio file format is supported (wav, mp3, m4a, etc.)

**"Empty response"**
- Check if the audio was too short or silent
- Verify the Get Value from Dictionary action is looking for the right key

**"422 Unprocessable Content" Error**
- This means the form fields are not configured correctly
- Make sure you've added the `audio` field in the Request Body Form section
- The audio field must be type "File" not "Text"
- Field name must be exactly `audio` (lowercase)
- Check server logs for specific error details

**"FFmpeg not found" Error**
- Install FFmpeg on your system for local ASR with audio conversion
- macOS: `brew install ffmpeg`
- Linux: `sudo apt-get install ffmpeg`
- Alternative: Use OpenAI ASR instead (set `asr-provider = "openai"` in config)

### Server Configuration

**Config File Example (`~/.config/agent-cli/config.toml`):**
```toml
[defaults]
# For transcription with Wyoming/FasterWhisper (local)
asr-provider = "wyoming"
asr-wyoming-ip = "localhost"
asr-wyoming-port = 10300

# For LLM cleanup (can use Ollama, OpenAI, or Gemini)
llm-provider = "ollama"
llm-ollama-model = "llama3"
llm-ollama-host = "http://localhost:11434"

# If using OpenAI for transcription or LLM:
# openai-api-key = "your-api-key-here"

[transcribe]
llm = true
clipboard = false  # Disabled for web service
extra-instructions = "Your custom cleanup instructions here"
```

### Advanced Shortcuts Features

**Voice Activation:**

- Add shortcut to Siri by saying "Hey Siri, add to Siri" while viewing the shortcut
- Record a custom phrase like "Transcribe this"

**Conditional Processing:**

- Add **"If"** actions to handle different response cases
- Show different notifications based on success/failure

**Text Processing:**

- Add text manipulation actions after transcription
- Format text, convert case, etc.

**Alternative: Save Recording First**
If you want to save the audio file:
1. After "Record Audio", add **"Save to Files"** action
   - Choose location (e.g., iCloud Drive/Recordings/)
   - Name: `Recording-{Current Date}`
2. Add **"Get File"** action to retrieve the saved file
3. Use this file in "Get Contents of URL"

## API Reference

### Endpoint: POST /transcribe

**Request:**
```
Content-Type: multipart/form-data

audio: <audio file>
cleanup: true/false (optional, default: true)
extra_instructions: <string> (optional)
```

**Response:**
```json
{
  "raw_transcript": "original transcription",
  "cleaned_transcript": "cleaned and formatted text",
  "success": true,
  "error": null
}
```

### Health Check: GET /health

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## Security Considerations

- **Network Security**: Use HTTPS in production
- **API Key Protection**: Keep OpenAI API key secure
- **Access Control**: Consider adding authentication to your API
- **Firewall**: Only expose necessary ports

## Next Steps

- Set up HTTPS with SSL certificates for production use
- Add authentication to the API endpoint
- Configure automatic server startup
- Create multiple shortcuts for different transcription scenarios
