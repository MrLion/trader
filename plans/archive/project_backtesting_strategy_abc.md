---
name: Backtesting Module Strategy ABC
description: Strategy abstraction enables arbitrary pluggable strategies; paper engine refactoring deferred to v2
type: project
originSessionId: 2a4870a1-6b70-4e4b-8baa-1e231eee19d1
---
The backtesting module uses a Strategy ABC (abstract base class) as its pluggable interface. Any strategy implements `evaluate_entries()` and `evaluate_exits()` — the engine is agnostic to strategy internals.

**Why this matters:** Stage2MomentumStrategy is the first implementation. Short, mean-reversion, and other strategies plug in without engine changes.

**Paper engine compatibility:** `scripts/paper_engine_alpaca.py` does NOT implement Strategy ABC. Entry/exit logic is inline in `_analyze_ticker()` and `_check_exits()`. Both systems share the same pure functions (calculate_stage2_score, get_entry_score, ExitEngine.evaluate_exit, calculate_position_size_with_constraints) but orchestration is duplicated. Refactoring the paper engine to use Strategy ABC is a v2 task — the paper engine is production code running daily and refactoring it risks breaking live trading.

**v2 target architecture:** Strategy ABC at the top, with PaperExecution and BacktestExecution as swappable execution layers. The pure functions in stage2_utils, paper_exits, and risk_config are the shared foundation.

**Why:** User confirmed this is the correct design — Strategy ABC as an arbitrary pluggable interface, not coupled to any specific strategy.