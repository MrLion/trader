# Changelog

All notable changes to this project will be documented in this file.

## [0.3.10] - 2026-04-10

### Fixed
- **Partial Fill Handling Not Implemented (FINDING-008)**
  - `PARTIAL_FILL` status existed but logic assumed full fills
  - Position created with full `order.qty` even if only partially filled
  - Fix: `check_order_status()` now captures `filled_qty` on every Alpaca check
  - Fix: `filled_qty` accumulates across partial fill events
  - Fix: Position creation uses actual `filled_qty` not `order.qty`
  - Fix: Partial fills logged with progress: "50/100 shares filled"

- **Dangerous Fallback Defaults (FINDING-005)**
  - `Position.from_dict()` silently defaulted `stop_price` to 5% below entry
  - Misrepresented actual risk when stop data unavailable
  - Fix: Positions with missing stops now marked as `UNSYNCED`
  - Fix: Sync from Alpaca now looks up stops from watchlist
  - Fix: Order fill requires explicit stop_price (no silent defaults)
  - Impact: No more hidden 5% stop assumptions

- **Split-Brain Vulnerability (FINDING-002)**
  - Position created locally before Alpaca confirmed fill
  - Crash between submit and fill = phantom position in local state
  - Fix: Order now stores entry metadata (`target_price`, `sector`, `expected_entry_price`)
  - Fix: Position creation moved to fill confirmation in `_process_pending_orders()`
  - Fix: `_execute_entry()` no longer creates position immediately
  - Impact: Eliminates phantom positions, ensures Alpaca is source of truth

- **Trade counters out of sync with trade log**
  - `sync_state.py` hardcoded `trade_count: 0` and `entries_today: 0`, causing data loss
  - Counters only incremented for trades through `PaperState.enter_position()`
  - No reconciliation between account file and trade log ground truth
  - Fix: Added `PaperState._reconcile_counters_from_log()` to count production trades from JSONL
  - Fix: Added `paper_portfolio.py reconcile` CLI command for manual fixes
  - Fix: Updated `sync_state.py` to preserve counts from trade log
  - Test trades excluded via `_meta.test_mode` flag and known patterns (AAPL@150)

### Changed
- **`paper_portfolio.py status`** now shows end-of-day (EOD) closing prices
  - Account Value = Cash + (positions × EOD close price)
  - Available Cash displayed separately
  - Position table shows EOD Close vs Entry price
  - Unrealized P&L calculated using EOD prices
- **`reconcile` command** defaults to $100,000 initial capital if non-standard value detected
  - Warns if initial_capital is not $100,000
  - Auto-corrects to standard value

## [0.3.9] - 2026-04-10

### Fixed
- **Order manager: stale test-order cleanup** (`fc84e37`)
  - `check_order_status` only matched IDs starting with `test-order-` (hyphen)
  - Exact-match `test-order` IDs (from some test files) were never cleaned up
  - Fix: also catch exact-match `test-order`, plus existing `test-order-*` and `mock-*` patterns

### Tests
- **paper_engine.py coverage: 66% → 88%** (`8021a6a`)
  - `_fetch_spy_data`: insufficient 5m history, <2 daily bars branch
  - `_analyze_ticker`: NaN pivot uses recent high, spy=None RS fallback, exception handler
  - `_check_entries`: all filter branches (score, distance, volume) + success path
  - `_check_exits`: exit triggered, hold, empty history, no positions, `_print_status`
- **paper_engine_alpaca.py coverage: 64% → 76%** (`8021a6a`)
  - `_get_current_price`: stale cache fallback when REST also fails
  - `_check_entries`: no watchlist, score/distance/stop-distance filters, success
  - `_execute_entry`: shares=0, can_enter fails, order fails, order succeeds
  - `_execute_exit`: no-position guard, pending-sell guard, success path
  - `_check_exit_async`: exit triggered, hold, no position
  - `_process_pending_orders`: buy fill entry-price update, sell fill log
  - `_print_status`: unrealized PnL from WebSocket cache and Alpaca fallback
- **Fixed `test_execute_entry_risk_validation_fails`** — was asserting 3 positions hit sector limit, but `max_sector_positions` YAML value was raised to 10; now mocks `can_enter_position` directly

## [0.3.8] - 2026-04-10

### Tests
- **paper_exits.py coverage: 43% → 92%** (`89dd81e`)
  - 34 new tests across 6 classes
  - `_get_cached_data`: cache miss/hit/TTL expiry, insufficient history, yfinance exception
  - `_get_ema_values`: real EMA lookup, None when no data
  - `evaluate_exit` edge paths: zero `initial_risk` fallback, no `risk_config` default thresholds
  - `get_position_summary`: PnL, R multiple, pct_to_stop, all keys present
  - `calculate_initial_stop`: percent method, ATR/atr_or_support, min/max bound enforcement, fallback paths
  - `calculate_target_price`: 2R default, explicit override, zero/inverted risk fallback, config `min_r_multiple`
  - `calculate_position_size`: dual-constraint path, fallback arithmetic, explicit risk override, zero risk, metadata storage

## [0.3.7] - 2026-04-10

### Fixed
- **Exit engine: R multiple corrupted after breakeven ratchet** (`f8fbb09`)
  - `evaluate_exit` used `position.stop_price` as both current stop and initial-stop denominator
  - After breakeven ratchet, stop moves to entry price → risk/share = 0 → r_multiple = 0.0 forever
  - Silently prevented EMA10/EMA21 trailing from ever activating after +1R
  - Fix: use `position.initial_risk` (set at entry, never mutated) so R multiple stays correct through all ratchets

### Tests
- **Comprehensive exit engine test suite** (`f8fbb09`)
  - 28 tests across 9 classes covering all exit rules and edge cases
  - Hard stop (at/below/above boundary), breakeven ratchet, EMA10 trailing (+1.5R), EMA21 trailing (+3R)
  - EMA fallback chain: EMA21=None falls back to EMA10, both None falls back to breakeven
  - Stop ratchet invariant: stop never moves down across sequential price advances or retreats
  - Custom `RiskConfig` thresholds (inline, no YAML dependency)
  - Lifecycle regression test: proves the initial_stop bug is fixed

## [0.3.6] - 2026-04-10

### Fixed
- **SPY market condition showing stale/incorrect value** (`bda9be6`)
  - Mixed data sources (Alpaca last trade + yfinance prev close) produced yesterday's move pre-market instead of today's
  - Now uses yfinance exclusively: `iloc[-1] / iloc[-2]` — consistent regardless of market hours

## [0.3.5] - 2026-04-10

### Changed
- **entry_signals.py now uses RiskConfigManager** (`7e0cb2a`)
  - Entry thresholds (`min_entry_score`, `max_dist_to_pivot_pct`, `max_spy_decline_pct`) now loaded from `config/risk_config.yaml` instead of hardcoded constants
  - Stays in sync with paper engine — changing YAML affects both tools
  - Added `--risk-profile` flag: `python3 entry_signals.py --risk-profile aggressive`

## [0.3.4] - 2026-04-10

### Fixed
- **Trade log validation blocking high-priced stocks** (`71c5324`)
  - `MAX_ENTRY_PRICE` was hardcoded to $500, silently skipping log entries for stocks like CAT ($788), MU ($413+), AVGO ($357+)
  - Order was still submitted to Alpaca but trade went unrecorded locally
  - Raised ceiling to $5000 (overridable via `PAPER_MAX_ENTRY_PRICE` env var)

## [0.3.3] - 2026-04-10

### Fixed
- **Position sizing rounded_to_zero for high-priced stocks** (`87ba100`)
  - Round-to-nearest-10 logic was zeroing out valid positions when share count < 10
  - Affects high-priced stocks (e.g. CAT at $786 → 9 shares → rounded to 0)
  - Fix: rounding now only applies when shares >= 10

## [0.3.2] - 2026-04-10

### Fixed
- **Entry Signals price lookup** (`3c563b0`)
  - `_get_current_price` was calling `AlpacaClient.get_latest_quote()` which never existed, causing `AttributeError` on every ticker scan
  - Replaced with `get_latest_price()` which returns a float directly and already has a yfinance fallback built in

## [0.3.1] - 2026-04-09

### Added
- **Test Data Isolation Solution (Three-Phase)** (`d52f834`)
  - **Phase 1: Data Cleanup Utility** (`scripts/clean_test_trades.py`)
    - Removes test/development entries from production `paper_trades.jsonl`
    - Detects by: unrealistic prices (>$400), excessive shares (>500), known test patterns
    - Automatic duplicate detection and removal
    - Creates timestamped backups before cleaning
    - Dry-run mode for safe preview
  - **Phase 2: Test Metadata Tagging**
    - Trade entries now include `_meta` dict with `test_mode` flag
    - Tests automatically tagged via `PAPER_TRADING_TEST_MODE` env var
    - Report command filters test entries by default
    - Added `--include-test-data` flag to show test data when needed
  - **Phase 3: Data Integrity Validation**
    - Real-time validation before trade logging (price, shares, P&L limits)
    - Configurable via environment variables: `PAPER_MAX_ENTRY_PRICE`, `PAPER_MAX_SHARES`, etc.
    - Validation failures logged with metadata for debugging
  - **Result:** Cleaned 90 test entries, reduced fake P&L from -$2.2M to real -$363
  - **Update (282f765):** Additional cleanup for STOCK0/1/2 patterns and history/today command filtering
    - Removed 12 more test entries (STOCK patterns)
    - History now shows 12 real trades vs 50 with garbage data

### Added
- **Flexible Risk Configuration System** (`config/risk_config.yaml`)
  - Named profiles: default, conservative, aggressive, tight_stops
  - Dual-constraint position sizing (account risk + position cap)
  - Min/max stop distance validation with automatic rejection
  - Environment variable overrides: `RISK_ACCOUNT_RISK_PCT`, `RISK_POSITION_MAX_PCT`
  - New CLI flags: `--risk-profile` and `--risk-summary` for paper engine
  - New module `traderlib/risk_config.py` with full configuration management
- Packaged traderlib as proper Python package (`setup.py` for editable installs)
- Pre-commit hooks (black, flake8, isort) for code quality
- Dynamic VIX calculation in premarket report (uses current VIX value)

### Changed
- Updated risk management: max position size capped at 5% of equity
- Reject trades with stop distance > 10% (configurable)

### Fixed
- Traderlib import errors (`calculate_relative_strength`)
- Test assertions for edge cases
- WebSocket error handling with exponential backoff
- ATR calculation consistency (now uses Alpaca data for stops)
- Entry price sync from Alpaca for accurate P&L
- Day P&L display persistence
- **Shutdown message** - Suppressed misleading "Using REST polling" message during Ctrl+C shutdown

### Infrastructure
- **requirements.txt** - All dependencies with pinned versions for reproducible installs
- **CI/CD** - GitHub Actions now uses `requirements.txt` instead of manual pip installs
- **python-dotenv** - For `.env` file support across all scripts

### Developer Experience
- **Unified credential management** - All API keys load from `.env` file using `python-dotenv`
- **One-command setup** - Added `setup.sh` script for directory creation and dependency installation
- **Makefile commands** - `make setup`, `make test`, `make clean`, `make lint`, `make format`

### Added (Post-Commit)
- **Structured Exception Logging** (`scripts/trading_exceptions.py`)
  - Severity levels: CRITICAL, ERROR, WARNING, INFO with appropriate tracebacks
  - Daily log rotation to `data/logs/trading_exceptions.log` (30 days retention)
  - Both console and file output for observability
  - Metrics tracking for monitoring/alerting
  - Decorator pattern: `@critical()`, `@error()`, `@warning()`, `@info()`
  - Replaced 19 silent `except Exception: pass` handlers across 8 files

### Fixed (Post-Commit)
- **GitHub Actions workflow** - Fixed 2 test failures causing CI/CD pipeline errors
  - Removed broken `ENTRY_THRESHOLD` import from `paper_engine_alpaca`
  - Fixed test isolation by patching `PaperState._load_state` to prevent disk state leaks
  - Fixed MagicMock format error in `state.get_stats()` mocking
  - Fixed Mock order object to include `ticker` attribute for `has_pending_order()` check
  - All 110 tests now passing

## [0.2.2] - 2026-04-09
### Fixed
- **Stock Split Adjustment (CRITICAL):**
    - Added `adjustment=Adjustment.ALL` to Alpaca `StockBarsRequest` to fetch split-adjusted prices
    - **Root Cause:** POWL had a 3:1 stock split on April 8, 2025. Alpaca returned unadjusted prices (~$180), while yfinance returned split-adjusted prices (~$60)
    - **Impact:** Entry scores were completely wrong - POWL showed score 15 (Tier 3) instead of 90 (Tier 1), causing false rejections
    - **Before Fix:** Stage2=3/7, 6M return=-27.6%, RS=-28.4%, Score=15
    - **After Fix:** Stage2=7/7, 6M return=+118.1%, RS=+116.7%, Score=90
    - Affects `scripts/alpaca_client.py` - all historical data now matches yfinance

## [0.2.1] - 2026-04-08
### Added
- **Portfolio CLI (`paper_portfolio.py`):**
    - Added Unrealized P&L display in `status` command showing current gains/losses from open positions

### Fixed
- **Portfolio CLI (`paper_portfolio.py`):**
    - Fixed entry price display to read from Alpaca format (`avg_entry_price`)
    - Fixed hard stop display to lookup `Stop_Level` from watchlist when not in position data

## [0.2.0] - 2026-04-08
### Added
- **Comprehensive Test Suite:**
    - `tests/test_alpaca_client_extended.py`: 34 tests covering config loading, rate limiting, fallbacks, orders, WebSocket
    - `tests/test_paper_engine_extended.py`: 28 tests for market hours, SPY cache, entry filters, execution paths
    - `tests/test_integration_paper_engine.py`: Phase 1 integration tests for critical paths
    - `tests/test_chaos.py`: Phase 3 chaos tests for failure scenarios
    - `tests/test_paper_state_recovery.py`: Phase 3 recovery tests for edge cases
    - `tests/conftest.py`: Automatic test isolation via environment variable
- **Test Isolation:** `PAPER_TRADING_DATA_DIR` environment variable for isolated test data
- **Coverage Reporting:** pytest-cov integration with HTML/XML output
- **CI/CD Pipeline:** GitHub Actions workflow (`.github/workflows/test.yml`) for automated testing on Python 3.11/3.12/3.13 with coverage enforcement

### Fixed
- **Data Pollution:** Tests no longer write to production `data/` folder (automatic temp directory isolation)

### Changed
- `paper_state.py`, `paper_engine_alpaca.py`, `paper_portfolio.py`, `order_manager.py`: Now support `PAPER_TRADING_DATA_DIR` env var

## [0.1.0] - 2026-04-08
### Added
- `scripts/entry_signals.py`: New scanner for identifying entry opportunities.
- SPY Relative Strength (RS) calculation integrated into the paper trading engine.
- Configurable `historical_days` for Alpaca data fetching to optimize between speed and accuracy.

### Fixed
- **Trading Engine:**
    - Fixed sector lookup during Alpaca position synchronization.
    - Resolved entry score discrepancy between `analyze_watchlist` and `paper_engine`.
    - Fixed DataFrame boolean evaluation errors in the engine loop.
    - Corrected the entry score proximity bug to use symmetric $\pm 1\%$ filtering.
    - Fixed WebSocket restart logic and added comprehensive debug logging.
    - Fixed countdown timer overwriting logs - Removed `\r` carriage return that was erasing entry check output
    - Fixed empty orders file error - Order manager now handles empty/corrupted JSON gracefully
    - Fixed historical data requirements - Lowered minimum bars from 50 to 30 and increased request from 60 to 90 days
- **Portfolio CLI (`paper_portfolio.py`):**
    - Fixed `NameError` in `live` command caused by missing `pos_dict` initialization.
    - Fixed incorrect entry price mapping (`avg_entry_price` vs `entry_price`) that caused `+inf%` P&L.
    - Added sector lookup from `watchlist.csv` for positions lacking sector data.
- **Data & API:**
    - Fixed Alpaca historical data feed specification.
    - Resolved "insufficient historical data" errors by increasing default fetch days.
    - Fixed sector reading logic from the watchlist CSV.

### Infrastructure
- **Test data isolation** - `PAPER_TRADING_DATA_DIR` environment variable prevents tests from polluting production data
- **Extended test coverage** - 62 new tests for `alpaca_client.py` (50% coverage) and `paper_engine_alpaca.py` (54% coverage)

### Changed
- Updated README with detailed documentation on the watchlist-to-order decision flow and Alpaca engine logic.
- Refined debug output and consolidated the engine countdown to a single line for better readability.
- Updated proximity scoring documentation to match symmetric implementation.

### Documented
- Entry score discrepancies and historical data requirements.
