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

### Option 2: Manual Installation

1. **Install Ollama:**
   ```bash
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

2. **Install Python dependencies:**
   ```bash
   # Install uv
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Install Wyoming services
   uv tool install wyoming-faster-whisper
   uv tool install wyoming-piper
   uv tool install wyoming-openwakeword
   ```

3. **Start services:**
   ```bash
   # Terminal 1: Ollama
   ollama serve

   # Terminal 2: Whisper (with GPU)
   wyoming-faster-whisper --model large-v3 --language en --device cuda --uri tcp://0.0.0.0:10300

   # Terminal 3: Piper
   wyoming-piper --voice en-us-ryan-high --uri tcp://0.0.0.0:10200

   # Terminal 4: OpenWakeWord
   wyoming-openwakeword --preload-model ok_nabu --uri tcp://0.0.0.0:10400
   ```

4. **Install agent-cli:**
   ```bash
   uv tools install agent-cli
   ```

5. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## Services Overview

| Service | Port | GPU Support | Memory Usage |
|---------|------|-------------|--------------|
| **Ollama** | 11434 | ✅ CUDA/ROCm | 2-8GB VRAM |
| **Whisper** | 10300 | ✅ CUDA | 1-4GB VRAM |
| **Piper** | 10200 | N/A | ~500MB RAM |
| **OpenWakeWord** | 10400 | N/A | ~200MB RAM |

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
