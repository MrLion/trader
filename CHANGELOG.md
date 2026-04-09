# Changelog

All notable changes to this project will be documented in this file.

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
- **Portfolio CLI (`paper_portfolio.py`):**
    - Fixed `NameError` in `live` command caused by missing `pos_dict` initialization.
    - Fixed incorrect entry price mapping (`avg_entry_price` vs `entry_price`) that caused `+inf%` P&L.
    - Added sector lookup from `watchlist.csv` for positions lacking sector data.
- **Data & API:**
    - Fixed Alpaca historical data feed specification.
    - Resolved "insufficient historical data" errors by increasing default fetch days.
    - Fixed sector reading logic from the watchlist CSV.

### Changed
- Updated README with detailed documentation on the watchlist-to-order decision flow and Alpaca engine logic.
- Refined debug output and consolidated the engine countdown to a single line for better readability.
- Updated proximity scoring documentation to match symmetric implementation.

### Documented
- Entry score discrepancies and historical data requirements.

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
