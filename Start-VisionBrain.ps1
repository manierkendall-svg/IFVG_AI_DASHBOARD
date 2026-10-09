# Start the Vision RAG brain, check Ollama, and print the phone dashboard URL.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Vision RAG Brain launcher" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not on PATH. Install Python 3.11+ from python.org and retry."
}

$OllamaHost = $env:OLLAMA_HOST
if (-not $OllamaHost) { $OllamaHost = "http://127.0.0.1:11434" }

try {
    $null = Invoke-RestMethod -Uri "$OllamaHost/api/tags" -TimeoutSec 3
    Write-Host "Ollama is reachable at $OllamaHost"
} catch {
    Write-Host "Ollama is not running. Start Ollama from the Start menu, then pull models:" -ForegroundColor Yellow
    Write-Host "  ollama pull llava"
    Write-Host "  ollama pull llama3.1"
    Write-Host "  ollama pull nomic-embed-text"
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

$Port = 8080
if ($env:PORT) { $Port = [int]$env:PORT }

$LocalIP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host ""
Write-Host "Dashboard on this PC:  http://127.0.0.1:$Port"
if ($LocalIP) {
    Write-Host "Android phone URL:     http://$LocalIP:$Port"
    Write-Host "Phone and PC must be on the same Wi-Fi. Add this URL as a Home screen app from Chrome."
}
Write-Host "MT5 WebRequest URL:    http://127.0.0.1:$Port"
Write-Host ""

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $Port
