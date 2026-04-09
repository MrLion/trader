# Release Notes

## v0.3.1 (Flexible Risk Configuration)
**Released:** 2026-04-09

### Summary
This release introduces a flexible risk configuration system that allows traders to customize risk parameters via YAML profiles. The system now enforces dual constraints: account risk per trade (default 0.75%) AND maximum position size (default 5%), preventing oversized positions even with tight stops.

### Key Features
- **Risk Profiles:** Choose from `default`, `conservative`, `aggressive`, or `tight_stops` profiles via `--risk-profile` flag
- **Dual Constraint Sizing:** Position sizing respects both account risk % and max position % caps
- **Stop Distance Validation:** Automatic rejection of trades with stops wider than configured limits (default 10% max)
- **Environment Overrides:** Runtime customization via `RISK_ACCOUNT_RISK_PCT`, `RISK_POSITION_MAX_PCT` env vars
- **Dynamic VIX:** Premarket report now uses current VIX value for threshold calculations

### Fixed in this Version
- WebSocket error handling with exponential backoff
- ATR calculation consistency using Alpaca data
- Entry price sync from Alpaca for accurate P&L tracking
- Traderlib import errors and packaging improvements
- GitHub Actions CI/CD test failures (110 tests passing)

### Infrastructure & Observability
- **Structured Exception Logging:** Centralized error handling with severity levels (CRITICAL/ERROR/WARNING/INFO)
  - Logs to both console and `data/logs/trading_exceptions.log`
  - Daily rotation with 30-day retention
  - Metrics tracking for monitoring
- **Silent Exception Fix:** Replaced 19 silent `except Exception: pass` handlers with proper logging across 8 files

### How to Use
```bash
# View risk configuration
python3 scripts/paper_engine_alpaca.py --risk-summary

# Run with conservative profile
python3 scripts/paper_engine_alpaca.py --risk-profile conservative

# Run with tight stops (rejects wide stops)
python3 scripts/paper_engine_alpaca.py --risk-profile tight_stops
```

---

## v0.1.0-stable (Alpaca Integration)
**Released:** 2026-04-08

### Summary
This release marks the stabilization of the Alpaca Paper Trading integration. The system can now autonomously scan a watchlist, calculate Stage 2 scores with Relative Strength, and execute market orders on Alpaca Paper accounts with built-in rate limiting and circuit breakers.

### Key Features
- **Automated Paper Trading:** Full loop from watchlist analysis $\rightarrow$ signal detection $\rightarrow$ order execution.
- **Resilient Data Layer:** Hybrid Alpaca/yfinance data fetching with automatic failover.
- **Risk Management:** Integrated position sizing based on account equity and stop-loss distance.
- **Real-time Monitoring:** WebSocket price streaming for low-latency exit signals.

### Fixed in this Version
- Stabilized the entry signal logic (Symmetric $\pm 1\%$ pivot proximity).
- Fixed critical API data feed errors and historical data gaps.
- Improved engine stability and error recovery during WebSocket disconnects.

### How to Use
1. Run `python3 scripts/setup_alpaca.py` to configure keys.
2. Run `python3 scripts/validate_alpaca.py` to verify connectivity.
3. Start the engine with `python3 scripts/paper_engine_alpaca.py`.
