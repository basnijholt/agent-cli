#!/bin/bash

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Installing tmux..."
    brew install tmux
fi

# Start tmux session
SESSION_NAME="agent-cli-services"

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session
tmux new-session -d -s $SESSION_NAME -n services

# Split window into 4 panes
tmux split-window -h -t $SESSION_NAME:services
tmux split-window -v -t $SESSION_NAME:services
tmux split-window -v -t $SESSION_NAME:services.2

# Run services in each pane (tmux numbers panes from 1)
tmux send-keys -t $SESSION_NAME:services.1 "ollama serve" C-m
tmux send-keys -t $SESSION_NAME:services.2 "./run-whisper-uvx.sh" C-m
tmux send-keys -t $SESSION_NAME:services.3 "./run-piper-uvx.sh" C-m
tmux send-keys -t $SESSION_NAME:services.4 "./run-openwakeword-uvx.sh" C-m

# Attach to session
echo "Starting all services in tmux session '$SESSION_NAME'..."
echo "Use 'Ctrl-B d' to detach from the session"
echo "Use 'tmux attach -t $SESSION_NAME' to reattach"
tmux attach -t $SESSION_NAME
