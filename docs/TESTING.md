# Testing Guide

How to run, write, and maintain tests for the Trader project.

---

## Running Tests

### Full Suite

```bash
# Run all tests with coverage
make test

# Or directly
PAPER_TRADING_DATA_DIR=/tmp/test_data python3 -m pytest tests/ -v --cov=traderlib --cov=scripts --cov-branch
```

### Specific Tests

```bash
# Single test file
python3 -m pytest tests/test_alpaca_client_extended.py -v

# Single test class
python3 -m pytest tests/test_alpaca_client_extended.py::TestRateLimiter -v

# Single test method
python3 -m pytest tests/test_alpaca_client_extended.py::TestRateLimiter::test_backoff -v
```

### Coverage Report

```bash
# HTML coverage report
make test-coverage

# Or directly
PAPER_TRADING_DATA_DIR=/tmp/test_data pytest tests/ -v --cov=traderlib --cov=scripts --cov-branch --cov-report=html
```

Report opens at: `.gstack/qa-reports/coverage/html/index.html`

---

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures, sys.path setup
├── generate_fixtures.py    # Offline fixture generator
├── test_alpaca_*.py        # Alpaca client and integration
├── test_backtest_*.py      # Backtesting engine
├── test_paper_*.py         # Paper trading engine
├── test_stage2_*.py        # Stage 2 scoring
├── test_vcp_*.py           # VCP pattern detection
├── test_earnings_*.py      # Earnings calendar/provider
├── test_universe_*.py      # Universe builder
├── test_strategy_*.py      # Strategy plugins
├── test_reports.py         # Report generation
├── test_doctor.py          # System health checks
├── test_chaos.py           # Chaos/failure testing
└── ...
```

---

## Data Isolation

Tests use `PAPER_TRADING_DATA_DIR` to write to temporary directories:

```bash
export PAPER_TRADING_DATA_DIR=/tmp/trader_test
pytest tests/
```

This prevents test data from polluting production `data/` files.

---

## Mock Patterns

### Mocking yfinance

```python
from unittest.mock import MagicMock, patch
import pandas as pd

hist = pd.DataFrame({
    'Open': [100] * 200,
    'High': [102] * 200,
    'Low': [98] * 200,
    'Close': list(range(100, 300)),
    'Volume': [1_000_000] * 200,
}, index=pd.date_range(end='2026-04-21', periods=200, freq='D'))

mock_ticker = MagicMock()
mock_ticker.history.return_value = hist

with patch('module.yf.Ticker', return_value=mock_ticker):
    # Your test code
```

### Mocking Alpaca Client

```python
from unittest.mock import patch

with patch('traderlib.alpaca_client.AlpacaClient') as MockClient:
    mock = MockClient.return_value
    mock.get_account.return_value = {'equity': '50000'}
    # Your test code
```

### Using conftest.py Fixtures

```python
# tests/conftest.py sets up sys.path and shared fixtures
def pytest_configure(config):
    # Add project root to path
    pass
```

---

## Writing New Tests

### Naming Convention

```
test_{module}_{feature}.py
test_{module}.py          # For simple modules
```

### Test Class Structure

```python
import pytest

class TestMyFeature:
    def test_basic_behavior(self):
        """Test the happy path."""
        assert True

    def test_edge_case_empty_input(self):
        """Test empty/null input handling."""
        assert True

    def test_error_handling(self):
        """Test exception paths."""
        with pytest.raises(ValueError):
            raise ValueError("expected")
```

### Deterministic Data

Always use fixed seed data or explicit DataFrames. Never rely on live API data in tests.

---

## Coverage Expectations

| Module | Target Coverage |
|--------|-----------------|
| `traderlib/` | >= 50% |
| `scripts/` | >= 30% |
| `traderlib/backtest/` | >= 60% |

---

## Troubleshooting

### Tests fail with `ModuleNotFoundError`

```bash
# Ensure conftest.py is loaded
python3 -m pytest tests/ -v

# Or add paths manually
PYTHONPATH=/path/to/trader python3 -m pytest tests/
```

### Tests write to production data

Ensure `PAPER_TRADING_DATA_DIR` is set to a temp directory.

### Coverage report not generated

Install pytest-cov: `pip install pytest-cov`

---

## Related

- [DEVELOPMENT.md](DEVELOPMENT.md) — Development setup
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
- `tests/README.md` — Alpaca integration test notes
