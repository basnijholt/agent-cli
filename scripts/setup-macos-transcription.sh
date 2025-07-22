#!/bin/bash

set -e

echo "🎙️ Setting up macOS transcription toggle system..."
echo "This will install and configure voice transcription toggling for agent-cli"
echo ""

# Function to check if we're running on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        echo "❌ ERROR: This script is designed for macOS only."
        echo "For Linux, use the Hyprland toggle script instead."
        exit 1
    fi
}

# Function to install Homebrew if not present
install_homebrew() {
    if ! command -v brew &> /dev/null; then
        echo "🍺 Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for current session
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            export PATH="/opt/homebrew/bin:$PATH"
        elif [[ -f "/usr/local/bin/brew" ]]; then
            export PATH="/usr/local/bin:$PATH"
        fi
    else
        echo "✅ Homebrew is already installed"
    fi
}

# Function to install terminal-notifier
install_terminal_notifier() {
    echo "📱 Checking terminal-notifier..."
    if ! command -v terminal-notifier &> /dev/null; then
        echo "Installing terminal-notifier..."
        brew install terminal-notifier
        echo "terminal-notifier installed successfully"
    else
        echo "✅ terminal-notifier is already installed"
    fi
}

# Function to install skhd.zig
install_skhd_zig() {
    echo "⌨️  Checking skhd.zig..."
    if ! command -v skhd &> /dev/null; then
        echo "Installing skhd.zig (modern skhd alternative)..."

        # Add jackielii's tap if not already added
        if ! brew tap | grep -q "jackielii/tap"; then
            echo "Adding jackielii/tap to Homebrew..."
            brew tap jackielii/tap
        fi

        brew install jackielii/tap/skhd-zig
        echo "skhd.zig installed successfully"
    else
        # Check if it's the original skhd or skhd.zig
        skhd_version=$(skhd --version 2>/dev/null || echo "unknown")
        if [[ "$skhd_version" == *"zig"* ]] || [[ "$skhd_version" == *"0.4"* ]] || [[ "$skhd_version" == *"0.5"* ]]; then
            echo "✅ skhd.zig is already installed"
        else
            echo "⚠️  Original skhd detected. Upgrading to skhd.zig..."
            # Stop the old service if running
            brew services stop skhd 2>/dev/null || true
            # Install skhd.zig
            if ! brew tap | grep -q "jackielii/tap"; then
                brew tap jackielii/tap
            fi
            brew install jackielii/tap/skhd-zig
        fi
    fi
}

# Function to verify agent-cli services
check_agent_cli_services() {
    echo "🤖 Checking agent-cli and services..."

    # Check if agent-cli is installed
    if ! command -v agent-cli &> /dev/null && ! command -v ~/.local/bin/agent-cli &> /dev/null; then
        echo "❌ agent-cli not found. Please run the main setup first:"
        echo "  ./setup-macos.sh"
        exit 1
    fi

    # Check if services are available
    echo "Checking required services..."

    # Check Ollama
    if ! command -v ollama &> /dev/null; then
        echo "⚠️  Ollama not found. Installing..."
        brew install ollama
    fi

    # Check if Wyoming services are set up (check for run scripts)
    if [[ ! -f "./run-whisper.sh" ]]; then
        echo "⚠️  Wyoming services not configured. Please run the main setup first:"
        echo "  ./setup-macos.sh"
        exit 1
    fi

    echo "✅ agent-cli and services are available"
}

# Function to create skhd configuration
setup_skhd_config() {
    echo "⚙️  Setting up skhd configuration..."

    # Create skhd config directory
    mkdir -p ~/.config/skhd

    # Get the current script directory to find the toggle script
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TOGGLE_SCRIPT="$SCRIPT_DIR/macos-toggle/toggle-transcription-best.sh"

    # Verify the toggle script exists
    if [[ ! -f "$TOGGLE_SCRIPT" ]]; then
        echo "❌ ERROR: Toggle script not found at $TOGGLE_SCRIPT"
        echo "Please ensure you're running this from the agent-cli scripts directory"
        exit 1
    fi

    # Create or update skhd config
    SKHD_CONFIG="$HOME/.config/skhd/skhdrc"

    # Check if config already has transcription toggle
    if [[ -f "$SKHD_CONFIG" ]] && grep -q "transcription" "$SKHD_CONFIG"; then
        echo "⚠️  Existing transcription toggle found in skhd config"
        echo "Backing up current config to ~/.config/skhd/skhdrc.backup"
        cp "$SKHD_CONFIG" "$SKHD_CONFIG.backup"

        # Remove existing transcription entries
        grep -v "transcription\|toggle-transcription" "$SKHD_CONFIG" > "$SKHD_CONFIG.tmp" || true
        mv "$SKHD_CONFIG.tmp" "$SKHD_CONFIG"
    fi

    # Add transcription toggle configuration
    cat >> "$SKHD_CONFIG" << EOF

# Agent-CLI Transcription Toggle
# Press Cmd+Shift+R to start/stop voice transcription
cmd + shift - r : "$TOGGLE_SCRIPT"

EOF

    echo "✅ skhd configuration updated"
    echo "   Config location: $SKHD_CONFIG"
    echo "   Hotkey: Cmd+Shift+R"
}

# Function to start and configure skhd service
setup_skhd_service() {
    echo "🚀 Setting up skhd service..."

    # Stop any existing skhd service
    pkill -f "skhd" 2>/dev/null || true
    sleep 1

    # Start skhd service
    echo "Starting skhd service..."
    skhd --start-service

    # Check if service started successfully
    sleep 2
    if pgrep -f "skhd" > /dev/null; then
        echo "✅ skhd service started successfully"
    else
        echo "⚠️  skhd service may need accessibility permissions"
        echo "Opening System Settings to grant permissions..."
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        echo ""
        echo "Please:"
        echo "1. Click the lock icon and enter your password"
        echo "2. Find 'skhd' in the list and enable it"
        echo "3. If skhd is not in the list:"
        echo "   - Click the '+' button"
        echo "   - Navigate to $(which skhd)"
        echo "   - Add and enable it"
        echo ""
        read -p "Press Enter after granting permissions..."

        # Try starting service again
        skhd --restart-service
        sleep 2

        if pgrep -f "skhd" > /dev/null; then
            echo "✅ skhd service started successfully"
        else
            echo "❌ skhd service failed to start. Please check accessibility permissions."
            exit 1
        fi
    fi
}

# Function to test the setup
test_transcription_system() {
    echo "🧪 Testing transcription system..."

    # Test terminal-notifier
    echo "Testing notifications..."
    terminal-notifier -title "🎙️ Test" -message "If you see this, notifications work!" -sound Glass
    sleep 2

    # Check if services are running
    echo "Checking services..."

    # Start Ollama if not running
    if ! pgrep -f "ollama serve" > /dev/null; then
        echo "Starting Ollama service..."
        ollama serve > /dev/null 2>&1 &
        sleep 3
    fi

    # Check Wyoming ASR
    if ! lsof -i :10300 > /dev/null 2>&1; then
        echo "⚠️  Wyoming ASR not running on port 10300"
        echo "Start it with: ./run-whisper.sh"
    else
        echo "✅ Wyoming ASR is running"
    fi

    # Check Ollama
    if ! lsof -i :11434 > /dev/null 2>&1; then
        echo "⚠️  Ollama not running on port 11434"
        echo "Start it with: ollama serve"
    else
        echo "✅ Ollama is running"
    fi

    echo ""
    echo "🎯 Test your setup:"
    echo "1. Press Cmd+Shift+R to start transcription"
    echo "2. Say something like 'This is a test'"
    echo "3. Press Cmd+Shift+R again to stop"
    echo "4. Check for the result notification and clipboard"
}

# Function to show final instructions
show_final_instructions() {
    echo ""
    echo "🎉 macOS Transcription Toggle Setup Complete!"
    echo "=============================================="
    echo ""
    echo "✅ Installed Components:"
    echo "   - terminal-notifier (notifications)"
    echo "   - skhd.zig (hotkey manager)"
    echo "   - Transcription toggle script"
    echo "   - skhd configuration"
    echo ""
    echo "🎯 Usage:"
    echo "   Press Cmd+Shift+R to toggle voice transcription"
    echo "   - First press: Start transcription (shows notification)"
    echo "   - Second press: Stop transcription and process result"
    echo "   - Result: Notification with transcribed text + clipboard copy"
    echo ""
    echo "🔧 Customization:"
    echo "   - Config file: ~/.config/skhd/skhdrc"
    echo "   - Change hotkey: Edit the 'cmd + shift - r' line"
    echo "   - Script location: $(dirname "${BASH_SOURCE[0]}")/macos-toggle/toggle-transcription-best.sh"
    echo ""
    echo "🚨 Required Services (start if not running):"
    echo "   - Ollama: ollama serve"
    echo "   - Wyoming ASR: ./run-whisper.sh"
    echo ""
    echo "📚 Documentation:"
    echo "   - Full guide: $(dirname "${BASH_SOURCE[0]}")/macos-toggle/README.md"
    echo "   - Install guide: $(dirname "${BASH_SOURCE[0]}")/macos-toggle/INSTALL-MACOS-TOGGLE.md"
    echo ""
    echo "🎙️ Ready to transcribe! Press Cmd+Shift+R to get started!"
}

# Main execution
main() {
    echo "Starting macOS transcription setup..."
    echo ""

    check_macos
    install_homebrew
    install_terminal_notifier
    install_skhd_zig
    check_agent_cli_services
    setup_skhd_config
    setup_skhd_service
    test_transcription_system
    show_final_instructions
}

# Run main function
main "$@"
