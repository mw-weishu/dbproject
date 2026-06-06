#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sets up a local ArangoDB environment in Docker and imports CSKG data.

.DESCRIPTION
    - Pulls the ArangoDB Docker image if not present
    - Creates and starts the container (or starts it if already exists)
    - Waits for ArangoDB to be ready
    - Runs import_cskg.py to load cskg.tsv into the local instance
    - Prints ready-to-use CLI example commands

.PARAMETER Password
    Root password for the local ArangoDB instance. Defaults to 'localpass'.

.PARAMETER SkipImport
    If set, skips the data import step (useful if data is already loaded).

.PARAMETER Fresh
    If set, truncates existing collections before importing.

.EXAMPLE
    .\setup_env.ps1
    .\setup_env.ps1 -Password mysecret
    .\setup_env.ps1 -SkipImport
#>

param(
    [string]$Password  = "localpass",
    [switch]$SkipImport,
    [switch]$Fresh
)

$ErrorActionPreference = "Stop"

$CONTAINER  = "cskg_arangodb"
$PORT       = 8529
$DB         = "DB_Project"
$IMAGE      = "arangodb/arangodb:latest"
$TSV_FILE   = "cskg.tsv"

Write-Host ""
Write-Host "=============================================="
Write-Host "  CSKG Local Environment Setup"
Write-Host "=============================================="
Write-Host ""

# ── Step 1: Check Docker ──────────────────────────────────
Write-Host "[1/5] Checking Docker..."
try {
    $dockerVersion = docker --version
    Write-Host "  OK: $dockerVersion"
} catch {
    Write-Error "Docker is not installed or not in PATH. Install Docker Desktop and try again."
}

# ── Step 2: Pull image if missing ────────────────────────
Write-Host ""
Write-Host "[2/5] Checking ArangoDB image..."
$imageExists = docker images -q arangodb/arangodb 2>$null
if (-not $imageExists) {
    Write-Host "  Pulling $IMAGE (this may take a few minutes)..."
    docker pull $IMAGE
} else {
    Write-Host "  Image already present, skipping pull."
}

# ── Step 3: Create or start container ────────────────────
Write-Host ""
Write-Host "[3/5] Starting ArangoDB container '$CONTAINER'..."
$containerExists = docker ps -a --filter "name=^${CONTAINER}$" --format "{{.Names}}" 2>$null

if ($containerExists -eq $CONTAINER) {
    $running = docker ps --filter "name=^${CONTAINER}$" --format "{{.Names}}" 2>$null
    if ($running -eq $CONTAINER) {
        Write-Host "  Container already running."
    } else {
        Write-Host "  Container exists but stopped. Starting it..."
        docker start $CONTAINER | Out-Null
    }
} else {
    Write-Host "  Creating new container..."
    docker run -d `
        --name $CONTAINER `
        -p "${PORT}:8529" `
        -e ARANGO_ROOT_PASSWORD=$Password `
        $IMAGE | Out-Null
    Write-Host "  Container created."
}

# ── Step 4: Wait for ArangoDB to be ready ────────────────
Write-Host ""
Write-Host "[4/5] Waiting for ArangoDB to be ready..."
$maxWait  = 60   # seconds
$interval = 3
$elapsed  = 0
$ready    = $false

while ($elapsed -lt $maxWait) {
    try {
        $response = Invoke-WebRequest `
            -Uri "http://localhost:${PORT}/_api/version" `
            -UseBasicParsing `
            -TimeoutSec 2 `
            -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # 401 = ArangoDB is up but requires auth — that's ready enough
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode -eq 401) {
            $ready = $true
            break
        }
        # Otherwise not ready yet
    }
    Write-Host "  ...waiting (${elapsed}s elapsed)"
    Start-Sleep -Seconds $interval
    $elapsed += $interval
}

if (-not $ready) {
    Write-Error "ArangoDB did not become ready within ${maxWait}s. Check 'docker logs $CONTAINER'."
}
Write-Host "  ArangoDB is ready."

# ── Step 5: Import data ───────────────────────────────────
Write-Host ""
if ($SkipImport) {
    Write-Host "[5/5] Skipping import (-SkipImport was set)."
} else {
    if (-not (Test-Path $TSV_FILE)) {
        Write-Warning "  '$TSV_FILE' not found in current directory - skipping import."
        Write-Host "  Copy cskg.tsv here and re-run without -SkipImport to load data."
    } else {
        Write-Host "[5/5] Importing CSKG data (this may take several minutes)..."
        $freshFlag = if ($Fresh) { "--fresh" } else { "" }
        $importArgs = @(
            "import_cskg.py",
            "--url", "http://localhost:${PORT}",
            "--password", $Password,
            "--db", $DB
        )
        if ($Fresh) { $importArgs += "--fresh" }

        python @importArgs
    }
}

# ── Done: print usage ─────────────────────────────────────
Write-Host ""
Write-Host "=============================================="
Write-Host "  Setup complete!"
Write-Host "=============================================="
Write-Host ""
Write-Host "  Web dashboard : http://localhost:${PORT}"
Write-Host "  Username      : root"
Write-Host "  Password      : $Password"
Write-Host ""
Write-Host "  Example CLI commands (local Docker):"
Write-Host "    python cskg_cli.py --host localhost --port $PORT --db $DB --user root --password $Password successors /c/en/dog"
Write-Host "    python cskg_cli.py --host localhost --port $PORT --db $DB --user root --password $Password distant-antonyms /c/en/rollercoaster 17"
Write-Host ""
Write-Host "  To stop the container when done:"
Write-Host "    docker stop $CONTAINER"
Write-Host ""
Write-Host "  To restart it later (data is preserved):"
Write-Host "    docker start $CONTAINER"
Write-Host "    # then run queries straight away - no need to re-import"
Write-Host ""
