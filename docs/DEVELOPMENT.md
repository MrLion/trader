# Development Guide

This guide covers development setup, testing, code quality, and CI/CD workflows for contributors to the Trader project.

---

## Development Setup

### One-Command Setup

```bash
# Run the setup script (creates directories, installs deps, copies .env, installs pre-commit hooks)
./setup.sh

# Or use Make
make setup
```

### Manual Setup

```bash
# 1. Install package in editable mode (recommended)
pip install -e .

# Or install dependencies only
pip install -r requirements/requirements.txt

# 2. Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys (optional, for Telegram and Alpaca)

# 3. Create required directories
mkdir -p data/config scans reports memory

# 4. (Optional) Install pre-commit hooks
pre-commit install

# 5. Run your first analysis
python3 scripts/entry_signals.py --ticker AAPL
```

---

## Development Commands

Use the Makefile for common development tasks:

```bash
# Setup (run once)
make setup              # Full setup (directories, deps, .env, pre-commit hooks)

# Testing
make test               # Run test suite with coverage
make test-coverage      # Generate HTML coverage report

# Code Quality (pre-commit hooks)
pre-commit run          # Run hooks on staged files
pre-commit run --all-files  # Run hooks on all files
make lint               # Run linter (flake8)
make format             # Format code with black

# Maintenance
make clean              # Remove cache files
```

---

## Pre-commit Hooks

Pre-commit hooks automatically check code quality before each commit:

```bash
# Install hooks (one-time setup)
pre-commit install

# Run manually
pre-commit run

# Skip hooks for a specific commit (emergency only)
git commit -m "message" --no-verify
```

Hooks configured:
- **trailing-whitespace** - Removes trailing whitespace
- **end-of-file-fixer** - Ensures files end with a newline
- **black** - Python code formatting
- **isort** - Import sorting
- **flake8** - Python linting
- **check-yaml/json/toml** - Syntax validation

---

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage report
pytest tests/ --cov=traderlib --cov=scripts --cov-branch --cov-report=html
open htmlcov/index.html
```

### Test Data Isolation

Tests use `PAPER_TRADING_DATA_DIR` environment variable to write to temporary directories:

```bash
# Run tests with custom data directory
export PAPER_TRADING_DATA_DIR=/tmp/trader_test
pytest tests/
```

---

## CI/CD

This project uses **GitHub Actions** for automated testing.

### Workflow Features
- **Multi-version testing:** Python 3.11, 3.12, 3.13
- **Coverage enforcement:** Fails if coverage drops below 50%
- **Automatic triggers:** Runs on every push to `main`/`develop` and all pull requests
- **Artifacts:** Coverage reports uploaded for each run

### Viewing Results

Check the **Actions** tab in GitHub to see:
- Test results per Python version
- Coverage reports
- Build status

### Coverage Reporting

Coverage reports are uploaded to:
- **Codecov** (if configured)
- **GitHub Artifacts** (retained for 7 days)

To generate coverage locally:

```bash
pytest tests/ --cov=traderlib --cov=scripts --cov-branch --cov-report=html
open htmlcov/index.html
```

---

## Project Structure

```
trader/
├── scripts/          - CLI tools for trading and analysis
├── traderlib/        - Library modules (imported by scripts)
├── tests/            - Test suite
├── data/             - Runtime data (watchlist, positions, trades)
├── scans/            - Daily CSV outputs from screens
├── reports/          - Generated HTML market reports
├── memory/           - Daily logs and curated memories
├── docs/             - Documentation and runbooks
├── config/           - Configuration files
└── .github/          - GitHub Actions workflows
```

### Key Library Modules (traderlib/)

| Module | Purpose |
|--------|---------|
| `alpaca_client.py` | Alpaca API client (REST + WebSocket) |
| `order_manager.py` | Order submission with rate limiting |
| `paper_state.py` | Position and portfolio state management |
| `paper_exits.py` | Exit rule engine (stops, trailing) |
| `risk_config.py` | Risk configuration and position sizing |
| `rate_limiter.py` | Rate limiting and circuit breaker |
| `trading_exceptions.py` | Structured exception handling |
| `backtest/` | Backtesting engine (data, execution, state, strategy, report) |

---

## Contributing Guidelines

### Before Committing

1. Run tests: `make test`
2. Run linting: `make lint`
3. Run formatting: `make format`
4. Check pre-commit hooks pass: `pre-commit run --all-files`

### Commit Message Format

Follow conventional commits:

```
feat: add new feature
fix: correct a bug
docs: update documentation
refactor: restructure code
test: add or update tests
chore: maintenance tasks
```

### Changelog

Update [CHANGELOG.md](../CHANGELOG.md) for user-facing changes.

---

## Environment Variables for Development

| Variable | Purpose | Default |
|----------|---------|---------|
| `PAPER_TRADING_DATA_DIR` | Data directory for paper trading state | `./data` |
| `PAPER_TRADING_TEST_MODE` | Enable test mode metadata tagging | `false` |
| `TRADER_WATCHLIST` | Path to custom watchlist CSV | `./data/watchlist.csv` |
| `TRADER_OUTPUT` | Path to custom output directory | `./reports` |

---

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError` for traderlib modules:

```bash
# Ensure package is installed in editable mode
pip install -e .
```

### Test Failures

If tests fail due to data pollution:

```bash
# Clean test data directory
rm -rf /tmp/paper_trading_test_*
```

### Pre-commit Hook Failures

If hooks fail on formatting:

```bash
# Auto-fix formatting
make format

# Re-run hooks
pre-commit run
```
