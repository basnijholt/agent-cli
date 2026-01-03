# PowerShell script to run Wyoming Piper TTS on Windows
# Run with: powershell -ExecutionPolicy Bypass -File scripts/run-piper-windows.ps1

Write-Host "🔊 Starting Wyoming Piper on port 10200..." -ForegroundColor Cyan

# Create .runtime directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ScriptDir ".runtime"
$PiperDataDir = Join-Path $RuntimeDir "piper-data"
if (-not (Test-Path $PiperDataDir)) {
    New-Item -ItemType Directory -Path $PiperDataDir -Force | Out-Null
}

# Download voice if not present
$VoiceDir = Join-Path $PiperDataDir "en_US-lessac-medium"
if (-not (Test-Path $VoiceDir)) {
    Write-Host "⬇️ Downloading voice model..." -ForegroundColor Yellow
    Push-Location $PiperDataDir
    uvx --python 3.12 --from piper-tts python -m piper.download_voices en_US-lessac-medium
    Pop-Location
}

# Run Wyoming Piper using uvx
uvx --python 3.12 `
    --from "git+https://github.com/rhasspy/wyoming-piper.git@v2.1.1" `
    wyoming-piper `
    --voice en_US-lessac-medium `
    --uri "tcp://0.0.0.0:10200" `
    --data-dir $PiperDataDir `
    --download-dir $PiperDataDir
