# Open TCP 8080 so your Android phone can reach the dashboard on the same Wi-Fi.

$ErrorActionPreference = "Stop"
$Port = 8080
if ($env:PORT) { $Port = [int]$env:PORT }

$ruleName = "MT5 Vision RAG Brain $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
    Write-Host "Firewall rule created for TCP $Port"
} else {
    Write-Host "Firewall rule already exists"
}
