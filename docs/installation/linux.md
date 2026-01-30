---
icon: fontawesome/brands/linux
---

# Linux Native Installation

Native Linux setup with full NVIDIA GPU acceleration for optimal performance.

> [!TIP]
> **🐧 Recommended for Linux** — Optimal performance with full NVIDIA GPU acceleration.

## Prerequisites

- Linux distribution (Ubuntu 20.04+, Fedora 35+, Arch, Debian, etc.)
- 8GB+ RAM (16GB+ recommended for GPU acceleration)
- 10GB free disk space
- Python 3.11 or higher

### For GPU Acceleration (Optional)

- NVIDIA GPU (GTX 1060+ or RTX series recommended)
- NVIDIA drivers 470+ installed
- CUDA 11.7+ installed

## Installation Methods

### Script-Based Installation (Recommended)

1. **Run the setup script:**

   ```bash
   scripts/setup-linux.sh
   ```

2. **Start all services:**

   ```bash
   scripts/start-all-services.sh
   ```

3. **Install agent-cli:**

   ```bash
   uv tool install agent-cli -p 3.13
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

### NixOS Users

If you're using NixOS, see the dedicated [NixOS Installation Guide](nixos.md) for system-level service integration.

### Option 3: Manual Installation

If you prefer manual setup:

```bash
# 1. Install dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Start services individually
# Terminal 1: Ollama
ollama serve

# Terminal 2: Whisper (with GPU)
scripts/run-whisper.sh

# Terminal 3: Piper
scripts/run-piper.sh

# Terminal 4: OpenWakeWord
scripts/run-openwakeword.sh
```

## Services Overview

| Service          | Port  | GPU Support  | Auto-Detection                |
| ---------------- | ----- | ------------ | ----------------------------- |
| **Ollama**       | 11434 | ✅ CUDA/ROCm | Automatic                     |
| **Whisper**      | 10300 | ✅ CUDA      | Automatic (falls back to CPU) |
| **Piper**        | 10200 | N/A          | N/A                           |
| **OpenWakeWord** | 10400 | N/A          | N/A                           |

## Session Management with Zellij

The scripts use Zellij for managing all services in one session (works on both Linux and macOS):

### Starting Services

```bash
scripts/start-all-services.sh
```

### Zellij Commands

- `Ctrl-O d` - Detach (services keep running)
- `zellij attach agent-cli` - Reattach to session
- `zellij list-sessions` - List all sessions
- `zellij kill-session agent-cli` - Stop all services
- `Alt + arrow keys` - Navigate between panes
- `Ctrl-Q` - Quit (stops all services)

## Automatic GPU Detection

The scripts automatically detect and use GPU acceleration:

- **Whisper**: Detects NVIDIA GPU and uses `large-v3` model with CUDA, falls back to `tiny` on CPU
- **Ollama**: Automatically uses available GPU (CUDA/ROCm)

## GPU Acceleration Setup

### NVIDIA GPU (CUDA)

1. **Install NVIDIA drivers:**

   ```bash
   # Ubuntu/Debian
   sudo apt install nvidia-driver-535

   # Fedora
   sudo dnf install akmod-nvidia
   ```

2. **Install CUDA toolkit:**

   ```bash
   # Ubuntu/Debian
   sudo apt install nvidia-cuda-toolkit

   # Fedora
   sudo dnf install cuda
   ```

3. **Verify GPU setup:**
   ```bash
   nvidia-smi
   nvcc --version
   ```

### AMD GPU (ROCm)

1. **Install ROCm:**

   ```bash
   # Ubuntu/Debian
   sudo apt install rocm-dev

   # Configure for Ollama
   export HSA_OVERRIDE_GFX_VERSION=10.3.0  # Adjust for your GPU
   ```

2. **Start Ollama with ROCm:**
   ```bash
   ollama serve
   ```

## Why Native Setup?

- **Full GPU acceleration** - NVIDIA CUDA support
- **Automatic configuration** - Scripts detect and configure GPU
- **Better performance** - Direct system integration

## Troubleshooting

### GPU Not Working

```bash
# Check if NVIDIA GPU is detected
nvidia-smi
```

### Services Not Starting

```bash
# Check what's running on the ports
ss -tlnp | grep -E ':(11434|10300|10200|10400)'
```

### General Issues

- Make sure you have enough RAM (8GB minimum)
- Services automatically download required models

## Alternative: Docker

If you prefer Docker (with some performance limitations):

- [Docker Setup Guide](docker.md)
- Note: May have reduced GPU acceleration support
