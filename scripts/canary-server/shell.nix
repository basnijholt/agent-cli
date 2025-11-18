{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python and uv
    python313
    uv

    # CUDA support
    cudaPackages.cudatoolkit
    cudaPackages.cudnn
    linuxPackages.nvidia_x11

    # System libraries
    glibc
    glibc.bin

    # Audio libraries
    ffmpeg
    sox
  ];

  shellHook = ''
    # Set up CUDA environment
    export CUDA_PATH=${pkgs.cudaPackages.cudatoolkit}
    export LD_LIBRARY_PATH=${pkgs.linuxPackages.nvidia_x11}/lib:${pkgs.cudaPackages.cudatoolkit}/lib:${pkgs.cudaPackages.cudnn}/lib:$LD_LIBRARY_PATH
    export EXTRA_LDFLAGS="-L${pkgs.linuxPackages.nvidia_x11}/lib"
    export EXTRA_CCFLAGS="-I${pkgs.cudaPackages.cudatoolkit}/include"

    # Add ldconfig to PATH
    export PATH=${pkgs.glibc.bin}/bin:$PATH

    # Canary server defaults
    export CANARY_PORT=9898
    export CANARY_DEVICE=cuda

    echo "CUDA environment configured"
    echo "CUDA_PATH: $CUDA_PATH"
    echo "Run 'uv sync' to install dependencies"
    echo "Then run 'uv run server.py' to start the server"
  '';
}
