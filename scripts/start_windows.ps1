# Build (if needed) and run the FinAlly container. Safe to re-run.
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Image = "finally"
$Container = "finally"
$Port = 8000
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is not running. Start Docker Desktop and try again."
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "No .env found - creating one from .env.example."
    Copy-Item ".env.example" ".env"
    Write-Host "Add your OPENROUTER_API_KEY to .env to enable the AI chat."
}

New-Item -ItemType Directory -Force -Path "db" | Out-Null

docker image inspect $Image *> $null
$imageMissing = ($LASTEXITCODE -ne 0)

if ($Build -or $imageMissing) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed."; exit 1 }
}

$running = docker ps -q -f "name=^$Container$"
if ($running) {
    Write-Host "Container '$Container' is already running."
    if ($Build) {
        Write-Host "Recreating it with the freshly built image..."
        docker rm -f $Container | Out-Null
        $running = $null
    }
}

if (-not $running) {
    $existing = docker ps -aq -f "name=^$Container$"
    if ($existing) { docker rm -f $Container | Out-Null }

    $dbMount = "$($Root -replace '\\', '/')/db:/app/db"
    docker run -d --name $Container -p "$($Port):8000" --env-file .env -v $dbMount $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to start container."; exit 1 }
}

Write-Host -NoNewline "Waiting for FinAlly to come up"
$healthy = $false
foreach ($i in 1..60) {
    try {
        Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $healthy = $true
        break
    } catch {
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 1
    }
}
Write-Host ""

if (-not $healthy) {
    Write-Host "FinAlly did not become healthy. Recent logs:"
    docker logs --tail 50 $Container
    exit 1
}

Write-Host "FinAlly is running at $Url"
Write-Host "Stop it with: scripts\stop_windows.ps1"

if (-not $NoBrowser) {
    Start-Process $Url
}
