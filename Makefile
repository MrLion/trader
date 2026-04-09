# Trader Makefile
# A systematic stock trading workflow system

.PHONY: help setup install test test-coverage clean lint format pre-commit pre-commit-all

# Default target shows help
help:
	@echo "Trader - Systematic Trading Workflow"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "  setup          - Initial setup (creates directories, installs deps, copies .env, hooks)"
	@echo "  install        - Install/update dependencies only"
	@echo "  install-dev    - Install with dev dependencies (pre-commit, black, flake8)"
	@echo "  test           - Run test suite with coverage"
	@echo "  test-coverage  - Generate HTML coverage report"
	@echo "  pre-commit     - Run pre-commit hooks on staged files"
	@echo "  pre-commit-all - Run pre-commit hooks on all files"
	@echo "  lint           - Run linter on scripts"
	@echo "  format         - Format code with black"
	@echo "  clean          - Remove temporary files and cache"
	@echo ""
	@echo "Quick commands:"
	@echo "  make setup     - First time setup"
	@echo "  make test      - Run tests"
	@echo ""

# Initial setup
setup:
	@echo "Running Trader setup..."
	@bash setup.sh

# Install dependencies only (production)
install:
	@echo "Installing dependencies..."
	@pip3 install -e .

# Install with dev dependencies
install-dev:
	@echo "Installing with dev dependencies..."
	@pip3 install -e ".[dev]"
	@echo "✅ Installed with dev dependencies (pre-commit, black, flake8, etc.)"

# Run tests
test:
	@echo "Running tests..."
	@PAPER_TRADING_DATA_DIR=/tmp/test_data python3 -m pytest tests/ -v --cov=traderlib --cov=scripts --cov-branch

# Run tests with coverage report
test-coverage:
	@echo "Running tests with coverage..."
	@PAPER_TRADING_DATA_DIR=/tmp/test_data python3 -m pytest tests/ -v --cov=traderlib --cov=scripts --cov-branch --cov-report=html
	@echo "Coverage report: .gstack/qa-reports/coverage/html/index.html"

# Run pre-commit hooks on staged files
pre-commit:
	@echo "Running pre-commit hooks..."
	@pre-commit run

# Run pre-commit hooks on all files
pre-commit-all:
	@echo "Running pre-commit hooks on all files..."
	@pre-commit run --all-files

# Lint scripts
lint:
	@echo "Running linter..."
	@flake8 scripts/ traderlib/ tests/ --max-line-length=120 --extend-ignore=E203,W503

# Format code
format:
	@echo "Formatting code..."
	@black scripts/ traderlib/ tests/

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"
