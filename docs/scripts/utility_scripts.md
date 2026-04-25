# Utility Scripts

Setup, validation, sync, and maintenance tools.

---

## doctor.py — System Health Check

Validates the trading environment and reports actionable fixes.

```bash
# Full health check
python3 scripts/doctor.py

# Or via Make
make doctor
```

**Checks:**
- Python version (3.11+)
- Required dependencies installed
- Alpaca API credentials configured
- Directory structure (`data/`, `scans/`, `reports/`)
- Watchlist file exists and is valid
- Telegram config (if `TELEGRAM_BOT_TOKEN` set)
- Git hooks installed

---

## setup_alpaca.py — Credential Setup

Configures Alpaca API credentials and migrates legacy JSON configs.

```bash
python3 scripts/setup_alpaca.py
```

**What it does:**
- Prompts for API key and secret
- Writes to `.env` file
- Migrates old `config/secrets/alpaca_config.json` if present

---

## validate_alpaca.py — API Validation

Verifies Alpaca API connectivity and permissions.

```bash
python3 scripts/validate_alpaca.py
```

**Validates:**
- REST API connectivity
- WebSocket connectivity
- Account status
- Market data permissions
- Order submission permissions (paper)

---

## sync_state.py — Force Sync

Reconciles local paper trading state with live Alpaca API.

```bash
python3 scripts/sync_state.py
```

**Use when:**
- Local state diverges from Alpaca (partial fills, manual orders)
- Removing test/development trades
- Recovering from crashes

---

## clean_test_trades.py — Cleanup

Removes test and development entries from `paper_trades.jsonl`.

```bash
# Preview what would be removed
python3 scripts/clean_test_trades.py --dry-run

# Clean test trades
python3 scripts/clean_test_trades.py
```

**Pattern detection:** Identifies trades with:
- Test tickers (AAPL-TEST, etc.)
- Zero or tiny position sizes
- Unrealistic prices
- Missing required fields

---

## risk_config_demo.py — Risk Config Demo

Interactive demonstration of the flexible risk configuration system.

```bash
python3 scripts/risk_config_demo.py
```

**Shows:**
- Position sizing formulas
- Risk profile comparison (conservative vs aggressive)
- Stop distance calculations
- Triple-constraint system in action

---

## Related

- [Getting Started](../getting-started.md) — Full onboarding
- [Configuration Reference](../config/configuration-reference.md) — All config options
- [DEVELOPMENT.md](../DEVELOPMENT.md) — Development setup
