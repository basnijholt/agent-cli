{ pkgs ? import <nixpkgs> { config.allowUnfree = true; } }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python and uv
    python313
    uv

    # Audio libraries
    ffmpeg
  ];

  shellHook = ''
    # Set up CUDA environment (use system NVIDIA drivers and CUDA libraries)
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:/run/current-system/sw/lib:$LD_LIBRARY_PATH

    # Tell triton where to find libcuda.so (avoids calling /sbin/ldconfig)
    export TRITON_LIBCUDA_PATH=/run/opengl-driver/lib

    # PyTorch memory management - avoid fragmentation
    export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

    # Canary server defaults
    export CANARY_PORT=9898
    # CANARY_DEVICE auto-detects GPU with most free memory (override if needed)

    echo "CUDA environment configured (using system NVIDIA drivers)"
    echo "TRITON_LIBCUDA_PATH: $TRITON_LIBCUDA_PATH"
    echo "PYTORCH_CUDA_ALLOC_CONF: $PYTORCH_CUDA_ALLOC_CONF"
    echo "Run 'uv run server.py' to start the server"
  '';
}
