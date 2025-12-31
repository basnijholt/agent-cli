# Nix Flake Installation for NixOS

Modern Nix setup using flakes for reproducible and declarative agent-cli installation on NixOS.

## Prerequisites

- NixOS with flakes enabled
- 8GB+ RAM (16GB+ recommended for GPU)
- 10GB free disk space

### Enable Flakes (if not already enabled)

Add to `/etc/nix/nix.conf`:
```
experimental-features = nix-command flakes
```

## Quick Start

### Development Shell

1. **Clone and enter the development environment:**
   ```bash
   git clone https://github.com/basnijholt/agent-cli.git
   cd agent-cli
   nix develop
   ```

2. **Check service status:**
   ```bash
   check-agent-services
   ```

3. **Use agent-cli:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

### Direct Usage (without cloning)

```bash
# Add to your system
nix profile install github:basnijholt/agent-cli
```

## Installation Methods

### Method 1: Development Shell (Recommended for Testing)

The development shell provides a complete environment with all dependencies:

```bash
cd agent-cli
nix develop

# Inside the shell:
check-agent-services  # Check status of NixOS services
agent-cli --help      # Use agent-cli
```

Features:
- Automatic Python environment setup
- All Wyoming services configured via NixOS
- Ollama LLM server via NixOS
- Development tools and utilities

### Method 2: System-Wide Installation (NixOS)

Add to your NixOS `configuration.nix` or flake:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    agent-cli.url = "github:basnijholt/agent-cli";
  };

  outputs = { self, nixpkgs, agent-cli, ... }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        agent-cli.nixosModules.default
        {
          services.agent-cli = {
            enable = true;
            enableOllama = true;
            enableWhisper = true;
            enablePiper = true;
            enableOpenWakeWord = true;
            enableServer = true;  # Optional API server
            serverPort = 61337;   # API server port

            # GPU acceleration options
            ollamaAcceleration = "cuda"; # or "rocm" or "cpu"
            whisperDevice = "cuda";       # or "cpu"
          };
        }
      ];
    };
  };
}
```

Then rebuild:
```bash
sudo nixos-rebuild switch --flake .#yourhostname
```

### Method 3: Home Manager Integration

```nix
{
  programs.agent-cli = {
    enable = true;
    package = agent-cli.packages.${pkgs.system}.default;
  };
}
```

### Method 4: Direct Package Installation

```bash
# Install to user profile
nix profile install github:basnijholt/agent-cli#agent-cli

# Or use in another flake
{
  environment.systemPackages = [
    agent-cli.packages.${pkgs.system}.agent-cli
  ];
}
```

## GPU Acceleration

### NVIDIA GPU

The flake automatically detects and enables CUDA support when available:

```nix
{
  # Enable NVIDIA drivers
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.opengl.enable = true;
  hardware.nvidia.modesetting.enable = true;

  # Configure agent-cli to use CUDA
  services.agent-cli = {
    enable = true;
    ollamaAcceleration = "cuda";
    whisperDevice = "cuda";
  };
}
```

### AMD GPU

For AMD GPUs with ROCm:

```nix
{
  # Enable AMD GPU support
  hardware.opengl.extraPackages = with pkgs; [
    rocm-opencl-icd
    rocm-opencl-runtime
  ];

  # Configure agent-cli to use ROCm
  services.agent-cli = {
    enable = true;
    ollamaAcceleration = "rocm";
    whisperDevice = "cpu"; # Whisper doesn't support ROCm yet
  };
}
```

## Services Overview

All services are managed by NixOS systemd:

| Service | Port | Purpose | Systemd Service |
|---------|------|---------|-----------------|
| Ollama | 11434 | Local LLM | `ollama.service` |
| Whisper | 10300 | Speech-to-text | `wyoming-faster-whisper.service` |
| Piper | 10200 | Text-to-speech | `wyoming-piper.service` |
| OpenWakeWord | 10400 | Wake word detection | `wyoming-openwakeword.service` |
| Agent-CLI Server | 61337 | API server (optional) | `agent-cli-server.service` |

## Configuration

The flake automatically creates a default configuration at `~/.config/agent-cli/config.toml`:

```toml
[llm]
provider = "ollama"
model = "qwen3:4b"

[asr]
provider = "wyoming-faster-whisper"

[tts]
provider = "wyoming-piper"

[wake_word]
provider = "wyoming-openwakeword"

[services]
ollama_url = "http://localhost:11434"
wyoming_faster_whisper_url = "tcp://localhost:10300"
wyoming_piper_url = "tcp://localhost:10200"
wyoming_openwakeword_url = "tcp://localhost:10400"
```

## NixOS Module Options

The NixOS module provides comprehensive configuration options:

### Basic Options

```nix
services.agent-cli = {
  enable = true;                    # Enable agent-cli services
  enableOllama = true;              # Enable Ollama LLM service
  enableWhisper = true;             # Enable Wyoming Faster Whisper ASR
  enablePiper = true;               # Enable Wyoming Piper TTS
  enableOpenWakeWord = true;        # Enable Wyoming OpenWakeWord
  enableServer = false;             # Enable agent-cli API server
  serverPort = 61337;               # API server port
};
```

### Ollama Configuration

```nix
services.agent-cli = {
  ollamaAcceleration = "cuda";     # "cuda", "rocm", or "cpu"
  ollamaHost = "0.0.0.0";          # Host address for Ollama
  ollamaEnvironmentVariables = {   # Environment variables for Ollama
    OLLAMA_KEEP_ALIVE = "1h";
    # Add any other Ollama env vars here
  };
};
```

### Whisper ASR Configuration

```nix
services.agent-cli = {
  whisperModel = "large-v3";       # Model size: tiny-int8, small, medium, large-v3
  whisperLanguage = "en";          # Language code: en, nl, fr, de, es, etc.
  whisperDevice = "cuda";          # "cuda" or "cpu"
  whisperUri = "tcp://0.0.0.0:10300"; # Server URI
};
```

### Piper TTS Configuration

```nix
services.agent-cli = {
  piperVoice = "en_US-ryan-high";  # Voice model
  piperUri = "tcp://0.0.0.0:10200"; # Server URI
};
```

### OpenWakeWord Configuration

```nix
services.agent-cli = {
  openWakeWordModels = [            # Wake word models to preload
    "alexa"
    "hey_jarvis"
    "ok_nabu"
  ];
  openWakeWordUri = "tcp://0.0.0.0:10400"; # Server URI
};
```

### Complete Example

```nix
services.agent-cli = {
  enable = true;

  # Enable all services
  enableOllama = true;
  enableWhisper = true;
  enablePiper = true;
  enableOpenWakeWord = true;
  enableServer = true;

  # GPU acceleration
  ollamaAcceleration = "cuda";
  whisperDevice = "cuda";

  # Advanced Whisper configuration
  whisperModel = "large-v3";
  whisperLanguage = "en";

  # Custom URIs (if using non-standard ports)
  whisperUri = "tcp://0.0.0.0:10300";
  piperUri = "tcp://0.0.0.0:10200";
  openWakeWordUri = "tcp://0.0.0.0:10400";

  # Wake words
  openWakeWordModels = [ "alexa" "hey_jarvis" "ok_nabu" ];
};
```

## Flake Outputs

The flake provides:

- `packages.default` - The agent-cli package
- `packages.agent-cli` - The agent-cli package (explicit)
- `packages.check-services` - Service status checking script
- `devShells.default` - Development environment
- `nixosModules.default` - NixOS module for system integration

## Troubleshooting

### Check Service Status

```bash
# In development shell
check-agent-services

# On NixOS system
systemctl status ollama
systemctl status wyoming-faster-whisper
systemctl status wyoming-piper
systemctl status wyoming-openwakeword
systemctl status agent-cli-server  # If enabled
```

### Port Conflicts

If ports are already in use:

1. Check what's using them:
   ```bash
   lsof -i :11434  # Ollama
   lsof -i :10300  # Whisper
   lsof -i :10200  # Piper
   lsof -i :10400  # OpenWakeWord
   lsof -i :61337  # Agent-CLI server
   ```

2. Stop conflicting services or modify the port configuration in your NixOS configuration

### GPU Not Detected

```bash
# Check NVIDIA
nvidia-smi

# Check CUDA availability in development shell
nix develop --command python -c "import torch; print(torch.cuda.is_available())"
```

### Missing Python Dependencies

Some packages are installed via pip in the development shell:
```bash
nix develop
# The shell automatically installs:
# - wyoming
# - pydantic-ai-slim[openai,duckduckgo,vertexai]
# - google-genai
# - audiostretchy
```

## Advanced Usage

### Custom Models

```bash
# Pull different Ollama models
ollama pull llama3:8b
ollama pull mistral:7b

# Update config.toml to use them
```

### Manual Service Management

```bash
# Start/stop services via systemd
sudo systemctl start ollama
sudo systemctl stop wyoming-faster-whisper
sudo systemctl restart wyoming-piper
sudo systemctl status wyoming-openwakeword
```

### Using with Direnv

Create `.envrc`:
```bash
use flake
```

Then:
```bash
direnv allow
# Environment loads automatically when entering directory
```

## Updating

```bash
# Update flake inputs
nix flake update

# Rebuild with latest versions
nix develop --recreate

# For NixOS system
sudo nixos-rebuild switch --flake .#yourhostname
```

## Notes

This flake is designed specifically for NixOS and uses native systemd services for all components. It does not support macOS or non-NixOS Linux distributions. For those platforms, please use the traditional installation methods described in other documentation.
