#!/bin/bash
# Setup script for Trader
# Creates directories, copies .env template, installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Trader Setup"
echo "=========================================="
echo ""

# GS-001: Python version check (3.11+)
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "")
if [ -z "$PYTHON_VERSION" ]; then
    echo "❌ Python 3 is required but not installed."
    echo ""
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

# Extract major and minor version
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

# Check if version is 3.11+
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo "❌ Python 3.11+ required, but found $PYTHON_VERSION"
    echo ""
    echo "Your current Python version is too old. Please upgrade:"
    echo "  macOS:   brew install python@3.11"
    echo "  Ubuntu:  sudo apt update && sudo apt install python3.11"
    echo "  Windows: Download from https://python.org/downloads"
    echo ""
    echo "Or use a version manager:"
    echo "  pyenv:   pyenv install 3.11 && pyenv global 3.11"
    exit 1
fi

echo "✅ Found Python $PYTHON_VERSION (meets requirement 3.11+)"
echo ""

# Create directories
echo "Creating directories..."
mkdir -p data/config
mkdir -p data/credentials
mkdir -p scans
mkdir -p reports
mkdir -p memory
echo "✅ Directories created"
echo ""

# Copy .env.example to .env if it doesn't exist
if [ -f .env ]; then
    echo "✅ .env file already exists (keeping existing)"
else
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env from template"
        echo "⚠️  IMPORTANT: Edit .env and add your API keys:"
        echo "   - ALPACA_API_KEY and ALPACA_SECRET_KEY (for trading)"
        echo "   - TELEGRAM_BOT_TOKEN (optional, for reports)"
        echo ""
    else
        echo "❌ .env.example not found"
        exit 1
    fi
fi

# Install dependencies
echo "Installing dependencies..."
REQ_FILE="requirements/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    pip3 install -r "$REQ_FILE" --quiet
    echo "✅ Dependencies installed"
else
    echo "❌ $REQ_FILE not found"
    exit 1
fi
echo ""

# Install package in editable mode
echo "Installing trader package in editable mode..."
if [ -f pyproject.toml ]; then
    pip3 install -e . --quiet
    echo "✅ Package installed (pip install -e .)"
else
    echo "⚠️  pyproject.toml not found, skipping editable install"
fi
echo ""

# Run first-time setup scripts if keys are not configured
echo "Checking Alpaca configuration..."
if [ -f data/config/alpaca_config.json ] || [ -n "$ALPACA_API_KEY" ]; then
    echo "✅ Alpaca credentials found"
else
    echo "⚠️  Alpaca credentials not configured"
    echo "   Run: python3 scripts/setup_alpaca.py"
    echo "   Or edit .env file with your keys"
fi
echo ""

# Install pre-commit hooks (optional)
echo "Setting up pre-commit hooks..."
if command -v pre-commit >/dev/null 2>&1; then
    pre-commit install
    echo "✅ Pre-commit hooks installed"
    echo "   Run 'pre-commit run --all-files' to check all files"
else
    echo "⚠️  pre-commit not installed (run: pip install pre-commit)"
fi
echo ""

# Success message
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your API keys:"
echo "   nano .env"
echo ""
echo "2. Run your first analysis:"
echo "   python3 scripts/analyze_ticker.py AAPL"
echo ""
echo "3. Start paper trading (after configuring Alpaca):"
echo "   python3 scripts/paper_engine_alpaca.py"
echo ""
echo "Development commands:"
echo "   make test          # Run tests"
echo "   make lint          # Run linter"
echo "   pre-commit run     # Run pre-commit hooks manually"
echo ""
echo "For more info:"
echo "   cat README.md | head -100"
echo "   cat AGENTS.MD"
echo ""
