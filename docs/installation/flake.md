# Nix Flake Installation

Modern Nix setup using flakes for reproducible and declarative agent-cli installation.

## Prerequisites

- Nix with flakes enabled
- 8GB+ RAM (16GB+ recommended for GPU)
- 10GB free disk space

### Enable Flakes (if not already enabled)

Add to `~/.config/nix/nix.conf` or `/etc/nix/nix.conf`:
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

2. **Start all services:**
   ```bash
   start-agent-services
   ```

3. **Use agent-cli (in another terminal):**
   ```bash
   nix develop
   agent-cli autocorrect "this has an eror"
   ```

### Direct Usage (without cloning)

```bash
# Run directly from GitHub
nix run github:basnijholt/agent-cli#start-services

# Or add to your system
nix profile install github:basnijholt/agent-cli
```

## Installation Methods

### Method 1: Development Shell (Recommended for Testing)

The development shell provides a complete environment with all dependencies:

```bash
cd agent-cli
nix develop

# Inside the shell:
start-agent-services  # Start all background services
agent-cli --help      # Use agent-cli
```

Features:
- Automatic Python environment setup
- All Wyoming services included
- Ollama LLM server
- Development tools and utilities

### Method 2: System-Wide Installation (NixOS)

Add to your `flake.nix`:

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
nix profile install .#agent-cli

# Or use in another flake
{
  environment.systemPackages = [
    agent-cli.packages.${pkgs.system}.agent-cli
  ];
}
```

## GPU Acceleration

### NVIDIA GPU

The flake automatically detects and enables CUDA support when available. For NixOS:

```nix
{
  # Enable NVIDIA drivers
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.opengl.enable = true;
  hardware.nvidia.modesetting.enable = true;

  # Agent-CLI will use CUDA automatically
  services.agent-cli.enable = true;
}
```

### AMD GPU

For AMD GPUs with ROCm:

```nix
{
  # In your system configuration
  hardware.opengl.extraPackages = with pkgs; [
    rocm-opencl-icd
    rocm-opencl-runtime
  ];
}
```

## Services Overview

The flake manages these services:

| Service | Port | Purpose | Systemd Service (NixOS) |
|---------|------|---------|-------------------------|
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

## Flake Outputs

The flake provides:

- `packages.default` - The agent-cli package
- `packages.start-services` - Service startup script
- `devShells.default` - Development environment
- `nixosModules.default` - NixOS module for system integration

## Troubleshooting

### Check Service Status

```bash
# In development shell
start-agent-services  # Shows status of each service

# On NixOS
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

2. Stop conflicting services or modify the configuration

### GPU Not Detected

```bash
# Check NVIDIA
nvidia-smi

# Check CUDA availability
nix develop --command python -c "import torch; print(torch.cuda.is_available())"
```

### Missing Python Dependencies

Some packages are installed via pip in the shell:
```bash
nix develop
pip install wyoming pydantic-ai-slim[openai,duckduckgo,vertexai] google-genai
```

## Advanced Usage

### Custom Models

```bash
# Pull different Ollama models
ollama pull llama3:8b
ollama pull mistral:7b

# Update config to use them
```

### Running Services Separately

```bash
# Start individual services
ollama serve &
wyoming-faster-whisper --model tiny-int8 --uri tcp://0.0.0.0:10300 &
wyoming-piper --voice en_US-ryan-high --uri tcp://0.0.0.0:10200 &
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
```
