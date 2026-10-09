# Pull the local models the brain expects. Run after installing Ollama for Windows.

$ErrorActionPreference = "Stop"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Error "Ollama is not on PATH. Install it from https://ollama.com/download then reopen PowerShell."
}

$models = @("llava", "llama3.1", "nomic-embed-text")
foreach ($model in $models) {
    Write-Host "Pulling $model ..."
    ollama pull $model
}

Write-Host "Models ready. You can now run windows\Start-VisionBrain.ps1"
