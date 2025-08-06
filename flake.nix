{
  description = "agent-cli: Local-first AI-powered command-line tools for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachSystem [ "x86_64-linux" "aarch64-linux" ] (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true; # For NVIDIA drivers
        };

        pythonEnv = pkgs.python311.withPackages (
          ps: with ps; [
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
          ]
        );

        # Build agent-cli package from source
        agent-cli = pkgs.python311Packages.buildPythonPackage rec {
          pname = "agent-cli";
          version = "0.1.0";
          src = ./.;

          format = "pyproject";

          nativeBuildInputs =
            with pkgs.python311Packages;
            [
              setuptools
              wheel
              versioningit
            ]
            ++ [ pkgs.git ];

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
          ];

          # Skip tests during build
          doCheck = false;

          # Skip runtime dependencies check since some packages are not in nixpkgs
          dontCheckRuntimeDeps = true;

          # Set version explicitly since we don't have git metadata in Nix build
          preBuild = ''
            # Create a fake git repository to satisfy versioningit
            git init -q
            git config user.email "nixbuild@example.com"
            git config user.name "Nix Build"
            git add -A
            git commit -q -m "Nix build commit"
            git tag -a "v${version}" -m "Version ${version}"
          '';

          pythonImportsCheck = [ "agent_cli" ];
        };

        # Simple script to check service status
        checkServicesScript = pkgs.writeShellScriptBin "check-agent-services" ''
          echo "🔍 Checking agent-cli services status..."
          echo ""

          # Check systemd services on NixOS
          for service in ollama wyoming-faster-whisper wyoming-piper wyoming-openwakeword agent-cli-server; do
            if systemctl is-active --quiet $service; then
              echo "✅ $service is running"
            else
              echo "❌ $service is not running"
            fi
          done

          echo ""
          echo "Service endpoints:"
          echo "  • Ollama: http://localhost:11434"
          echo "  • Wyoming Faster Whisper: tcp://localhost:10300"
          echo "  • Wyoming Piper: tcp://localhost:10200"
          echo "  • Wyoming OpenWakeWord: tcp://localhost:10400"
          echo "  • Agent-CLI Server: http://localhost:61337"
        '';

      in
      {
        # Packages
        packages = {
          default = agent-cli;
          inherit agent-cli;
          check-services = checkServicesScript;
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs =
            with pkgs;
            [
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

              # Utilities
              netcat-gnu
              curl
              jq

              # Custom scripts
              checkServicesScript
            ]
            ++ pkgs.lib.optionals (pkgs.config.cudaSupport or false) [
              # CUDA support
              pkgs.cudatoolkit
            ];

          shellHook = ''
            echo "🚀 Agent-CLI NixOS Development Environment"
            echo ""
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
            echo "To use agent-cli on NixOS:"
            echo "  1. Add the NixOS module to your configuration.nix"
            echo "  2. Enable the services you need"
            echo "  3. Run 'check-agent-services' to verify status"
            echo ""
            echo "Available commands:"
            echo "  • agent-cli --help    - Show all commands"
            echo "  • check-agent-services - Check service status"
            echo ""

            # Install missing Python packages via pip
            echo "Installing Python packages not in nixpkgs..."
            pip install -q wyoming pydantic-ai-slim[openai,duckduckgo,vertexai] google-genai audiostretchy 2>/dev/null || true
          '';

          # Environment variables
          AGENT_CLI_DEV = "1";
          PYTHONDONTWRITEBYTECODE = "1";
        };

        # NixOS module for system-wide installation
        nixosModules.default =
          {
            config,
            lib,
            pkgs,
            ...
          }:
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

              ollamaAcceleration = mkOption {
                type = types.enum [
                  "cuda"
                  "rocm"
                  "cpu"
                ];
                default = "cpu";
                description = "Acceleration method for Ollama";
              };

              whisperDevice = mkOption {
                type = types.enum [
                  "cuda"
                  "cpu"
                ];
                default = "cpu";
                description = "Device for Whisper ASR";
              };
            };

            config = mkIf cfg.enable {
              # Install agent-cli package
              environment.systemPackages = [ cfg.package ];

              # Configure Ollama
              services.ollama = mkIf cfg.enableOllama {
                enable = true;
                acceleration = cfg.ollamaAcceleration;
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
                  device = cfg.whisperDevice;
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
                preloadModels = [
                  "alexa"
                  "hey_jarvis"
                ];
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
                  User = "nobody";
                  Group = "nogroup";
                };
              };

              # Open firewall ports
              networking.firewall = {
                allowedTCPPorts =
                  lib.optional cfg.enableOllama 11434
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
