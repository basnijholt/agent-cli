# Using agent-cli with llama-server (llama-cpp)

This guide explains how to use agent-cli with llama-server, which provides an OpenAI-compatible API for running local LLM models.

## Prerequisites

1. Install and set up llama-cpp with llama-server support
2. Download a compatible GGUF model file

## Starting llama-server

Start the llama-server with your model:

```bash
# Example with a 3B parameter model
llama-server \
  -m /path/to/your/model.gguf \
  -c 2048 \
  --host 0.0.0.0 \
  --port 8080
```

## Configuration

### Option 1: Using Configuration File

Add to your `~/.config/agent-cli/config.toml` or `./agent-cli-config.toml`:

```toml
[defaults]
llm-provider = "openai"
llm-openai-model = "your-model-name"  # Can be anything, llama-server ignores this
openai-base-url = "http://localhost:8080/v1"
# openai-api-key is not required for llama-server
```

### Option 2: Using Command Line

```bash
# Example: Autocorrect text
agent-cli autocorrect \
  --llm-provider openai \
  --llm-openai-model llama-3.2-3b \
  --openai-base-url http://localhost:8080/v1

# Example: Transcribe and process audio
agent-cli transcribe \
  --llm-provider openai \
  --llm-openai-model llama-3.2-3b \
  --openai-base-url http://localhost:8080/v1 \
  --llm

# Example: Chat assistant
agent-cli chat \
  --llm-provider openai \
  --llm-openai-model llama-3.2-3b \
  --openai-base-url http://localhost:8080/v1
```

## Notes

- The `--llm-openai-model` parameter is sent to llama-server but typically ignored (the model is already loaded)
- No API key is required when using llama-server
- Make sure the base URL includes the `/v1` suffix for OpenAI API compatibility
- Performance depends on your hardware and the model size

## Advantages

- Complete privacy - all processing happens locally
- No API costs
- No internet connection required (after model download)
- Full control over the model and parameters
- Can use any GGUF-compatible model

## Troubleshooting

If you encounter issues:

1. Verify llama-server is running: `curl http://localhost:8080/v1/models`
2. Check the llama-server logs for errors
3. Ensure the base URL includes `/v1` at the end
4. Try a simple curl test:
   ```bash
   curl http://localhost:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "test",
       "messages": [{"role": "user", "content": "Hello"}]
     }'
   ```
