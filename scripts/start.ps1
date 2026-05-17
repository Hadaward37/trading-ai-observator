# ── Trading AI Observator — Windows startup script ───────────────────────────
#
# Usage:
#   .\scripts\start.ps1           — normal start
#   .\scripts\start.ps1 -Setup    — create venv + install deps, then start
#
param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

# ── Check Python ──────────────────────────────────────────────────────────────
Write-Step "Checking Python version..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "ERROR: python not found in PATH. Install Python 3.11+." -ForegroundColor Red
    exit 1
}
$version = python --version 2>&1
Write-Host "Found: $version"

# ── Virtual environment ───────────────────────────────────────────────────────
$VenvPath = Join-Path $ProjectRoot "venv"
if ($Setup -or -not (Test-Path $VenvPath)) {
    Write-Step "Creating virtual environment..."
    python -m venv venv
}

# ── Activate venv ─────────────────────────────────────────────────────────────
Write-Step "Activating virtual environment..."
$activateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "ERROR: venv activation script not found. Run with -Setup flag." -ForegroundColor Red
    exit 1
}
& $activateScript

# ── Install dependencies ──────────────────────────────────────────────────────
if ($Setup) {
    Write-Step "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
}

# ── Ensure .env exists ────────────────────────────────────────────────────────
if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Step "Creating .env from .env.example..."
    Copy-Item "$ProjectRoot\.env.example" "$ProjectRoot\.env"
    Write-Host "  .env created. Edit it if needed." -ForegroundColor Yellow
}

# ── Start the system ──────────────────────────────────────────────────────────
Write-Step "Starting Trading AI Observator..."
Write-Host "  Dashboard: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

python -m app.main
