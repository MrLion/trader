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

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>/dev/null || echo "not found")
if [ "$PYTHON_VERSION" = "not found" ]; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi
echo "✅ Found $PYTHON_VERSION"
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
if [ -f requirements.txt ]; then
    pip3 install -r requirements.txt --quiet
    echo "✅ Dependencies installed"
else
    echo "❌ requirements.txt not found"
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
