#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AI Job Hunter — First-Run Setup Script
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

echo -e "${CYAN}"
echo "  ██╗ ██████╗ ██████╗     ██╗  ██╗██╗   ██╗███╗   ██╗████████╗███████╗██████╗ "
echo "  ██║██╔═══██╗██╔══██╗    ██║  ██║██║   ██║████╗  ██║╚══██╔══╝██╔════╝██╔══██╗"
echo "  ██║██║   ██║██████╔╝    ███████║██║   ██║██╔██╗ ██║   ██║   █████╗  ██████╔╝"
echo "  ██║██║   ██║██╔══██╗    ██╔══██║██║   ██║██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗"
echo "  ██║╚██████╔╝██████╔╝    ██║  ██║╚██████╔╝██║ ╚████║   ██║   ███████╗██║  ██║"
echo "  ╚═╝ ╚═════╝ ╚═════╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"
echo -e "${RESET}"
echo "  AI Job Hunter — Setup"
echo

# ── Python version check ──────────────────────────────────────────────────────
info "Checking Python version..."
PYTHON=$(command -v python3 || command -v python || error "Python not found")
PY_VER=$($PYTHON --version 2>&1 | awk '{print $2}')
info "Found Python $PY_VER at $PYTHON"
MAJOR=$(echo $PY_VER | cut -d. -f1)
MINOR=$(echo $PY_VER | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    error "Python 3.10+ required. Found $PY_VER"
fi
success "Python $PY_VER OK"

# ── Virtual environment ────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    success "Virtual environment created at .venv"
else
    info "Virtual environment already exists"
fi

# Activate
source .venv/bin/activate
info "Virtual environment activated"

# ── Pip upgrade + deps ────────────────────────────────────────────────────────
info "Upgrading pip..."
pip install --quiet --upgrade pip

info "Installing Python dependencies (this may take a few minutes)..."
pip install --quiet -r requirements.txt
success "Python dependencies installed"

# ── Playwright ────────────────────────────────────────────────────────────────
info "Installing Playwright Chromium browser..."
playwright install chromium --with-deps
success "Playwright ready"

# ── spaCy model ───────────────────────────────────────────────────────────────
info "Downloading spaCy English model..."
python -m spacy download en_core_web_sm --quiet
success "spaCy model ready"

# ── Config ────────────────────────────────────────────────────────────────────
if [ ! -f "config/config.yaml" ]; then
    info "Creating config from example..."
    cp config/config.example.yaml config/config.yaml
    warn "Edit config/config.yaml to add your Naukri credentials and Telegram token!"
else
    info "config/config.yaml already exists — skipping"
fi

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    info "Creating .env from example..."
    cp .env.example .env
    warn "Edit .env to add secrets (or set them in config/config.yaml)"
fi

# ── Data directories ──────────────────────────────────────────────────────────
info "Creating data directories..."
mkdir -p data/cache data/models data/logs data/exports
success "Directories ready"

# ── Resume check ──────────────────────────────────────────────────────────────
if [ ! -f "data/resume.pdf" ]; then
    warn "No resume found at data/resume.pdf"
    warn "Place your resume PDF at: $(pwd)/data/resume.pdf"
else
    success "Resume found at data/resume.pdf"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
success "Setup complete!"
echo
echo -e "  ${CYAN}Next steps:${RESET}"
echo "  1. Edit config/config.yaml  — add Naukri email/password + Telegram token"
echo "  2. Place resume at          — data/resume.pdf"
echo "  3. Run the agent            — python main.py"
echo "  4. Or run Docker            — docker compose up --build"
echo "  5. Dashboard                — http://localhost:8000"
echo "  6. Telegram bot             — /start in your bot chat"
echo
