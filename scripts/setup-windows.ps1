# PowerShell script to set up agent-cli services on Windows
# Run with: powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "🚀 Setting up agent-cli services on Windows..." -ForegroundColor Cyan

# Create .runtime directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ScriptDir ".runtime"
if (-not (Test-Path $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

# Check if uv is installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "📦 Installing uv..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "✅ uv is already installed" -ForegroundColor Green
}

# Check if Ollama is installed
Write-Host "🧠 Checking Ollama..." -ForegroundColor Yellow
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "📦 Ollama is not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please download and install Ollama from:" -ForegroundColor Yellow
    Write-Host "  https://ollama.com/download/windows" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "After installing, run this script again." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "✅ Ollama is already installed" -ForegroundColor Green
}

# Install agent-cli
Write-Host "🤖 Installing/upgrading agent-cli..." -ForegroundColor Yellow
uv tool install --upgrade agent-cli

# Preload default Ollama model
Write-Host "⬇️ Preloading default Ollama model (gemma3:4b)..." -ForegroundColor Yellow
Write-Host "⏳ This may take a few minutes depending on your internet connection..." -ForegroundColor Gray
ollama pull gemma3:4b

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "You can now run the services:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option 1 - Run all services at once:" -ForegroundColor White
Write-Host "  .\scripts\start-all-services-windows.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "Option 2 - Run services individually:" -ForegroundColor White
Write-Host "  1. Ollama: ollama serve  (or it runs automatically as a service)" -ForegroundColor Gray
Write-Host "  2. Whisper: .\scripts\run-whisper-windows.ps1" -ForegroundColor Gray
Write-Host "  3. Piper: .\scripts\run-piper-windows.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "📝 Note: Scripts use uvx to run without needing virtual environments." -ForegroundColor Yellow
Write-Host "For GPU acceleration, make sure NVIDIA drivers and CUDA 12 are installed." -ForegroundColor Yellow
Write-Host "🎉 agent-cli has been installed and is ready to use!" -ForegroundColor Green
