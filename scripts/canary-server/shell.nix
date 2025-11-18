{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python and uv
    python313
    uv

    # System libraries (for ldconfig, needed by triton)
    glibc.bin

    # Audio libraries
    ffmpeg
  ];

  shellHook = ''
    # Set up CUDA environment (use system NVIDIA drivers and CUDA libraries)
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:/run/current-system/sw/lib:$LD_LIBRARY_PATH

    # Add ldconfig to PATH (required by triton)
    export PATH=${pkgs.glibc.bin}/bin:$PATH

    # Canary server defaults
    export CANARY_PORT=9898
    export CANARY_DEVICE=cuda

    echo "CUDA environment configured (using system NVIDIA drivers)"
    echo "Run 'uv sync' to install dependencies"
    echo "Then run 'uv run server.py' to start the server"
  '';
}
