---
icon: lucide/snowflake
---

# NixOS Installation

Native NixOS setup using system configuration with full GPU acceleration support.

> [!TIP]
> **❄️ For NixOS Users** — Integrates agent-cli services directly into your NixOS system configuration.

## Prerequisites

- NixOS system
- Root access for system configuration
- 8GB+ RAM (16GB+ recommended for GPU acceleration)
- 10GB free disk space

### For GPU Acceleration (Optional)

- NVIDIA GPU with proprietary drivers enabled in configuration
- Or AMD GPU with ROCm support

## Configuration

Add this to your NixOS configuration (`/etc/nixos/configuration.nix`):

```nix
{
  # AI & Machine Learning services
  services.ollama = {
    enable = true;
    acceleration = "cuda";  # or "rocm" for AMD, "cpu" for no GPU
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
      device = "cuda";  # or "cpu" if no GPU
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
}
```

## NVIDIA GPU Configuration

If you have an NVIDIA GPU, also add:

```nix
{
  # NVIDIA drivers
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.opengl = {
    enable = true;
    driSupport = true;
    driSupport32Bit = true;
  };

  # CUDA support
  hardware.nvidia = {
    modesetting.enable = true;
    powerManagement.enable = false;
    powerManagement.finegrained = false;
    open = false; # Use proprietary driver
    nvidiaSettings = true;
    package = config.boot.kernelPackages.nvidiaPackages.stable;
  };
}
```

## Apply Configuration

1. **Rebuild your system:**

   ```bash
   sudo nixos-rebuild switch
   ```

2. **Check service status:**

   ```bash
   sudo systemctl status ollama
   sudo systemctl status wyoming-faster-whisper
   sudo systemctl status wyoming-piper
   sudo systemctl status wyoming-openwakeword
   ```

3. **Install agent-cli:**

   ```bash
   nix-shell -p portaudio pkg-config gcc python3 --run "uv tool install --upgrade agent-cli -p 3.13"
   # or add to your configuration:
   # environment.systemPackages = with pkgs; [ agent-cli ];
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## Services Overview

| Service          | Port  | GPU Support  | Systemd Service                  |
| ---------------- | ----- | ------------ | -------------------------------- |
| **Ollama**       | 11434 | ✅ CUDA/ROCm | `ollama.service`                 |
| **Whisper**      | 10300 | ✅ CUDA      | `wyoming-faster-whisper.service` |
| **Piper**        | 10200 | N/A          | `wyoming-piper.service`          |
| **OpenWakeWord** | 10400 | N/A          | `wyoming-openwakeword.service`   |

## Service Management

```bash
# Check all services
sudo systemctl status wyoming-*
sudo systemctl status ollama

# Restart a service
sudo systemctl restart ollama

# View logs
journalctl -u ollama -f
journalctl -u wyoming-faster-whisper -f
```

## Troubleshooting

### GPU Not Working

```bash
# Check NVIDIA setup
nvidia-smi
lspci | grep -i nvidia

# Check Ollama GPU usage
sudo -u ollama ollama info
```

### Service Issues

```bash
# Check service status
sudo systemctl --failed
journalctl -u ollama --since "1 hour ago"
```

### Firewall Issues

Make sure `openFirewall = true` is set for each service, or manually add:

```nix
{
  networking.firewall = {
    allowedTCPPorts = [ 11434 10200 10300 10400 ];
  };
}
```

## Configuration Example

Complete example from [basnijholt/dotfiles](https://github.com/basnijholt/dotfiles/blob/main/configs/nixos/configuration.nix):

```nix
{
  # Complete AI services configuration
  services.ollama = {
    enable = true;
    acceleration = "cuda";
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
      device = "cuda";
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
    preloadModels = [ "alexa" "hey_jarvis" "ok_nabu" ];
    uri = "tcp://0.0.0.0:10400";
  };
}
```

## Alternative: Script-Based Setup

If you prefer not to use system services, you can also use the [regular Linux scripts](linux.md) on NixOS.
