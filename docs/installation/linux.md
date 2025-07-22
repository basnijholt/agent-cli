# Linux Native Installation

Native Linux setup with full NVIDIA GPU acceleration for optimal performance.

> **🐧 Recommended for Linux**
> This setup provides optimal performance with full NVIDIA GPU acceleration support.

## Prerequisites

- Linux distribution with systemd (Ubuntu 20.04+, Fedora 35+, etc.)
- 8GB+ RAM (16GB+ recommended for GPU acceleration)
- 10GB free disk space
- Python 3.11 or higher

### For GPU Acceleration (Optional)
- NVIDIA GPU (GTX 1060+ or RTX series recommended)
- NVIDIA drivers 470+ installed
- CUDA 11.7+ installed

## Quick Start

### Option 1: NixOS (Recommended)

If you're using NixOS, add this to your configuration:

```nix
# AI & Machine Learning services
services.ollama = {
  enable = true;
  acceleration = "cuda";  # or "rocm" for AMD
  host = "0.0.0.0";
  openFirewall = true;
  environmentVariables = {
    OLLAMA_KEEP_ALIVE = "1h";
  };
};

services.wyoming.faster-whisper = {
  servers.english = {
    enable = true;
    model = "large-v3";
    language = "en";
    device = "cuda";  # or "cpu"
    uri = "tcp://0.0.0.0:10300";
  };
};

services.wyoming.piper.servers.default = {
  enable = true;
  voice = "en-us-ryan-high";
  uri = "tcp://0.0.0.0:10200";
};

services.wyoming.openwakeword = {
  enable = true;
  preloadModels = [
    "alexa"
    "hey_jarvis"
    "ok_nabu"
  ];
  uri = "tcp://0.0.0.0:10400";
};
```

Then rebuild your system:
```bash
sudo nixos-rebuild switch
```

### Option 2: Script-Based Installation (Recommended)

1. **Run the setup script:**
   ```bash
   chmod +x scripts/setup-linux.sh
   scripts/setup-linux.sh
   ```

2. **Start all services:**
   ```bash
   scripts/start-all-services.sh
   ```

3. **Install agent-cli:**
   ```bash
   uv tools install agent-cli
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

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
scripts/run-whisper-uvx.sh

# Terminal 3: Piper
scripts/run-piper-uvx.sh

# Terminal 4: OpenWakeWord
scripts/run-openwakeword-uvx.sh
```

## Services Overview

| Service | Port | GPU Support | Auto-Detection |
|---------|------|-------------|----------------|
| **Ollama** | 11434 | ✅ CUDA/ROCm | Automatic |
| **Whisper** | 10300 | ✅ CUDA | Automatic (falls back to CPU) |
| **Piper** | 10200 | N/A | N/A |
| **OpenWakeWord** | 10400 | N/A | N/A |

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
- **Whisper**: Detects NVIDIA GPU and uses `large-v3` model with CUDA, falls back to `tiny-int8` with CPU
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

## Systemd Services (Optional)

Create systemd services for auto-startup:

### Ollama Service
```bash
sudo tee /etc/systemd/system/ollama.service > /dev/null <<EOF
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="OLLAMA_HOST=0.0.0.0:11434"

[Install]
WantedBy=default.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Whisper Service
```bash
sudo tee /etc/systemd/system/wyoming-whisper.service > /dev/null <<EOF
[Unit]
Description=Wyoming Faster Whisper
After=network-online.target

[Service]
ExecStart=/home/$(whoami)/.local/bin/wyoming-faster-whisper --model large-v3 --language en --device cuda --uri tcp://0.0.0.0:10300
User=$(whoami)
Group=$(whoami)
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wyoming-whisper
sudo systemctl start wyoming-whisper
```

## Performance Optimization

### Ollama GPU Settings
```bash
# Check GPU utilization
watch -n 1 nvidia-smi

# Set GPU memory fraction (if needed)
export OLLAMA_GPU_MEM_FRAC=0.8
```

### Whisper GPU Settings
```bash
# For high VRAM GPUs
wyoming-faster-whisper --model large-v3 --device cuda --compute-type float16

# For lower VRAM GPUs
wyoming-faster-whisper --model medium --device cuda --compute-type int8
```

## Troubleshooting

### GPU Not Detected
```bash
# Check NVIDIA setup
nvidia-smi
lspci | grep -i nvidia

# Check CUDA
nvcc --version
nvidia-smi

# Check Ollama GPU usage
ollama info
```

### Memory Issues
```bash
# Check memory usage
free -h
nvidia-smi

# Reduce model sizes
ollama pull qwen3:1.5b  # Instead of qwen3:4b
```

### Service Connection Issues
```bash
# Check if services are running
sudo systemctl status ollama
sudo systemctl status wyoming-whisper

# Check ports
ss -tlnp | grep -E ':(11434|10300|10200|10400)'

# Test connections
curl http://localhost:11434/api/version
```

### Performance Issues
```bash
# Monitor GPU usage
nvidia-smi -l 1

# Check CPU usage
htop

# Optimize for your hardware
# - Use appropriate model sizes
# - Adjust batch sizes
# - Enable GPU acceleration where possible
```

## Alternative: Docker

If you prefer Docker (with some performance limitations):
- [Docker Setup Guide](docker.md)
- Note: May have reduced GPU acceleration support
