# Stop FinAlly (Windows). Safe to run repeatedly; never touches the data volume.
#
# Mirrors scripts/stop_mac.sh. The shell pair is the automatically verified
# one; change the two together.

$ErrorActionPreference = "Stop"

$ContainerName = if ($env:FINALLY_CONTAINER) { $env:FINALLY_CONTAINER } else { "finally" }
$VolumeName    = if ($env:FINALLY_VOLUME)    { $env:FINALLY_VOLUME }    else { "finally-data" }

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is installed but the daemon isn't running. Open Docker Desktop and try again."
    exit 1
}

# -a so a stopped-but-present container is still cleaned up. Anchored filter,
# same reason as the start script.
$Existing = docker ps -aq --filter "name=^$ContainerName$"
if ($Existing) {
    docker rm -f $ContainerName *> $null
    Write-Host "FinAlly stopped and removed."
} else {
    Write-Host "FinAlly is not running."
}

Write-Host "Your data volume ($VolumeName) was left in place - cash, positions, and history are safe."
