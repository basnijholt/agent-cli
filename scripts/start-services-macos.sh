#!/bin/bash

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Installing with Homebrew..."
    brew install tmux
fi

# Check if services are set up
if [ ! -f "run-whisper.sh" ] || [ ! -f "run-piper.sh" ] || [ ! -f "run-openwakeword.sh" ]; then
    echo "Services not set up. Please run setup-macos.sh first."
    exit 1
fi

# Start tmux session
SESSION_NAME="agent-cli-services"

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session
tmux new-session -d -s $SESSION_NAME -n services

# Split window into 4 panes
tmux split-window -h -t $SESSION_NAME:services
tmux split-window -v -t $SESSION_NAME:services.0
tmux split-window -v -t $SESSION_NAME:services.1

# Run services in each pane
tmux send-keys -t $SESSION_NAME:services.0 "ollama serve" C-m
tmux send-keys -t $SESSION_NAME:services.1 "./run-whisper.sh" C-m
tmux send-keys -t $SESSION_NAME:services.2 "./run-piper.sh" C-m
tmux send-keys -t $SESSION_NAME:services.3 "./run-openwakeword.sh" C-m

# Attach to session
echo "Starting all services in tmux session '$SESSION_NAME'..."
echo "Use 'Ctrl-B d' to detach from the session"
echo "Use 'tmux attach -t $SESSION_NAME' to reattach"
tmux attach -t $SESSION_NAME
