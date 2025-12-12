#!/usr/bin/env bash
echo "🧠 Starting MLX LLM Server on port 8080..."

# Check if running on macOS with Apple Silicon
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ MLX only works on macOS with Apple Silicon."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "❌ MLX requires Apple Silicon (M1/M2/M3/M4). Intel Macs are not supported."
    exit 1
fi

# Default model - can be overridden with MLX_MODEL environment variable
# Popular options:
#   - mlx-community/Qwen3-4B-4bit (fast, high quality, default)
#   - mlx-community/Qwen3-8B-4bit (larger, even better quality)
#   - mlx-community/gpt-oss-20b-MXFP4-Q8 (20B parameter, high quality)
MODEL="${MLX_MODEL:-mlx-community/Qwen3-4B-4bit}"
PORT="${MLX_PORT:-10500}"

echo "📦 Model: $MODEL"
echo "🔌 Port: $PORT"
echo ""
echo "Usage with agent-cli:"
echo "  agent-cli transcribe --llm --llm-provider openai --openai-base-url http://localhost:$PORT/v1 --llm-openai-model $MODEL"
echo "  agent-cli autocorrect --llm-provider openai --openai-base-url http://localhost:$PORT/v1 --llm-openai-model $MODEL"
echo ""
echo "To make MLX the default, add to ~/.config/agent-cli/config.toml:"
echo "  [defaults]"
echo "  llm_provider = \"openai\""
echo "  openai_base_url = \"http://localhost:$PORT/v1\""
echo "  llm_openai_model = \"$MODEL\""
echo ""

# Run mlx-lm server using uvx
# --host 0.0.0.0 allows connections from other machines/tools
uvx --python 3.12 \
    --from "mlx-lm" \
    mlx_lm.server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port "$PORT"
