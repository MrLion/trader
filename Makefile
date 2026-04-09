# Trader Makefile
# A systematic stock trading workflow system

.PHONY: help setup test clean lint format

# Default target shows help
help:
	@echo "Trader - Systematic Trading Workflow"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "  setup       - Initial setup (creates directories, installs deps, copies .env)"
	@echo "  install     - Install/update dependencies only"
	@echo "  test        - Run test suite with coverage"
	@echo "  clean       - Remove temporary files and cache"
	@echo "  lint        - Run linter on scripts"
	@echo "  format      - Format code (if black is installed)"
	@echo ""
	@echo "Quick commands:"
	@echo "  make setup  - First time setup"
	@echo "  make test   - Run tests"
	@echo ""

# Initial setup
setup:
	@echo "Running Trader setup..."
	@bash setup.sh

# Install dependencies only
install:
	@echo "Installing dependencies..."
	@pip3 install -r requirements.txt

# Run tests
test:
	@echo "Running tests..."
	@PAPER_TRADING_DATA_DIR=/tmp/test_data python3 -m pytest tests/ -v --cov=scripts --cov-branch

# Run tests with coverage report
test-coverage:
	@echo "Running tests with coverage..."
	@PAPER_TRADING_DATA_DIR=/tmp/test_data python3 -m pytest tests/ -v --cov=scripts --cov-branch --cov-report=html
	@echo "Coverage report: .gstack/qa-reports/coverage/html/index.html"

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"

# Lint scripts
lint:
	@echo "Running linter..."
	@which flake8 > /dev/null 2>&1 && flake8 scripts/ --max-line-length=120 --ignore=E501,W503 || echo "flake8 not installed, skipping"

# Format code
format:
	@echo "Formatting code..."
	@which black > /dev/null 2>&1 && black scripts/ tests/ || echo "black not installed, skipping"
