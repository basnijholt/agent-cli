# PowerShell script to start all agent-cli services on Windows
# Run with: powershell -ExecutionPolicy Bypass -File scripts/start-all-services-windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting all agent-cli services..." -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check if Windows Terminal is available for a nicer experience
$UseWindowsTerminal = $false
if (Get-Command wt -ErrorAction SilentlyContinue) {
    $UseWindowsTerminal = $true
}

if ($UseWindowsTerminal) {
    Write-Host "📺 Using Windows Terminal for multi-tab view..." -ForegroundColor Green

    # Start Windows Terminal with multiple tabs
    wt --title "agent-cli services" `
        new-tab --title "Ollama" powershell -NoExit -Command "ollama serve" `; `
        new-tab --title "Whisper" powershell -NoExit -ExecutionPolicy Bypass -File "$ScriptDir\run-whisper-windows.ps1" `; `
        new-tab --title "Piper" powershell -NoExit -ExecutionPolicy Bypass -File "$ScriptDir\run-piper-windows.ps1"

    Write-Host ""
    Write-Host "✅ Services started in Windows Terminal tabs!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📝 Tips:" -ForegroundColor Yellow
    Write-Host "  - Switch tabs with Ctrl+Tab" -ForegroundColor Gray
    Write-Host "  - Close all: Close the Windows Terminal window" -ForegroundColor Gray
} else {
    Write-Host "📺 Opening services in separate PowerShell windows..." -ForegroundColor Yellow

    # Start each service in a new PowerShell window
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'Ollama' -ForegroundColor Cyan; ollama serve"
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$ScriptDir\run-whisper-windows.ps1"
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$ScriptDir\run-piper-windows.ps1"

    Write-Host ""
    Write-Host "✅ Services started in separate windows!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📝 Note: Install Windows Terminal for a better multi-tab experience:" -ForegroundColor Yellow
    Write-Host "  winget install Microsoft.WindowsTerminal" -ForegroundColor Gray
}

Write-Host ""
Write-Host "🔌 Service ports:" -ForegroundColor Cyan
Write-Host "  - Ollama:  http://localhost:11434" -ForegroundColor Gray
Write-Host "  - Whisper: tcp://localhost:10300" -ForegroundColor Gray
Write-Host "  - Piper:   tcp://localhost:10200" -ForegroundColor Gray
Write-Host ""
Write-Host "🎉 You can now use agent-cli!" -ForegroundColor Green
Write-Host "  agent-cli transcribe" -ForegroundColor Gray
