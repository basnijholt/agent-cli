# PowerShell script to run Wyoming Faster Whisper on Windows
# Run with: powershell -ExecutionPolicy Bypass -File scripts/run-whisper-windows.ps1

Write-Host "🎤 Starting Wyoming Faster Whisper on port 10300..." -ForegroundColor Cyan

# Create .runtime directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ScriptDir ".runtime"
$WhisperDataDir = Join-Path $RuntimeDir "whisper-data"
if (-not (Test-Path $WhisperDataDir)) {
    New-Item -ItemType Directory -Path $WhisperDataDir -Force | Out-Null
}

# Detect if CUDA is available
$Device = "cpu"
$Model = "tiny"

try {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidiaSmi) {
        $null = & nvidia-smi 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "⚡ NVIDIA GPU detected" -ForegroundColor Green
            $Device = "cuda"
            $Model = "large-v3"
        }
    }
} catch {
    # nvidia-smi not found or failed
}

if ($Device -eq "cpu") {
    Write-Host "💻 No GPU detected or CUDA unavailable, using CPU" -ForegroundColor Yellow
}

# Allow override via environment variables
if ($env:WHISPER_DEVICE) { $Device = $env:WHISPER_DEVICE }
if ($env:WHISPER_MODEL) { $Model = $env:WHISPER_MODEL }

Write-Host "📦 Using model: $Model on device: $Device" -ForegroundColor Cyan

# Run Wyoming Faster Whisper using uvx
uvx --python 3.12 `
    --from "git+https://github.com/rhasspy/wyoming-faster-whisper.git@v3.0.1" `
    wyoming-faster-whisper `
    --model $Model `
    --language en `
    --device $Device `
    --uri "tcp://0.0.0.0:10300" `
    --data-dir $WhisperDataDir `
    --download-dir $WhisperDataDir
