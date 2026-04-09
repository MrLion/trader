# Release Notes

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
