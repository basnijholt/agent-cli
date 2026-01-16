{
  description = "agent-cli: Local-first AI-powered command-line tools";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      # Development shell with system dependencies
      # Python packages are managed by uv (much simpler than fighting nixpkgs)
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              # Python via uv (handles all Python deps)
              uv
              python312

              # System dependencies for PyAudio/sounddevice
              portaudio
              pkg-config

              # Audio tools
              ffmpeg
              sox

              # Build tools
              gcc
              git
            ];

            shellHook = ''
              export LD_LIBRARY_PATH="${
                pkgs.lib.makeLibraryPath [ pkgs.portaudio ]
              }''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

              # Auto-sync Python dependencies
              if [ -f pyproject.toml ]; then
                echo "Syncing Python dependencies..."
                uv sync --all-extras --quiet
                echo "Ready! Run: agent-cli --help"
              fi
            '';
          };
        }
      );

      # NixOS module for configuring AI services (ollama, wyoming-*)
      # Install agent-cli itself via: uv tool install agent-cli
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.agent-cli;
        in
        {
          options.services.agent-cli = {
            enable = lib.mkEnableOption "agent-cli AI backend services";

            # Ollama LLM
            ollama = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Ollama LLM service";
              };
              acceleration = lib.mkOption {
                type = lib.types.enum [
                  "cuda"
                  "rocm"
                  "cpu"
                ];
                default = "cpu";
                description = "Hardware acceleration for Ollama";
              };
              host = lib.mkOption {
                type = lib.types.str;
                default = "127.0.0.1";
                description = "Host address for Ollama";
              };
              environmentVariables = lib.mkOption {
                type = lib.types.attrsOf lib.types.str;
                default = {
                  OLLAMA_KEEP_ALIVE = "1h";
                };
                description = "Environment variables for Ollama";
              };
            };

            # Wyoming Faster Whisper (ASR)
            whisper = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Wyoming Faster Whisper ASR";
              };
              model = lib.mkOption {
                type = lib.types.str;
                default = "tiny-int8";
                description = "Whisper model (tiny-int8, small, medium, large-v3)";
              };
              language = lib.mkOption {
                type = lib.types.str;
                default = "en";
                description = "Language for transcription";
              };
              device = lib.mkOption {
                type = lib.types.enum [
                  "cuda"
                  "cpu"
                ];
                default = "cpu";
                description = "Device for Whisper";
              };
              uri = lib.mkOption {
                type = lib.types.str;
                default = "tcp://127.0.0.1:10300";
                description = "URI for Whisper server";
              };
            };

            # Wyoming Piper (TTS)
            piper = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Wyoming Piper TTS";
              };
              voice = lib.mkOption {
                type = lib.types.str;
                default = "en_US-ryan-high";
                description = "Piper voice";
              };
              uri = lib.mkOption {
                type = lib.types.str;
                default = "tcp://127.0.0.1:10200";
                description = "URI for Piper server";
              };
            };

            # Wyoming OpenWakeWord
            openwakeword = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Wyoming OpenWakeWord";
              };
              preloadModels = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ "ok_nabu" ];
                description = "Wake word models to preload";
              };
              uri = lib.mkOption {
                type = lib.types.str;
                default = "tcp://127.0.0.1:10400";
                description = "URI for OpenWakeWord server";
              };
            };
          };

          config = lib.mkIf cfg.enable {
            # Ollama
            services.ollama = lib.mkIf cfg.ollama.enable {
              enable = true;
              acceleration = cfg.ollama.acceleration;
              host = cfg.ollama.host;
              environmentVariables = cfg.ollama.environmentVariables;
            };

            # Wyoming Faster Whisper
            services.wyoming.faster-whisper.servers.agent-cli = lib.mkIf cfg.whisper.enable {
              enable = true;
              model = cfg.whisper.model;
              language = cfg.whisper.language;
              device = cfg.whisper.device;
              uri = cfg.whisper.uri;
            };

            # Wyoming Piper
            services.wyoming.piper.servers.agent-cli = lib.mkIf cfg.piper.enable {
              enable = true;
              voice = cfg.piper.voice;
              uri = cfg.piper.uri;
            };

            # Wyoming OpenWakeWord
            services.wyoming.openwakeword = lib.mkIf cfg.openwakeword.enable {
              enable = true;
              preloadModels = cfg.openwakeword.preloadModels;
              uri = cfg.openwakeword.uri;
            };
          };
        };
    };
}
