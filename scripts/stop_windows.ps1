# Stop and remove the FinAlly container. Database files in db/ are left untouched.
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Container = "finally"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running - nothing to stop."
    exit 0
}

$existing = docker ps -aq -f "name=^$Container$"
if (-not $existing) {
    Write-Host "Container '$Container' is not running."
    exit 0
}

docker rm -f $Container | Out-Null
Write-Host "Stopped and removed container '$Container'. Your data in db/ is preserved."
