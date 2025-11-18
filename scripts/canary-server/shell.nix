{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

let
  # Wrapper script for ldconfig (triton hardcodes /sbin/ldconfig)
  ldconfigWrapper = pkgs.writeScriptBin "ldconfig" ''
    #!${pkgs.bash}/bin/bash
    exec ${pkgs.glibc.bin}/bin/ldconfig "$@"
  '';
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python and uv
    python313
    uv

    # ldconfig wrapper (triton needs this at /sbin/ldconfig)
    ldconfigWrapper

    # Audio libraries
    ffmpeg
  ];

  shellHook = ''
    # Set up CUDA environment (use system NVIDIA drivers and CUDA libraries)
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:/run/current-system/sw/lib:$LD_LIBRARY_PATH

    # Create /sbin symlink for ldconfig (triton hardcodes this path)
    mkdir -p .nix-sbin
    ln -sf ${ldconfigWrapper}/bin/ldconfig .nix-sbin/ldconfig

    # Prepend our fake /sbin to PATH so subprocess.Popen finds it
    export PATH=$PWD/.nix-sbin:$PATH

    # Canary server defaults
    export CANARY_PORT=9898
    export CANARY_DEVICE=cuda

    echo "CUDA environment configured (using system NVIDIA drivers)"
    echo "Run: nix-shell --run 'uv run server.py'"
  '';
}
