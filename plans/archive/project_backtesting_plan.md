---
name: Backtesting Module Plan
description: Comprehensive plan for building a backtesting module using Alpaca historical data, strategy abstraction, data isolation, and multi-account support
type: project
---

A detailed implementation plan has been created and saved at `/Users/mintmrlion/.claude/plans/bubbly-sprouting-cocoa.md`.

**Why:** The trading system has production-grade paper trading, Stage 2 scoring, exit logic, and risk management but no way to test strategies against historical data.

**How to apply:** When the user returns to implement the backtesting module, reference the plan file. Key decisions:
- New subpackage `traderlib/backtest/` with 6 modules (data_provider, strategy, state, engine, report, account)
- CLI at `scripts/backtest.py`
- Zero modifications to existing code — reuses ExitEngine.evaluate_exit(historical_data=), Position dataclass, stage2_utils pure functions, RiskConfig
- Data isolation: each run in `data/backtests/{run_name}/`, cache in `data/backtest_cache/`
- Multi-account via env var prefixes + ProcessPoolExecutor
- 8 implementation phases starting with data layer
