# Start FinAlly (Windows). Safe to run repeatedly.
#
# This mirrors scripts/start_mac.sh line for line. The shell pair is the one
# automatically verified in this project's CI/dev environment; no Windows
# runner exists there, so this file is verified by a human. Change the two
# together — a drift here creates a platform where the app behaves
# differently, and nobody would notice.

param(
    [switch]$Build,
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$ImageTag      = if ($env:FINALLY_IMAGE)     { $env:FINALLY_IMAGE }     else { "finally:latest" }
$ContainerName = if ($env:FINALLY_CONTAINER) { $env:FINALLY_CONTAINER } else { "finally" }
$VolumeName    = if ($env:FINALLY_VOLUME)    { $env:FINALLY_VOLUME }    else { "finally-data" }
$HostPort      = if ($env:FINALLY_PORT)      { $env:FINALLY_PORT }      else { "8000" }

# Resolve from this script's location, not the caller's cwd — same reason as
# the shell version.
Set-Location (Split-Path -Parent $PSScriptRoot)

# NOTE: $ErrorActionPreference = "Stop" does NOT make a failing native
# command throw. `docker` is a native command, so every invocation whose
# failure matters checks $LASTEXITCODE explicitly. This is the most common
# way a PowerShell port of a `set -e` script silently continues past a
# failed build.

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is installed but the daemon isn't running. Open Docker Desktop and try again."
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example."
    Write-Host "  Add your OPENROUTER_API_KEY to it to enable the AI copilot (everything else works without it)."
}

docker image inspect $ImageTag *> $null
$ImageMissing = ($LASTEXITCODE -ne 0)
if ($Build -or $ImageMissing) {
    Write-Host "Building $ImageTag ..."
    docker build -t $ImageTag .
    if ($LASTEXITCODE -ne 0) { Write-Error "Build failed."; exit 1 }
}

$Running = docker ps -q --filter "name=^$ContainerName$"
if ($Running) {
    Write-Host "FinAlly is already running."
} else {
    docker rm -f $ContainerName *> $null
    docker run -d `
        --name $ContainerName `
        -p "${HostPort}:8000" `
        -v "${VolumeName}:/app/db" `
        --env-file .env `
        $ImageTag *> $null
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to start container."; exit 1 }
    Write-Host "FinAlly started."
}

$Url = "http://localhost:$HostPort"
Write-Host "  $Url"

if ($Open) {
    Start-Process $Url
}
