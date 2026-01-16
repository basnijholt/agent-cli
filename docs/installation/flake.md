# Nix Flake for NixOS

Nix flake providing a development shell and NixOS module for AI service configuration.

## Prerequisites

- NixOS with flakes enabled
- 8GB+ RAM (16GB+ recommended for GPU)

### Enable Flakes

Add to `/etc/nix/nix.conf`:
```
experimental-features = nix-command flakes
```

## Quick Start

### Development Shell

```bash
git clone https://github.com/basnijholt/agent-cli.git
cd agent-cli
nix develop

# Inside the shell:
uv sync --all-extras
uv run agent-cli --help
```

The dev shell provides:
- Python 3.12 with uv for package management
- System dependencies (portaudio, ffmpeg, sox)
- Build tools (gcc, pkg-config)

### Install agent-cli

```bash
# Using uv (recommended)
uv tool install agent-cli

# Or with pip
pip install agent-cli
```

## NixOS Module

The flake includes a NixOS module that configures AI backend services (Ollama, Wyoming Whisper/Piper/OpenWakeWord).

### Basic Usage

Add to your NixOS flake:

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
            # All services enabled by default
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

### Module Options

```nix
services.agent-cli = {
  enable = true;  # Enable AI backend services

  # Ollama LLM
  ollama = {
    enable = true;                    # Default: true
    acceleration = "cuda";            # "cuda", "rocm", or "cpu"
    host = "127.0.0.1";               # Host address
    environmentVariables = {
      OLLAMA_KEEP_ALIVE = "1h";
    };
  };

  # Wyoming Faster Whisper (ASR)
  whisper = {
    enable = true;                    # Default: true
    model = "tiny-int8";              # tiny-int8, small, medium, large-v3
    language = "en";                  # Language code
    device = "cuda";                  # "cuda" or "cpu"
    uri = "tcp://127.0.0.1:10300";
  };

  # Wyoming Piper (TTS)
  piper = {
    enable = true;                    # Default: true
    voice = "en_US-ryan-high";        # Voice model
    uri = "tcp://127.0.0.1:10200";
  };

  # Wyoming OpenWakeWord
  openwakeword = {
    enable = false;                   # Default: false
    preloadModels = [ "ok_nabu" ];    # Wake word models
    uri = "tcp://127.0.0.1:10400";
  };
};
```

### GPU Configuration

#### NVIDIA GPU

```nix
{
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.graphics.enable = true;
  hardware.nvidia.modesetting.enable = true;

  services.agent-cli = {
    enable = true;
    ollama.acceleration = "cuda";
    whisper.device = "cuda";
  };
}
```

#### AMD GPU (ROCm)

```nix
{
  hardware.graphics.extraPackages = with pkgs; [
    rocmPackages.clr.icd
  ];

  services.agent-cli = {
    enable = true;
    ollama.acceleration = "rocm";
    whisper.device = "cpu";  # Whisper doesn't support ROCm
  };
}
```

## Services Overview

| Service | Port | Purpose | Systemd Service |
|---------|------|---------|-----------------|
| Ollama | 11434 | Local LLM | `ollama.service` |
| Whisper | 10300 | Speech-to-text | `wyoming-faster-whisper-agent-cli.service` |
| Piper | 10200 | Text-to-speech | `wyoming-piper-agent-cli.service` |
| OpenWakeWord | 10400 | Wake word | `wyoming-openwakeword.service` |

## Configuration

Create `~/.config/agent-cli/config.toml`:

```toml
[llm]
provider = "ollama"
model = "qwen3:4b"

[asr]
provider = "wyoming"

[tts]
provider = "wyoming"

[services]
ollama_url = "http://localhost:11434"
wyoming_asr_uri = "tcp://localhost:10300"
wyoming_tts_uri = "tcp://localhost:10200"
```

## Troubleshooting

### Check Services

```bash
systemctl status ollama
systemctl status wyoming-faster-whisper-agent-cli
systemctl status wyoming-piper-agent-cli
journalctl -u ollama -f
```

### GPU Issues

```bash
nvidia-smi                    # Check NVIDIA
rocminfo                      # Check AMD ROCm
```

## Using with Direnv

Create `.envrc`:
```bash
use flake
```

Then:
```bash
direnv allow
```

## Updating

```bash
nix flake update
sudo nixos-rebuild switch --flake .#yourhostname
```
