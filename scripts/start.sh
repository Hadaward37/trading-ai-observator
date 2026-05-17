#!/usr/bin/env bash
# ── Trading AI Observator — Linux/macOS startup script ───────────────────────
#
# Usage:
#   ./scripts/start.sh          — normal start
#   ./scripts/start.sh --setup  — create venv + install deps, then start

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

SETUP=false
for arg in "$@"; do
    [[ "$arg" == "--setup" ]] && SETUP=true
done

step() { echo ""; echo "==> $1"; }

# ── Python check ──────────────────────────────────────────────────────────────
step "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.11+."
    exit 1
fi
python3 --version

# ── Virtual environment ───────────────────────────────────────────────────────
if $SETUP || [[ ! -d "venv" ]]; then
    step "Creating virtual environment..."
    python3 -m venv venv
fi

step "Activating virtual environment..."
source venv/bin/activate

# ── Dependencies ──────────────────────────────────────────────────────────────
if $SETUP; then
    step "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# ── Ensure .env ───────────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    step "Creating .env from .env.example..."
    cp .env.example .env
    echo "  .env created. Edit it if needed."
fi

# ── Start ─────────────────────────────────────────────────────────────────────
step "Starting Trading AI Observator..."
echo "  Dashboard: http://localhost:8000/docs"
echo "  Press Ctrl+C to stop."
echo ""

python -m app.main
