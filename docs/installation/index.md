---
icon: lucide/download
---

# Installation Guide

Choose the best installation method for your platform and performance needs.

## Quick Platform Guide

| Platform         | Recommended Method             | GPU Support   | Performance |
| ---------------- | ------------------------------ | ------------- | ----------- |
| **macOS**        | [Native Setup](macos.md)       | ✅ Metal GPU  | Best        |
| **Linux**        | [Native Setup](linux.md)       | ✅ NVIDIA GPU | Best        |
| **NixOS**        | [System Integration](nixos.md) | ✅ NVIDIA GPU | Best        |
| **Any Platform** | [Docker Setup](docker.md)      | ⚠️ Limited\*  | Good        |

> [!WARNING]
> Docker on macOS does not support GPU acceleration. For best performance on Mac, use the [native setup](macos.md).

## Installation Methods

### 🍎 macOS Native (Recommended)

**Best performance with Metal GPU acceleration**

- Full GPU acceleration for Ollama
- Optimized for Apple Silicon
- Native macOS integrations

👉 [Follow macOS Setup Guide](macos.md)

### 🐧 Linux Native (Recommended)

**Best performance with NVIDIA GPU acceleration**

- NVIDIA GPU support
- Full system integration
- Optimal resource usage

👉 [Follow Linux Setup Guide](linux.md)

### ❄️ NixOS System Integration

**Declarative system configuration with GPU support**

- System-level service integration
- Declarative configuration
- Automatic service management

👉 [Follow NixOS Setup Guide](nixos.md)

### 🐳 Docker (Cross-platform)

**Universal solution, some limitations**

- Works on any platform
- Consistent environment
- ⚠️ No GPU acceleration on macOS
- ⚠️ Limited GPU support on other platforms

👉 [Follow Docker Setup Guide](docker.md)

## What Gets Installed

All installation methods set up these services:

- **🧠 Ollama** - LLM server (gemma3:4b model)
- **🎤 Wyoming Whisper** - Speech-to-text (faster-whisper on Linux/Intel, MLX Whisper on Apple Silicon)
- **🗣️ Wyoming Piper** - Text-to-speech
- **👂 Wyoming OpenWakeWord** - Wake word detection

## Service Ports

All methods use the same ports:

- Ollama (LLM): `11434`
- Whisper (ASR): `10300`
- Piper (TTS): `10200`
- OpenWakeWord: `10400`

## After Installation

Once services are running, install the agent-cli package:

```bash
# Using uv (recommended)
uv tool install agent-cli -p 3.13

# Using pip
pip install agent-cli
```

> [!NOTE]
> The `-p 3.13` flag is required because some dependencies don't support Python 3.14 yet.
> See [uv issue #8206](https://github.com/astral-sh/uv/issues/8206) for details.

Then test with:

```bash
agent-cli autocorrect --help
```

## Need Help?

- Check the troubleshooting section in your chosen installation guide
- Open an issue on [GitHub](https://github.com/basnijholt/agent-cli/issues)
