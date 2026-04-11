# Backtesting Engine Feasibility Analysis

## Executive Summary

**Verdict: HIGHLY FEASIBLE and HIGHLY VALUABLE**

Building a backtesting engine is both technically achievable and strategically important for this trading system. The existing architecture provides a solid foundation.

---

## Current Foundation Assessment

### ✅ Existing Assets That Enable Backtesting

| Component | Relevance | Notes |
|-----------|-----------|-------|
| **AlpacaClient.get_historical_bars()** | Data source | Already fetches historical data with rate limiting |
| **ExitEngine** | Exit logic | All exit rules (stops, trailing, targets) are modular |
| **RiskConfigManager** | Configuration | Risk parameters already configurable via YAML |
| **entry_signals.py** | Entry logic | Entry scoring system already implemented |
| **paper_state.py** | Position tracking | Can be adapted for historical simulation |
| **watchlist.csv** | Universe definition | Ticker list with pivot prices, stops, sectors |

### ⚠️ Gaps That Need Building

| Component | Effort | Complexity |
|-----------|--------|------------|
| **Time-series simulation loop** | Medium | Walk through historical bars day-by-day |
| **Market regime simulation** | Low | Apply SPY/VIX filters to each date |
| **Sector/position tracking** | Low | Reuse existing position tracking logic |
| **Trade log replay** | Low | Adapt existing paper_trades.jsonl format |
| **Performance metrics** | Medium | Sharpe, max drawdown, win rate, etc. |
| **Visualization** | Medium | Equity curves, trade distribution charts |

---

## Technical Architecture

### Proposed Design

```
scripts/backtest_engine.py
├── BacktestEngine
│   ├── load_watchlist()          # From watchlist.csv
│   ├── fetch_historical_data()   # AlpacaClient.get_historical_bars()
│   ├── run_simulation()          # Day-by-day walk
│   │   ├── evaluate_signals()    # Entry criteria
│   │   ├── check_exits()         # ExitEngine.evaluate_exit()
│   │   └── update_positions()    # P&L tracking
│   └── generate_report()         # Performance metrics
│
├── BacktestPosition              # Simulated position
│   ├── entry_date, entry_price
│   ├── shares, stop_price
│   ├── target_price
│   └── trail logic (from ExitEngine)
│
└── PerformanceAnalyzer
    ├── calculate_metrics()
    ├── compare_benchmarks()
    └── export_results()
```

### Data Flow

```
1. CONFIGURATION
   └── Load risk_config.yaml
   └── Parse watchlist.csv (tickers + pivot prices)
   └── Set backtest date range

2. DATA FETCHING
   └── For each ticker in watchlist:
       └── AlpacaClient.get_historical_bars(start, end)
       └── Store OHLCV in memory (DataFrame)

3. SIMULATION LOOP
   └── For each trading day in range:
       ├── Market Open
       │   └── Update existing positions (gaps, overnight)
       │   └── Calculate trailing stops
       │
       ├── Market Hours
       │   └── Check entry signals (from entry_signals logic)
       │   └── If signal + capital available:
       │       └── Calculate position size (risk_config)
       │       └── Enter position at Open price
       │   └── For each open position:
       │       └── Check if Low <= stop_price (STOP_HIT)
       │       └── Check if High >= target_price (TARGET_HIT)
       │       └── Update trailing stops based on High
       │
       └── Market Close
           └── Mark remaining positions to Close
           └── Log daily stats

4. RESULTS
   └── Calculate metrics (Sharpe, drawdown, etc.)
   └── Generate equity curve
   └── Export trade log
   └── Compare to buy-and-hold benchmark
```

---

## Feasibility Assessment

### ✅ Strengths (Why This Will Work)

1. **Modular Exit Logic**
   - `ExitEngine.evaluate_exit()` is already position-data-driven
   - Can pass historical prices instead of real-time
   - No WebSocket dependency

2. **Entry Scoring Exists**
   - `entry_signals.py` has all the logic
   - Just needs historical data instead of current

3. **Alpaca Historical Data**
   - Free tier: 200 requests/minute
   - Can fetch years of data for watchlist
   - Pagination handled in existing client

4. **Risk Configuration**
   - All parameters already in `risk_config.yaml`
   - Easy to test different profiles

5. **Clean Position Model**
   - `paper_state.py` tracks positions simply
   - Easy to replicate for historical simulation

### ⚠️ Challenges (What Needs Careful Design)

1. **Intraday Execution Price**
   - Backtest uses OHLC bars
   - Real execution is intraday with slippage
   - **Mitigation:** Use realistic assumptions (enter at Open + slippage, exit at stop price)

2. **Market Impact**
   - Real orders move prices (especially illiquid stocks)
   - **Mitigation:** Add liquidity filter (skip stocks with <$1M daily volume)

3. **Look-Ahead Bias**
   - Must ensure decisions only use data available at that time
   - **Mitigation:** Strict date filtering in simulation loop

4. **Correlation of Signals**
   - Multiple entries on same day may not all fill
   - **Mitigation:** Capital allocation queue (first signals get filled)

---

## Implementation Estimates

### Phase 1: MVP (2-3 days)

**Scope:** Basic walk-forward with daily bars

| Task | Hours | Deliverable |
|------|-------|-------------|
| Create BacktestPosition class | 4 | Simulated position with P&L tracking |
| Build simulation loop | 8 | Day-by-day processing |
| Integrate ExitEngine | 4 | Reuse existing exit logic |
| Basic entry signals | 4 | Adapt entry_signals.py |
| CSV export | 2 | Trade log output |

**Output:** 
```bash
python3 scripts/backtest_engine.py --start 2025-01-01 --end 2025-12-31
# Produces: backtest_results.csv with all simulated trades
```

### Phase 2: Performance Metrics (1-2 days)

| Task | Hours | Deliverable |
|------|-------|-------------|
| Calculate metrics | 6 | Sharpe, Sortino, max drawdown, win rate |
| Equity curve | 4 | Time-series plot |
| Trade distribution | 2 | Histogram of R-multiples |

**Output:**
```bash
python3 scripts/backtest_analyzer.py backtest_results.csv
# Produces: metrics.json + equity_curve.png
```

### Phase 3: Advanced Features (3-5 days)

| Task | Hours | Deliverable |
|------|-------|-------------|
| Walk-forward optimization | 8 | Test parameter ranges |
| Monte Carlo simulation | 6 | Randomize trade order |
| Benchmark comparison | 4 | vs SPY buy-and-hold |
| Parameter sensitivity | 4 | Which settings matter most |
| Report generation | 4 | HTML report with charts |

**Output:**
```bash
python3 scripts/backtest_engine.py --optimize --monte-carlo 1000
# Produces: optimized_params.yaml + detailed_report.html
```

### Phase 4: Intraday Simulation (5-7 days)

| Task | Hours | Deliverable |
|------|-------|-------------|
| Hourly bar support | 8 | More realistic entries/exits |
| Volume profile simulation | 6 | Time-of-day entry rules |
| Slippage modeling | 4 | Entry at VWAP vs Open |
| Partial fill simulation | 4 | More realistic sizing |

**Total: 11-17 days for full-featured backtester**

---

## Viability Analysis

### Business Value: HIGH

**Before Backtester:**
- Risk settings based on gut feel
- No way to validate strategy
- Live trading = expensive experimentation

**After Backtester:**
- Validate risk_config settings before live trading
- Optimize entry thresholds (60 vs 70 vs 80)
- Test trailing stop variations (EMA10 vs EMA8)
- Compare risk profiles (conservative vs aggressive)
- Build confidence in strategy

### Technical Risk: LOW

- Reuses existing, tested components
- No new external dependencies
- Can start simple and add complexity
- Easy to validate (compare to paper trades)

### Maintenance Burden: LOW

- Shares code with production engine
- Updates to ExitEngine automatically apply
- Same risk_config.yaml format
- Minimal divergence

---

## Recommended Implementation Plan

### Week 1: MVP
- Day 1: BacktestPosition class + data fetching
- Day 2: Simulation loop + entry/exit integration
- Day 3: Testing + bug fixes

### Week 2: Metrics & Visualization
- Day 1-2: Performance calculations
- Day 3: Chart generation
- Day 4-5: Report formatting

### Week 3: Optimization & Polish
- Day 1-2: Walk-forward optimization
- Day 3-4: Monte Carlo simulation
- Day 5: Documentation + examples

---

## Comparison to Alternatives

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **Build Custom** | Matches exact strategy, integrates with existing code | Time investment | ✅ **RECOMMENDED** |
| **Backtrader** | Feature-rich, community support | Learning curve, different paradigm | Consider if time-constrained |
| **Zipline** | Production-tested, Quantopian heritage | Complex setup, less active | Not recommended |
| **VectorBT** | Fast, modern, Python-native | Less intuitive API | Good alternative |

**Decision:** Custom build is best because:
1. Existing ExitEngine is already the core logic
2. Watchlist/risk_config integration is unique
3. Faster than learning new framework
4. Easier to maintain

---

## Key Design Decisions

### 1. Daily vs Hourly Bars

**Recommendation:** Start with daily, add hourly later

- Daily sufficient for swing trading (hold days to weeks)
- Hourly adds complexity (more data, intraday gaps)
- Can validate daily first, then enhance

### 2. Entry Price Assumptions

**Recommendation:** Enter at next day's Open

- Realistic: Can't enter at yesterday's close
- Accounts for overnight gaps
- Simple to implement

### 3. Exit Logic

**Recommendation:** Check stops against daily Low/High

- If Low <= stop: Exit at stop price (intraday hit)
- If High >= target: Exit at target price
- Otherwise: Hold

### 4. Capital Allocation

**Recommendation:** Sequential allocation by signal strength

- Rank signals by entry score
- Allocate capital to best signals first
- Prevents over-allocation on correlated setups

---

## Success Metrics

**MVP Complete When:**
- [ ] Can run backtest on 2024 watchlist
- [ ] Produces trade log matching paper_trades format
- [ ] Calculates basic metrics (win rate, avg R)
- [ ] Matches actual paper trade results (for validation)

**Production Ready When:**
- [ ] Supports multiple risk profiles
- [ ] Generates equity curve charts
- [ ] Includes benchmark comparison
- [ ] Has walk-forward optimization
- [ ] Documentation complete

---

## Conclusion

**Building a backtesting engine is:**
- ✅ Technically feasible (reuse existing components)
- ✅ Strategically valuable (validate before live trading)
- ✅ Time-efficient (2-3 weeks for MVP)
- ✅ Maintainable (shares code with production)

**Next Step:** Approve MVP scope and begin implementation with BacktestPosition class.
