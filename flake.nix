{
  description = "agent-cli: Local-first AI-powered command-line tools";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true; # For potential NVIDIA drivers
        };

        pythonEnv = pkgs.python311.withPackages (ps: with ps; [
          # Core dependencies
          pip
          setuptools
          wheel
          versioningit

          # Project dependencies (from pyproject.toml)
          pyaudio
          rich
          pyperclip
          typer
          openai
          python-dotenv

          # Server dependencies
          fastapi
          uvicorn

          # Additional useful packages
          # audiostretchy  # Not available in nixpkgs, install via pip
        ]);

        # Build agent-cli package from source
        agent-cli = pkgs.python311Packages.buildPythonPackage rec {
          pname = "agent-cli";
          version = "0.1.0";
          src = ./.;

          format = "pyproject";

          nativeBuildInputs = with pkgs.python311Packages; [
            setuptools
            wheel
            versioningit
          ];

          propagatedBuildInputs = with pkgs.python311Packages; [
            # Core dependencies
            pyaudio
            rich
            pyperclip
            typer
            openai
            python-dotenv

            # Server dependencies
            fastapi
            uvicorn

            # Note: Some packages like wyoming, pydantic-ai-slim might need to be
            # installed via pip in the shell environment
          ];

          # Skip tests during build
          doCheck = false;

          pythonImportsCheck = [ "agent_cli" ];
        };

        # Script to start all services (uses Docker on macOS, native on Linux/NixOS)
        startServicesScript = pkgs.writeShellScriptBin "start-agent-services" ''
          set -e

          echo "🚀 Starting agent-cli services..."
          echo "Platform: ${pkgs.stdenv.system}"

          # Create necessary directories
          mkdir -p ~/.cache/agent-cli
          mkdir -p ~/.config/agent-cli

          # Function to check if a service is running
          check_service() {
            local name=$1
            local port=$2
            if nc -z localhost $port 2>/dev/null; then
              echo "✅ $name is already running on port $port"
              return 0
            else
              return 1
            fi
          }

          # Check if Docker is available (for macOS)
          if [[ "${pkgs.stdenv.isDarwin}" == "true" ]] || [[ "${pkgs.stdenv.system}" == *"darwin"* ]]; then
            if ! command -v docker &> /dev/null; then
              echo "❌ Docker is required on macOS to run the AI services."
              echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
              exit 1
            fi

            echo "Using Docker to run services on macOS..."

            # Start Ollama via Docker
            if ! check_service "Ollama" 11434; then
              echo "Starting Ollama in Docker..."
              docker run -d --name ollama \
                -p 11434:11434 \
                -v ollama:/root/.ollama \
                --restart unless-stopped \
                ollama/ollama:latest || true
              sleep 5

              # Pull default model
              docker exec ollama ollama pull qwen3:4b || true
            fi

            # Start Wyoming Faster Whisper via Docker
            if ! check_service "Wyoming Faster Whisper" 10300; then
              echo "Starting Wyoming Faster Whisper in Docker..."
              docker run -d --name wyoming-whisper \
                -p 10300:10300 \
                -v ~/.cache/agent-cli/whisper:/data \
                --restart unless-stopped \
                rhasspy/wyoming-whisper:latest \
                --model tiny-int8 \
                --language en || true
            fi

            # Start Wyoming Piper via Docker
            if ! check_service "Wyoming Piper" 10200; then
              echo "Starting Wyoming Piper in Docker..."
              docker run -d --name wyoming-piper \
                -p 10200:10200 \
                -v ~/.cache/agent-cli/piper:/data \
                --restart unless-stopped \
                rhasspy/wyoming-piper:latest \
                --voice en_US-ryan-high || true
            fi

            # Start Wyoming OpenWakeWord via Docker
            if ! check_service "Wyoming OpenWakeWord" 10400; then
              echo "Starting Wyoming OpenWakeWord in Docker..."
              docker run -d --name wyoming-openwakeword \
                -p 10400:10400 \
                -v ~/.cache/agent-cli/openwakeword:/data \
                --restart unless-stopped \
                rhasspy/wyoming-openwakeword:latest \
                --preload-model alexa \
                --preload-model hey_jarvis || true
            fi

            echo ""
            echo "✅ Docker services started!"
            echo ""
            echo "To stop services, run:"
            echo "  docker stop ollama wyoming-whisper wyoming-piper wyoming-openwakeword"
            echo ""

          else
            # Linux/NixOS - services should be managed by systemd
            echo "On NixOS, services should be configured in your system configuration."
            echo "Add the NixOS module from this flake to your configuration.nix"
            echo ""
            echo "For non-NixOS Linux, you can run services manually or use the setup scripts."
          fi

          # Start agent-cli server (works on all platforms)
          if ! check_service "Agent-CLI Server" 61337; then
            echo "Starting Agent-CLI Server..."
            cd ${./.}
            ${pythonEnv}/bin/python -m uvicorn agent_cli.api:app \
              --host 0.0.0.0 \
              --port 61337 \
              --log-level info &
            SERVER_PID=$!
          fi

          echo ""
          echo "Services available at:"
          echo "  • Ollama: http://localhost:11434"
          echo "  • Wyoming Faster Whisper: tcp://localhost:10300"
          echo "  • Wyoming Piper: tcp://localhost:10200"
          echo "  • Wyoming OpenWakeWord: tcp://localhost:10400"
          echo "  • Agent-CLI Server: http://localhost:61337"
          echo ""

          if [[ -n "$SERVER_PID" ]]; then
            echo "Press Ctrl+C to stop the agent-cli server..."
            trap 'echo "Stopping server..."; kill $SERVER_PID 2>/dev/null; exit' INT TERM
            wait $SERVER_PID
          fi
        '';

        # Development shell script
        devShellScript = pkgs.writeShellScriptBin "agent-cli-dev" ''
          echo "🛠️  Agent-CLI Development Environment"
          echo ""
          echo "Available commands:"
          echo "  start-agent-services  - Start all background services"
          echo "  agent-cli            - Run agent-cli commands"
          echo ""
          echo "Installing remaining Python dependencies via pip..."
          pip install -q wyoming pydantic-ai-slim[openai,duckduckgo,vertexai] google-genai
          echo "✅ Environment ready!"
        '';

      in
      {
        # Packages
        packages = {
          default = agent-cli;
          inherit agent-cli;
          start-services = startServicesScript;
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Python environment
            pythonEnv

            # System dependencies
            portaudio
            pkg-config
            gcc
            git

            # Audio tools
            sox
            ffmpeg

            # Note: Wyoming and Ollama services on macOS need to be run via Docker or manually
            # since NixOS service modules aren't available on Darwin.
            # The start-services script handles this.

            # Utilities
            netcat-gnu
            curl
            jq
            zellij

            # Custom scripts
            startServicesScript
            devShellScript
          ] ++ pkgs.lib.optionals pkgs.stdenv.isDarwin [
            # macOS specific
            pkgs.darwin.apple_sdk.frameworks.AudioToolbox
            pkgs.darwin.apple_sdk.frameworks.CoreAudio
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux && pkgs.config.cudaSupport or false) [
            # CUDA support for Linux
            pkgs.cudatoolkit
          ];

          shellHook = ''
            echo "🚀 Agent-CLI Nix Development Environment"
            echo ""
            echo "Setting up environment variables..."
            export AGENT_CLI_ROOT="${./.}"
            export PYTHONPATH="$AGENT_CLI_ROOT:$PYTHONPATH"

            # Create config directories
            mkdir -p ~/.config/agent-cli
            mkdir -p ~/.cache/agent-cli

            # Set default config if not exists
            if [ ! -f ~/.config/agent-cli/config.toml ]; then
              echo "Creating default config..."
              cat > ~/.config/agent-cli/config.toml << 'EOF'
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
            EOF
            fi

            echo "✅ Environment ready!"
            echo ""
            echo "Quick start:"
            echo "  1. Run 'start-agent-services' to start all services"
            echo "  2. In another terminal, use 'agent-cli <command>'"
            echo ""
            echo "Available agent-cli commands:"
            echo "  • autocorrect - Correct grammar and spelling"
            echo "  • transcribe  - Voice-to-text transcription"
            echo "  • speak       - Text-to-speech"
            echo "  • voice-edit  - Voice-powered clipboard editing"
            echo "  • assistant   - Voice assistant with wake word"
            echo "  • chat        - Conversational AI agent"
            echo "  • server      - Run API server (port 61337)"
            echo ""
            echo "Run 'agent-cli --help' for more information"

            # Install missing Python packages via pip
            echo ""
            echo "Installing Python packages not in nixpkgs..."
            pip install -q wyoming pydantic-ai-slim[openai,duckduckgo,vertexai] google-genai 2>/dev/null || true
          '';

          # Environment variables
          AGENT_CLI_DEV = "1";
          PYTHONDONTWRITEBYTECODE = "1";
        };

        # NixOS module for system-wide installation
        nixosModules.default = { config, lib, pkgs, ... }:
          with lib;
          let
            cfg = config.services.agent-cli;
          in
          {
            options.services.agent-cli = {
              enable = mkEnableOption "agent-cli services";

              package = mkOption {
                type = types.package;
                default = self.packages.${pkgs.system}.agent-cli;
                description = "The agent-cli package to use";
              };

              enableOllama = mkOption {
                type = types.bool;
                default = true;
                description = "Enable Ollama LLM service";
              };

              enableWhisper = mkOption {
                type = types.bool;
                default = true;
                description = "Enable Wyoming Faster Whisper ASR service";
              };

              enablePiper = mkOption {
                type = types.bool;
                default = true;
                description = "Enable Wyoming Piper TTS service";
              };

              enableOpenWakeWord = mkOption {
                type = types.bool;
                default = true;
                description = "Enable Wyoming OpenWakeWord service";
              };

              enableServer = mkOption {
                type = types.bool;
                default = false;
                description = "Enable agent-cli API server";
              };

              serverPort = mkOption {
                type = types.int;
                default = 61337;
                description = "Port for agent-cli API server";
              };
            };

            config = mkIf cfg.enable {
              # Install agent-cli package
              environment.systemPackages = [ cfg.package ];

              # Configure Ollama
              services.ollama = mkIf cfg.enableOllama {
                enable = true;
                acceleration = "cuda"; # or "rocm" or "cpu"
                host = "0.0.0.0";
                openFirewall = true;
                environmentVariables = {
                  OLLAMA_KEEP_ALIVE = "1h";
                };
              };

              # Configure Wyoming services
              services.wyoming.faster-whisper = mkIf cfg.enableWhisper {
                servers.default = {
                  enable = true;
                  model = "tiny-int8";
                  language = "en";
                  device = "cuda"; # or "cpu"
                  uri = "tcp://0.0.0.0:10300";
                };
              };

              services.wyoming.piper.servers.default = mkIf cfg.enablePiper {
                enable = true;
                voice = "en_US-ryan-high";
                uri = "tcp://0.0.0.0:10200";
              };

              services.wyoming.openwakeword = mkIf cfg.enableOpenWakeWord {
                enable = true;
                preloadModels = [ "alexa" "hey_jarvis" ];
                uri = "tcp://0.0.0.0:10400";
              };

              # Agent-CLI server as systemd service
              systemd.services.agent-cli-server = mkIf cfg.enableServer {
                description = "Agent-CLI API Server";
                after = [ "network.target" ];
                wantedBy = [ "multi-user.target" ];

                serviceConfig = {
                  Type = "simple";
                  ExecStart = "${cfg.package}/bin/agent-cli server --port ${toString cfg.serverPort}";
                  Restart = "on-failure";
                  RestartSec = "5s";
                };
              };

              # Open firewall ports
              networking.firewall = {
                allowedTCPPorts = lib.optional cfg.enableOllama 11434
                  ++ lib.optional cfg.enableWhisper 10300
                  ++ lib.optional cfg.enablePiper 10200
                  ++ lib.optional cfg.enableOpenWakeWord 10400
                  ++ lib.optional cfg.enableServer cfg.serverPort;
              };
            };
          };
      }
    );
}
