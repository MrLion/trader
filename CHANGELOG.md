# Changelog

All notable changes to this project will be documented in this file.

## [0.6.1.5] — 2026-04-18

### Changed
- **Config-driven profiles** — `scraper_config.yaml` is now the single source of truth for all profile parameters; no hardcoded values remain in Python
  - Profile YAML blocks now include screener structural filter defaults alongside universe pre-filter thresholds: `stack_short`, `stack_long`, `rs_near_high_pct`, `min_price_vs_10ma`, `min_share_volume`, `min_stage2_score`, `min_convergence_score`
  - `large_cap`: `stack_long=true`, `rs_near_high_pct=5`, `min_price_vs_10ma=6`, `min_share_volume=1M`, `min_stage2_score=5`
  - `high_octane`: `stack_long=false`, `rs_near_high_pct=12`, `min_price_vs_10ma=4`, `min_share_volume=400K`, `min_stage2_score=4`
  - `--profile` now accepts any string — add custom profiles as YAML blocks in `scraper_config.yaml` without touching Python
  - CLI flags override config values per-run (e.g. `--rs-near-high 8` overrides the profile's `rs_near_high_pct`)
  - `UniverseBuilder.get_profile_config()` new method — returns full profile dict for a given profile name

## [0.6.1.4] — 2026-04-18

### Changed
- **Trend Screener UX overhaul** — Three buckets of improvements across prefiltering, scanning, and console output

#### Prefiltering
- `large_cap.min_price` raised from $10 → $30 in `config/scraper_config.yaml` to align universe pre-filter with screener floor (was wasting API calls on tickers that failed immediately)
- `universe_builder.py`: added `marginable=True` gate for high-octane profile — blocks non-institutional penny stocks ($2–5 range) while allowing fallen large-caps (e.g. EBAY) which remain marginable
- `universe_builder._compute_dollar_volumes()`: chunked at 500 tickers per `StockBarsRequest` (was unbounded, risked URL-length failures on 6,000+ symbol universes)

#### Scanning
- Per-ticker progress with live pass count (`Scanning AAPL — 12 passed`) instead of batch-level granularity
- Filter breakdown printed after every scan — shows rejections by stage (price, MA stack short/long, RS, liquidity, convergence, passed)
- Profile-aware structural filter defaults: `stack_long` off by default for high-octane (50D>150D>200D too strict for volatile names), `rs_near_high` threshold relaxed to 12% for high-octane vs 5% for large-cap
- Note added after universe load: "structural filters will further reduce this list"

#### Console Output
- Results table replaced with Rich table — color-coded by grade (green=A, yellow=B, dim=C)
- Column renames: `S2`→`Stage2`, `Conv`→`Score`, `Clust`→`MAs`, `MA_Risk`→`MA Stop%`, `Prox%`→`To Pivot`, `Vol`→`Vol Ratio`
- Run context header above results: profile, universe size, active filters, rank-by
- Score distribution shown when no convergence threshold applied (range, mean)
- `Entry` column hidden in default `--entry-mode any` (always READY, was redundant)
- `--no-hide-grade-c` flag to show Grade C results (hidden by default in discovery mode)

#### Backtest Compatibility
- CSV export now uses `Ticker` (capital T) column — matches `backtest.py --watchlist` primary expectation
- New `--export-watchlist <path>` flag: writes single-column `Ticker` CSV directly usable as `python3 scripts/backtest.py --watchlist <path>`

## [0.6.1.3] — 2026-04-17

### Fixed
- **entry_signals.py --ticker silent exit** — `analyze_single()` exited without output when API returned DataFrame with <200 rows and `print_analysis()` call referenced non-existent method. Fixed by lowering threshold to >=150 rows and removing the phantom `print_analysis()` call that never existed.
- **README.md streamlined** — Reduced from 520 to 130 lines (75% reduction) for better scannability
  - Removed detailed script examples — link to `docs/` instead of duplicating content
  - Removed trading framework details — link to `METHODOLOGY.md` and `RISK_GUIDE.md`
  - Removed configuration tables — link to `docs/config/configuration-reference.md`
  - Kept essential: Quick Start, navigation tables, FAQ, documentation index
  - New `docs/README.md` documentation hub organized by user type
  - New `docs/reports/README.md` for pre/post-market report usage
  - Benefits: Easier maintenance, single source of truth, faster onboarding

## [0.6.1.2] - 2026-04-17

### Fixed
- **ETF exclusion now handled at universe building stage** — ETFs are filtered using name-pattern detection in `traderlib/universe_builder.py` since Alpaca API doesn't distinguish stocks from ETFs
  - Removed hardcoded ETF ticker list from `scripts/trend_screener.py` (40+ tickers)
  - Added name-pattern detection: `'ETF'`, `'EXCHANGE-TRADED FUND'`, `'TRUST'` + provider keywords, `'FUND'` + provider keywords
  - Funnel metrics now show ETF count excluded (e.g., "Filtered to 11,475 (tradable, exclude OTC, AMEX, ~2,000 ETFs)")
  - Benefits: No manual list maintenance, catches all ETFs not just hardcoded ones

### Changed
- **Trend screener UX improvements** — Replaced 100+ lines of progress spam with single-line Rich progress bar
  - Per-batch ETA display (e.g., "Batches ━━━ 12/12 • ETA: 45s")
  - Batch processing (100 tickers/batch) for stable ETA calculation
  - Elapsed time displayed for universe build and scan phases
  - Fallback to plain text if Rich not available

### Fixed
- **Cache bug: funnel metrics showed 0 on cache hit** — `_load_cached()` now populates `UniverseResult` fields from cached CSV columns
  - `total_assets`, `after_tradable_filter`, `after_price_filter`, `after_dvol_filter` now display correctly
  - Example: "13,552 → 7,297 → 4,637 → 1,147" instead of "0 → 0 → 0 → 0"

## [0.6.1.1] - 2026-04-17

### Changed
- **Rate limiter now configurable via `config/scraper_config.yaml`**
  - Added `rate_limiter` section with `max_requests` and `window_seconds` settings
  - Default bumped from 200/min (free tier) to 10,000/min (paid tier)
  - Both `traderlib/rate_limiter.py` and `traderlib/alpaca_client.py` now load config on init
  - Free tier users: set `max_requests: 200` in config to restore previous behavior

## [0.6.1.0] - 2026-04-17

### Added
- **Trend Screener with MA Convergence Detection** — Complete VCP (Volatility Contraction Pattern) breakout trading system (Phases 0-6)
  - Phase 0: Unified exit action pattern (`ExitActionType` enum, `ExitAction` dataclass, `evaluate_exit_action()`)
  - Phase 1: Unified Strategy ABC with auto-discovery registry (`@register_strategy` decorator, `STRATEGY_REGISTRY`)
  - Phase 2: MA convergence scoring in `stage2_utils.py` (`calculate_convergence_score()`, `calculate_volume_metrics()`)
  - Phase 3: Standalone trend screener (`scripts/trend_screener.py`) with MarketSurge filters
  - Phase 4: VCP pattern detection (`traderlib/vcp_utils.py`) with swing high/low detection
  - Phase 5: VCP breakout strategy plugins (`traderlib/strategies/vcp_breakout.py`) — large-cap and high-octane profiles
  - Phase 6: Backtest integration — `scripts/backtest.py` now supports `--strategy` argument for registered strategies
- **86 new tests** (785 → 871 total)
  - VCP pattern detection: 16 tests (swing points, contractions, progression validation)
  - VCP breakout strategies: 18 tests (large-cap, high-octane, exit management, registry)
  - Composite strategy: 15 tests (union/intersection modes, exit conflict resolution)
  - MA convergence: 20 tests (scoring components, volume metrics, edge cases)
  - Strategy ABC: 17 tests (interface, registry, ExitAction types)

## [0.6.0.4] - 2026-04-16

### Added
- **Auto-restart daemon mode** — `paper_engine_alpaca.py` now runs as a persistent daemon that automatically manages its lifecycle around market hours.
  - Pre-market: Waits for 9:30 AM ET open with countdown display (Ctrl+C to cancel)
  - Market hours: Runs normally, trades execute
  - Market close (4:00 PM): Graceful shutdown, auto-restarts at next 9:30 AM
  - Weekend/holiday: Waits until next trading day automatically
  - Error recovery: On crash, waits 60s and retries (Ctrl+C to stop)
  - One command: `python3 paper_engine_alpaca.py` → runs all week until stopped

## [0.6.0.3] - 2026-04-16

### Fixed
- **WebSocket market-aware lifecycle** — `paper_engine_alpaca.py` now stops the engine entirely when the market is closed, preventing rapid reconnection attempts that caused "connection limit exceeded" errors from Alpaca.
  - Pre-flight check in `main()`: exits immediately with message showing next market open time if market closed
  - Market-close detection in `run()` loop: graceful shutdown when market transitions from open to closed
  - WebSocket guard: only attempts WebSocket connection when `is_market_open()` returns True
  - Benefits: eliminates WebSocket errors when market closed, no unnecessary API calls, cleaner logs, resource efficient

## [0.6.0.2] - 2026-04-16

### Fixed
- **Order submission crash on connectivity loss** — `order_manager.submit_entry()` now catches `TimeoutError` and `ConnectionError` in `_execute_entry()`, printing a warning and returning instead of crashing the engine.

### Added
- **88 new tests for critical trading modules** (712 → 746 passing)
  - Phase 1: Risk management circuit breakers — 15 tests in `tests/test_paper_state_risk_gates.py`
  - Phase 2: Order lifecycle state transitions — 18 tests in `tests/test_order_manager_lifecycle.py`
  - Phase 3: Market hours calendar edges — 29 tests in `tests/test_market_hours_calendar.py`
  - Phase 4: Paper engine fill processing & cooldown — 14 tests in `tests/test_paper_engine_fills.py`
  - Phase 5: Backtest accuracy gates (gap rejection, stop calc, position sizing) — 12 tests in `tests/test_backtest_gap_rejection.py` and `tests/test_backtest_stop_calc.py`

## [0.6.0.1] - 2026-04-16

### Fixed
- **Rate limiter deadlock bug** — Changed `APIHealthMonitor._lock` from `Lock()` to `RLock()` to allow reentrant calls when `get_status()` calls `get_provider()`.
- **Risk config singleton persistence** — Added `reset_risk_config()` function to enable proper test isolation when environment variables change between tests.
- **Test isolation in `test_alpaca_client_extended.py`** — Fixed patch paths to use `traderlib.alpaca_client.CONFIG_FILE` instead of `alpaca_client.CONFIG_FILE`.
- **Test expectation in `test_risk_config.py`** — Updated expected value to match config file default (0.5%).

### Added
- **Comprehensive MA Support Stop unit tests** — 25 tests in `tests/test_ma_support_stop.py` covering edge cases: no MAs below price, cluster boundaries, buffer calculation, NaN handling, price exactly at MA.

## [0.6.0] - 2026-04-16

### Added
- **Comprehensive Test Suite for Critical Modules** — Added 155 new tests across 5 modules with zero previous coverage, bringing estimated test coverage from ~40-50% to ~70-80%.
  - `tests/test_validation.py` (27 tests) — Ticker validation, false positive detection, batch validation, NO_COLOR support.
  - `tests/test_rate_limiter.py` (33 tests) — Rate limiting, exponential backoff, circuit breaker, API health monitoring, thread safety.
  - `tests/test_market_hours.py` (25 tests) — Trading day detection, market hours, holidays, timezone handling.
  - `tests/test_risk_config.py` (40 tests) — Risk configuration loading, profiles, environment overrides, position sizing with triple constraints.
  - `tests/test_order_manager.py` (30 tests) — Order lifecycle, queue processing, Alpaca integration, position sync, callbacks.

## [0.5.6] - 2026-04-16

### Added
- **MA Support Stop — Dual Risk Parameter** — New stop calculation based on clustered moving averages below price. When MAs converge below the price, they form a natural support zone. The system computes both ATR stop and MA support stop, using `max(atr_stop, ma_support_stop)` for tighter risk management.
  - `calculate_ma_support_stop()` in `traderlib/stage2_utils.py` — algorithm collects MAs below price, requires minimum cluster size (default 2) within spread threshold (default 5%), calculates stop at lowest MA minus buffer (default 1%).
  - `MASupportConfig` dataclass in `traderlib/risk_config.py` — configuration with `enabled`, `buffer_pct`, `cluster_spread_pct`, `min_cluster_size`.
  - `ma_support` section in `config/risk_config.yaml` — default enabled with profile overrides for conservative (1.5% buffer), aggressive (0.5% buffer), and tight_stops (3% spread, min 3 MAs).
  - Dual risk display in `entry_signals.py` — shows ATR%, MA%, and Stop type (ATR/MA) columns.
  - Integration in `paper_exits.py`, `backtest/strategy.py`, `paper_engine_alpaca.py`, `premarket_report.py` — MA support stop included in all stop calculations.
  - MA10 added to `get_stage2_details()` return values for MA support calculations.

## [0.5.5] - 2026-04-15

### Changed
- **Backtest terminal report redesigned with Rich** — replaced plain monochrome output with color-coded, two-column layout. Green for positive, red for negative, dim for broken metrics. Includes Sharpe gauge (●●●○○), win rate bar (▉▉▉▉▉▉▉░░░), exit reason breakdown with P&L, top 5 winners/losers, and equity sparkline (▂▃▄▅▆▇█).
- **Commissions removed from backtesting** — `ExecutionConfig` no longer has commission fields. `FillResult` no longer tracks commission. P&L is pure `(exit - entry) * shares` for LONG. Cash accounting simplified. Commissions were noise at this scale and added complexity without insight.
- **SPY benchmark timezone fix** — `engine._get_benchmark()` compared tz-aware Alpaca timestamps against tz-naive pandas Timestamps, causing `TypeError` and silently returning 0.00% SPY return. Now strips timezone with `tz_localize(None)` before date comparison. SPY benchmark and alpha now display correctly.
- **Graceful Ctrl+C shutdown** — pressing Ctrl+C during backtest no longer dumps a raw KeyboardInterrupt traceback. During prefetch: prints how many tickers were cached and exits cleanly. During simulation: liquidates open positions, returns a partial `BacktestResult` with `partial=True`, and prints a partial report with a yellow "PARTIAL RUN" warning showing the actual date range covered.

### Added
- `--trades` flag on `scripts/backtest.py` — shows a full trade table (all trades sorted by entry date) with Ticker, Entry/Exit dates, Shares, Entry/Exit prices, P&L, R-multiple, and exit reason. Uses a wider Console (140 cols) to prevent column truncation.
- `print_report_rich()` on `BacktestReporter` — Rich-formatted terminal report with color, panels, tables, and sparkline. Falls back to `print_report()` if Rich import fails.
- **Rich progress bar during backtest** — two-bar display: "Fetching data" shows per-ticker progress during prefetch (with current ticker name), "Simulating" shows per-day progress with current date, open positions, equity, and trade count. Uses `transient=True` so bars disappear after completion, leaving a clean report. Plain-text fallback with `\r` overwrites if Rich is unavailable.
- `BacktestProgress` dataclass and `on_progress`/`progress_interval` callback on `BacktestConfig` — engine emits progress snapshots each iteration, CLI wires them into Rich Progress display. Engine stays decoupled (no Rich imports).
- `on_progress` callback on `AlpacaDataProvider.prefetch()` — emits `(current, total, ticker)` per ticker during data fetching.
- Exit breakdown section in report — groups trades by exit reason (Target Hit, Stop Hit, Liquidation) with count and total P&L for each.
- Gap rejections now shown in the report body (was previously printed separately in `backtest.py`).
- `quiet=True` parameter on `RiskConfigManager` — suppresses "Applying risk profile" print to avoid duplicate output during backtests.
- `watchlist_df` parameter on `Stage2MomentumStrategy` — accepts a DataFrame with `week_start` column for date-aware ticker filtering during backtests. Tickers are filtered to only those active on or before `sim_date`, supporting time-varying watchlists from `mc_historical_watchlists.csv`.
- `partial` flag on `BacktestResult` and `BacktestReport` — marks interrupted runs so the report can show a warning.

### Fixed
- **Backtest data provider: Alpaca BarSet API** — `bars[ticker]` returns a list, not a Bars object with `.df`. Fixed to use `bars.df` (MultiIndex DataFrame) and extract per-ticker data with `.loc[ticker]`. Column names normalized from lowercase (open/high/low/close) to Title Case.
- **Backtest data provider: RateLimiter API** — `wait_if_needed()` doesn't exist on RateLimiter. Fixed to use `can_make_request()`, `get_wait_time()`, and `record_request()`.
- **Backtest engine: prefetch date range too narrow** — engine was passing `start_date` as prefetch start, only getting ~23 days of data. Extended to `start_date - 400 days` to satisfy 252-row min_lookback and provide historical context for indicators (130-day RS, 50-day MA, 14-day ATR).
- **Drawdown showing green ▲ arrow** — `_fmt_pct(invert=True)` logic was wrong. Higher drawdown = worse, now correctly shows ▼ and red for positive drawdown values.
- **Trade table column truncation** — Rich auto-compressed columns to fit terminal width, truncating "Shares" to "Shar..." and hiding R/Reason columns. Fixed by using fixed `width=` columns and a dedicated 140-col Console for the trade table.
- **Ctrl+C traceback during prefetch** — `time.sleep(wait)` in `AlpacaDataProvider.prefetch()` threw raw `KeyboardInterrupt`. Now caught with a clean message showing cached ticker count.

## [0.5.4] - 2026-04-15

### Fixed
- **Backtest sector limits** — backtests were hardcoding `sector='Unknown'` for all tickers, causing sector concentration limits to block entries after only 3 positions (all grouped under 'Unknown'). Now uses yfinance to lookup actual sectors with in-memory and disk caching (`data/ticker_sectors_cache.json`). Sector limits now work correctly with real diversification across sectors.

## [0.5.3] - 2026-04-15

### Changed
- **Backtest data isolation** — backtests now default to `data-only` mode, connecting only to Alpaca's shared data endpoint (`data.alpaca.markets`) and never to any trading sub-account. The `TradingClient` is no longer instantiated during backtests. Same API keys, same account, but the backtest path cannot touch trading. Use `--alpaca-mode paper` to restore the old behavior (not recommended).

### Added
- `data_only` parameter on `AlpacaClient.__init__` — when `True`, skips `TradingClient` creation. Only `StockHistoricalDataClient` is initialized. Backtests use `data_only=True` by default.
- `--alpaca-mode` flag on `scripts/backtest.py` — choices: `data-only` (default), `paper`.
- `get_current_price` and `prefetch` methods added to `DataFrameProvider` protocol — both were called by the engine but not declared in the protocol, making `isinstance` checks unreliable.
- `prefetch` no-op on `DictDataProvider` — in-memory provider doesn't need bulk fetching, returns `None`.
- `tickers_dropped` field on `BacktestResult` — properly wires dropped ticker data from the provider through to the report, replacing dead code that accessed a non-existent `_data_provider` attribute on `BacktestState`.
- **`scripts/mcstock_historical_scraper.py`** — new scraper for MC Stock Charts archive pages. Scrapes weekly watchlists going back 1-2 years for backtesting with time-varying watchlists. Groups daily reports by week (Monday-based), accumulates tickers across Mon-Fri, outputs `data/mc_historical_watchlists.csv` with columns: `week_start`, `ticker`, `list_type`, `first_seen_date`, `scraped_date`. CLI supports date filtering (`--start`, `--end`), week limits (`--weeks N`), and pagination limits (`--max-pages`).

### Fixed
- **MC Stock Charts historical scraper rewrite** — replaced unreliable archive pagination with direct URL generation. Archive pages had variable report counts (4-9) due to responsive layouts, and date termination wasn't working. New approach generates Mon-Fri trading dates directly, constructs URLs using the pattern `/members/pre-market-report-{weekday}-{month}-{day}-{year}-900a-m-est/`, and handles 404s gracefully (market holidays). Removed `--max-pages` CLI arg. Scraping is now deterministic, faster, and handles date ranges correctly.
- **Dead code in `report.py`** — `report.py:188-193` accessed `result.state._data_provider` which was never set on `BacktestState`, so `tickers_dropped` always reported 0. Now reads from `result.tickers_dropped`.
- **Protocol coupling removed** — `engine.py` no longer imports `AlpacaDataProvider` or uses `isinstance()` checks. The engine calls `prefetch()` directly on whatever `DataFrameProvider` it receives.

### Tests
- 13 new tests in `tests/test_data_providers.py`: protocol enforcement (3), DictDataProvider compliance (2), data_only mode (3), tickers_dropped data flow (2), CLI defaults (1), engine with DictDataProvider (2).

## [0.5.2] - 2026-04-15

### Fixed
- **WebSocket reconnection storm** — the Alpaca SDK's internal `_run_forever()` loop retries disconnections with zero delay, causing a rapid `TimeoutError` cascade (4-5 failures in seconds). Added a health watchdog (`_ws_health_watchdog`) that force-stops the stream after 90s without messages, breaking the SDK's infinite loop and allowing the existing exponential backoff to work.
- **Keepalive ping timeout (code 1011)** — increased `ping_interval` from 20s to 30s and `ping_timeout` from 20s to 60s in `StockDataStream` websocket params, making the client 3x more tolerant of slow pong responses from Alpaca's server.
- **Slow shutdown** — pressing Ctrl+C took 5+ seconds and sometimes required multiple presses because the task was cancelled before the stream was stopped. Reversed the shutdown order: stop the stream first (signals the SDK to exit), then cancel the task. Reduced total shutdown timeout from 5s to 3s.
- **Force-exit on second Ctrl+C** — if graceful shutdown is still in progress when the user presses Ctrl+C again, the engine now force-exits immediately via `os._exit(1)`.

## [0.5.1] - 2026-04-15

### Changed
- **MA penalties in entry score** — stocks below key moving averages now receive explicit score deductions: -20 points for below 50 MA, -10 points for below 20 MA. Previously, the 8-point bucket system couldn't distinguish *which* criteria failed, so a stock at 6/8 failing both MAs scored the same 25-point stage2 component as one failing two other criteria. NEE (6/8, below both MAs) drops from 80 (Tier 1) to 50 (Tier 2). NFG (5/8, below both MAs) drops from 75 (Tier 2) to 45 (Tier 2). Stocks passing all MAs are unaffected. Score floor remains 0.

### Added
- `below_50ma` and `below_20ma` boolean params on `get_entry_score()` — all 4 production callers (`entry_signals.py`, `paper_engine_alpaca.py`, `premarket_report.py`, `backtest/strategy.py`) now extract MA flags from `get_stage2_details()` and pass them through.
- `get_stage2_details` exported from `traderlib/__init__.py` for convenient import.
- 10 MA penalty unit tests in `TestMAPenalties` class covering: individual penalties, combined penalties, NEE/NFG scenarios, floor at 0, no double counting, perfect stock unaffected, tier logic.
- 4 Hypothesis property tests for MA penalties: `test_ma_penalty_reduces_score`, `test_penalty_magnitude`, `test_floor_at_zero` (with MA flags), `test_score_bounds` (with MA flags).

## [0.5.0] - 2026-04-14

### Changed
- **Stage 2 scoring upgraded from 7-point to 8-point system** — added "Price > 20 MA" as criterion #1, creating a natural progression from short-term to long-term trend health. The 20 MA is excluded from the MA stacking check (50 > 100 > 200) since it's too volatile and penalizes valid pullback entries. Recalibrated `get_entry_score()` buckets: 7/8=30pts, 6/8=25pts (was 30), 5/8=20pts (was 25), 4/8=15pts (was 20). Tier 2 threshold raised from stage2 >= 4 to stage2 >= 5.
- **NEE/NFG scoring gap fixed** — stocks below 50 MA and 20 MA no longer score equal to stocks with perfect trend alignment. Under 7-point: 6/7 = 85 (Tier 1). Under 8-point: 5/8 = 75 (Tier 2). The key fix is that 6/8 and 7/8 now give different entry scores (25 vs 30), whereas 6/7 and 7/7 previously gave the same 30.
- Display strings updated from `/7` to `/8` across all reports and tools.

### Added
- 42 regression tests for 8-point scoring system covering: 20 MA criterion, `get_stage2_details()` fields, entry score boundary values at every threshold (0-8), tier classification logic, NEE/NFG scenario, `is_stage2_compliant()`, and flat stock with sufficient data. Coverage of `stage2_utils.py`: 72% → 97%.

## [0.4.0.1] - 2026-04-14

### Fixed
- **Cooldown re-entry bug** — engine restart lost all cooldown state because `last_exit_time` and `consecutive_losses` are in-memory dicts. After restart, `_check_cooldown()` returned True for all tickers, allowing immediate re-entry regardless of cooldown config. Now `_rebuild_cooldown_state()` reads the trade log on startup to reconstruct cooldown state from recent EXIT events.
- **Daily reset killed active cooldowns** — `_reset_daily_signals()` cleared both cooldown dicts at midnight, even when a long cooldown (e.g., 4-hour exponential backoff starting late afternoon) was still active. Now only expired entries are removed, so overnight cooldowns persist correctly.

## [0.4.0] - 2026-04-13

### Added
- **Backtesting module** — full simulation engine for validating the Stage 2 momentum strategy against historical data
  - `traderlib/backtest/data_provider.py` — `DataFrameProvider` protocol, `AlpacaDataProvider` (Alpaca data with rate limiting), `DictDataProvider` (synthetic data for tests)
  - `traderlib/backtest/execution.py` — `ExecutionModel` with deterministic slippage (5bps) and commissions ($0.005/share, $1 min)
  - `traderlib/backtest/state.py` — `BacktestState` with sim_date clock (no datetime.now()), side-aware P&L, sector limits, max positions
  - `traderlib/backtest/strategy.py` — `Strategy` ABC, `Stage2MomentumStrategy` (mirrors paper engine entry logic with injected data)
  - `traderlib/backtest/engine.py` — `BacktestEngine` day-by-day simulation with next-bar fill, gap rejection, and SPY benchmark
  - `traderlib/backtest/report.py` — `BacktestReporter` with return/risk metrics, alpha vs SPY, and survivorship bias disclaimer
  - `scripts/backtest.py` — CLI entry point with `--start`, `--end`, `--capital`, `--watchlist`, `--risk-profile`, `--max-positions` options
  - 84 new tests covering data slicing, execution model, state management, strategy, engine, and reporting

### Changed
- **`evaluate_exit()` returns stop updates instead of mutating position** — `ExitSignal` now carries `new_stop` and `new_stop_type` fields; callers apply the update. This eliminates deepcopy requirements and enables clean backtest integration.
- Paper engine updated to apply stop updates from `ExitSignal` return values instead of relying on position mutation.
- **Partial position support when cash is limited** — position sizer now
  accepts `available_cash` as a third constraint alongside account risk and
  position cap. When cash is insufficient for the full position, shares are
  reduced to fit available cash instead of rejecting the trade entirely.
  Cash-limited positions below `min_position_pct` are allowed since the
  smaller size is caused by capital deployment, not a deliberate choice.
  Logged as `reduced_for_available_cash ($X,XXX)`.

### Fixed
- **MC Stock scraper $Vol_M unit bug** — stored raw dollar volume instead of
  millions, causing watchlist population to overflow `Avg_Volume_50d`.
- **Scraper validation thresholds now configurable** — added
  `config/scraper_config.yaml` for min price, market cap, history days, and
  dollar volume filters. Supports `--config` CLI flag for custom config paths
  and `extra_false_positives` list for skipping specific tickers.
- **risk_config.yaml comment** — corrected risk_per_trade_pct comment from
  0.75% to 0.5%.
- **Move batch price pre-fetch before market condition check** — SPY price
  wasn't available on the first cycle because the batch pre-fetch ran after
  the market condition gate. Now SPY is fetched first.
- **Add API rate limit status to engine output** — shows requests/min usage
  percentage and circuit breaker state in the status line.
- **Include SPY in batch price pre-fetch** — market condition check requires
  SPY current price but wasn't included in the batch, causing "Cannot fetch SPY"
  errors when WebSocket had limited coverage
- **Batch quotes API response format** — Alpaca SDK returns `Dict[str, Quote]`
  for batch requests, not an object with `.data` attribute. This caused
  `'dict' object has no attribute 'data'` errors and 5 tickers failing to get prices.
  Now handles both single-symbol (`.data`) and batch (plain dict) response formats.
- **Skip per-ticker REST calls when circuit breaker is open** (prevents API cascade)
- **Log batch quotes API failures** for debugging price fetch issues
- **Log batch pre-fetch summary** showing how many prices were fetched vs unavailable
- Circuit breaker was causing per-ticker REST calls to fail silently, accumulating
  more errors and keeping the breaker open. Now skips per-ticker calls when breaker
  is open, allowing the batch pre-fetch to be the primary price source.
- **Stale price fallback improved for WebSocket-disconnected mode**
  - When WebSocket is disconnected, allow AlpacaClient cache up to 5 minutes (vs 30s normally)
  - Engine cache fallback also extended to 5 minutes for graceful degradation
  - Avoid per-ticker REST calls when batch pre-fetch already failed (prevents circuit breaker cascade)
  - Shows price age in stale cache warnings (e.g. "45s old")
- **Stale price cache mismatch causing "Using stale price from cache (REST failed)"**
  - Eliminated duplicate price cache in paper_engine_alpaca (60s) vs AlpacaClient (30s)
  - Added `get_latest_prices_batch()` to AlpacaClient for bulk price fetching (1-2 API calls instead of 2N)
  - Pre-fetch all watchlist prices before entry scan loop to populate caches proactively
  - Prevents circuit breaker cascade when scanning 27+ tickers simultaneously

## [0.3.19] - 2026-04-12

### Changed
- **Remove yfinance dependency from ExitEngine calculations**
  - Added `historical_data` parameter to `calculate_initial_stop()` for data injection pattern
  - Enables Alpaca-only mode and backtesting without yfinance network calls
  - Added column validation for injected DataFrames (fail-fast on missing columns)
  - Deprecated yfinance fallback with `DeprecationWarning` for reports/tools only
  - Updated tests to use mock data injection instead of yfinance mocking

### Fixed
- **R-multiple drift bug on breakeven ratchet**
  - Fixed `initial_stop_price` not being stored, causing R-multiple to drift to 0 after stop ratcheted up
  - Prevents division by zero when calculating R-multiples after breakeven move
  - Migration path for legacy positions: derives from current stop on first call, then stores for subsequent calls

## [0.3.18] - 2026-04-11

### Fixed
- **Async blocking calls in paper trading engine**
  - Fixed `TypeError: get_latest_price() got unexpected keyword argument 'use_fallback'`
  - Made `_print_status()`, `_process_pending_orders()`, `_check_exits()`, `_check_entries()` async
  - Wrapped blocking Alpaca API calls in `asyncio.to_thread()` to prevent event loop blocking
  - Fixed 30-second countdown not appearing due to blocking HTTP calls
  - Fixed shutdown hang by properly awaiting WebSocket task cancellation
  - Fixed account value calculation to fetch missing prices via REST when not cached
  - Removed health summary display (caused rate limiter deadlock)

## [0.3.17] - 2026-04-11

### Added
- **Re-entry Cooldown Protection (FLY Case Study)**
  - Configurable cooldown periods to prevent immediate re-entry after losses
  - Based on FLY trade analysis where re-entry 2 minutes after loss caused -$769 total loss
  - Configuration in `config/risk_config.yaml` under `cooldown` section:
    - `reentry_cooldown_minutes`: Base cooldown (default: 60 minutes)
    - `min_loss_to_trigger_cooldown_pct`: Loss threshold (default: 0.0 = any loss)
    - `max_cooldown_minutes`: Maximum cooldown cap (default: 240 minutes / 4 hours)
    - `consecutive_loss_multiplier`: Exponential backoff factor (default: 2.0x)
  - Implementation in `scripts/paper_engine_alpaca.py`:
    - `_check_cooldown()`: Validates if enough time has passed since last exit
    - `_record_position_exit()`: Tracks exit time and consecutive loss count
    - Cooldown automatically resets on new trading day
  - Updated `traderlib/risk_config.py` with `CooldownConfig` dataclass
  - Entry blocked with message like: "Cooldown: 45min remaining (2 consecutive losses)"

### Fixed
- **FINDING-007: Weekend/holiday market hours**
  - Integrated `pandas_market_calendars` for accurate market schedule
  - Created `traderlib/market_hours.py` module with:
    - `is_market_open()` - Check if market is currently open
    - `is_trading_day()` - Check if date is a trading day (excludes weekends/holidays)
    - `next_market_open()` - Get next trading session open time
    - `format_market_status()` - Human-readable market status with next open info
  - Updated `paper_engine_alpaca.py`:
    - Added market hours check before entering positions
    - Skips trading on weekends and market holidays
    - Updated status display with detailed market info
    - Falls back to basic weekday check if pandas_market_calendars not available
  - Added `pandas-market-calendars>=4.3.0` to requirements.txt

## [0.3.16] - 2026-04-11

### Added
- **GS-001: Python version check in setup.sh**
  - Added strict Python 3.11+ version check
  - Extracts major/minor version and validates
  - Provides platform-specific upgrade instructions (macOS, Ubuntu, Windows)
  - Suggests pyenv for version management
  - Clear error messages with actionable next steps

- **GS-002: `make doctor` command for config validation**
  - Created `scripts/doctor.py` - comprehensive configuration checker
  - Checks: Python version, dependencies, Alpaca credentials, directories
  - Checks: Watchlist, Telegram (optional), git hooks
  - Provides actionable fixes for each issue
  - Returns exit code 0 if all checks pass, 1 otherwise
  - Added `doctor` target to Makefile
  - Color-coded output (respects NO_COLOR)

- **NO_COLOR: Respect NO_COLOR environment variable**
  - Added `USE_COLOR` flag in `traderlib/validation.py`
  - Created emoji constants: `EMOJI_CHECK`, `EMOJI_CROSS`, `EMOJI_WARN`, `EMOJI_INFO`, etc.
  - When `NO_COLOR` is set, emojis are replaced with ASCII equivalents: `[OK]`, `[ERR]`, `[WARN]`
  - Updated `watchlist_manager.py` to use new constants
  - Follows https://no-color.org/ standard for CLI toolscolor
- **CLI-004: `--dry-run` flags for destructive commands**
  - Added `--dry-run` to `watchlist_manager.py remove <ticker>`
  - Added `--dry-run` to `watchlist_manager.py remove-all`
  - Added `--dry-run` to `paper_portfolio.py close <ticker>`
  - Shows what would be done without executing
  - Helps users preview destructive operations

- **DOC-001: Create `docs/getting-started.md`**
  - Comprehensive quick-start guide for new users
  - Covers: installation, first workflow, daily rhythm, common commands
  - Includes troubleshooting section for common errors
  - Quick reference tables for entry scores, Stage 2 criteria, risk rules
  - Step-by-step setup for automated trading

### Fixed
- **Critical Design Fixes**
  - **Timezone suffix**: Added "ET" (Eastern Time) suffix to timestamp displays in:
    - `paper_portfolio.py`: `format_et_timestamp()` helper, used in `status` command
    - `paper_engine_alpaca.py`: Status header showing current time
  - **Portfolio overlap**: Added `[IN PORTFOLIO]` indicator to `watchlist_manager.py list`
    - Loads portfolio positions and shows "✓ IN PORTFOLIO" column
    - Helps prevent accidental double-positions
  - **Signal age**: Added timestamp and age column to entry signals in `entry_signals.py`
    - Each signal now records timestamp at creation
    - Age displayed as "Xs ago", "Xm ago", or "Xh ago"
    - Helps identify stale signals when re-running scans
  - **Market filter context**: Expanded "Market filter blocking entries" message with:
    - Reason: SPY decline threshold exceeded
    - Reset condition: SPY closes above prior day high
    - Override note: Reference to `--i-know-what-im-doing` flag
  - **Empty watchlist guidance**: Added "HOW TO POPULATE" help text when watchlist is empty
    - Lists 4 ways to populate (from CSV, single add, midday scan, sector scan)
    - Links to docs/getting-started.md for full workflow

- **EH-003: Actionable API key error message**
  - Created `APIKeyError` exception class in `traderlib/trading_exceptions.py`
  - Follows problem+cause+fix+docs pattern for clear user guidance
  - Applied to `AlpacaClient.__init__()` when keys are missing
  - Applied to API calls (401/403 auth errors) with specific guidance
  - Error message includes:
    - **Problem**: API keys not configured
    - **Cause**: Where the system looked (env vars, config file)
    - **Fix**: Three options (env vars, setup script, .env file)
    - **Docs**: Links to runbook and Alpaca dashboard
  - Impact: Users get clear actionable steps instead of generic "keys not found"

- **FINDING-011: Input validation on tickers — Added regex validation**
  - Created `traderlib/validation.py` with `validate_ticker()` and `validate_tickers()` functions
  - Ticker format: `^[A-Z]{1,5}$` (1-5 uppercase letters, US equity standard)
  - Added false positive rejection (common words like "THE", "AND", "BEST")
  - Applied validation to CLI entry points:
    - `watchlist_manager.py`: `add` and `remove` commands
    - `entry_signals.py`: `--ticker` and `--tickers` arguments
    - `paper_portfolio.py`: `close` command
  - Validation occurs at entry point - rejects invalid tickers before API calls
  - Impact: Prevents invalid ticker symbols from reaching trading engine or external APIs

- **FINDING-013: R-multiple drift — Store initial_stop_price as immutable**
  - Added `initial_stop_price` field to Position dataclass (immutable after entry)
  - Updated R-multiple calculation in `ExitEngine.evaluate_exit()` to use `initial_stop_price`
  - Priority order: `initial_stop_price` → `initial_risk` → `current_stop` (last resort)
  - Updated `Position.from_dict()` to migrate legacy positions (derives from stop_price if missing)
  - Updated `PaperState.enter_position()` to set `initial_stop_price` at creation
  - Updated `paper_engine_alpaca.py` Position creation to include `initial_stop_price`
  - Impact: Prevents R-multiple calculation drift when stops ratchet (breakeven/EMA trailing)

- **FINDING-006: Stale price cache poisoning — Added staleness rejection**
  - Added `price_cache_max_age = 30` (30 second staleness threshold) to `AlpacaClient`
  - Modified `get_cached_price()` to check timestamp before returning cached price
  - Prices older than 30 seconds return `None` instead of stale data
  - Added `is_price_fresh()` method to check cache freshness
  - Added `get_cache_staleness()` method to get cache age in seconds
  - Updated `check_health()` to report fresh/stale cache counts and stale tickers
  - Impact: Prevents trading decisions based on stale WebSocket price data

- **FINDING-014: Async/thread safety — Added threading locks**
  - Added `self._lock = threading.Lock()` to `RateLimiter` class
  - Added `self._lock = threading.Lock()` to `APIHealthMonitor` class
  - Protected all mutable state access with `with self._lock:` blocks
  - Methods protected: `can_make_request()`, `record_request()`, `record_error()`, `record_success()`, `get_wait_time()`, `get_status()`
  - Health monitor protected: `mark_success()`, `mark_failure()`, `get_provider()`, `get_status()`
  - Impact: Thread-safe operation under concurrent access from multiple threads

- **FINDING-009: Concurrent file writes — Added atomic write protection**
  - Added `_atomic_write_json()` function to `traderlib/paper_state.py`
  - Added `_atomic_write_json()` function to `traderlib/order_manager.py`
  - Updated `save_state()`, `_save_daily_tracker()`, and `_save_orders()` to use atomic writes
  - Pattern: Write to temp file → atomic rename → replaces target only if write succeeds
  - Prevents data corruption if process crashes during file write
  - Impact: Data integrity guaranteed even on crashes or power failures

- **Fixed failing GitHub Actions test suite**
  - Updated `tests/test_paper_engine.py`: Changed import from removed `paper_engine` to `paper_engine_alpaca`
  - Updated `tests/test_paper_engine_new_coverage.py`: Removed tests for deprecated `paper_engine` module (Groups 1-5), kept `paper_engine_alpaca` tests (Groups 6-12)
  - Deleted `tests/test_paper_engine.py`: File was written for removed `paper_engine` module, tests incompatible with `AlpacaPaperEngine` interface
  - Updated `tests/test_exit_engine.py`: Changed patch path from `scripts.paper_exits.yf.Ticker` to `traderlib.paper_exits.yf.Ticker` (module was moved to traderlib)
  - Impact: CI/CD pipeline now passes, test suite reflects production code

### Changed
- **Documentation updated to reflect Alpaca-only trading architecture**
  - Updated `CLAUDE.md`: Clarified trading uses Alpaca exclusively; reports/tools may use yfinance
  - Updated `README.md`: Changed data source description, updated integrations table
  - Updated `memory/paper-trading-engine-plan.md`: Changed yfinance dependency to Alpaca
  - Updated `docs/runbooks/api_outage.md`: Removed references to yfinance fallback (no longer exists)
  - Updated `docs/runbooks/stuck_position.md`: Replaced yfinance examples with Alpaca API
  - Updated `docs/runbooks/data_quality.md`: Clarified data sources (Alpaca for trading, yfinance for reports)
  - Impact: Documentation accurately reflects single-source trading architecture

### Added
- **Configurable EMA periods, cache TTL, and fallback target in `risk_config.yaml`**
  - `profit_target.ema_periods.short/long`: Configure EMA periods for trailing stops (default: 10/21)
  - `profit_target.fallback_target_pct`: Target % above entry when R calculation fails (default: 10%)
  - `cache.ttl_seconds`: Price data cache TTL in seconds (default: 300 = 5 minutes)
  - Update `traderlib/risk_config.py` dataclasses to load new parameters
  - Update `traderlib/paper_exits.py` to use configured values instead of hardcoded
  - Impact: Users can now customize trailing stop EMA periods, cache duration, and fallback targets

### Changed
- **Trading engine migrated to Alpaca-only (yfinance fallback removed)**
  - Removed `_yfinance_fallback_price()` and `_yfinance_fallback_bars()` from `AlpacaClient`
  - Removed `use_fallback` parameter from `get_latest_price()` and `get_historical_bars()`
  - Trading engine now uses Alpaca API exclusively — no yfinance fallback
  - Updated `scripts/entry_signals.py`: SPY regime check uses Alpaca instead of yfinance
  - Updated `scripts/paper_engine_alpaca.py`: Yesterday's close from Alpaca instead of yfinance
  - Updated `scripts/paper_portfolio.py`: Position prices from Alpaca position/quotes API
  - Impact: Single data source for trading execution, consistent real-time pricing, backtesting support

- **ExitEngine refactored to support data injection**
  - Added optional `historical_data: Optional[pd.DataFrame]` parameter to `evaluate_exit()`
  - Modified `_get_ema_values()` to calculate EMAs from injected data when provided
  - Falls back to yfinance when `historical_data` is None (backward compatible for reports/tools)
  - Impact: Enables backtesting with historical data and Alpaca-only trading mode

- **Updated tests for Alpaca-only operation**
  - Removed `test_yfinance_fallback_*` tests from `test_alpaca_client_extended.py`
  - `ExitEngine` tests remain compatible (yfinance path still available when data not injected)
  - Impact: Tests reflect production code behavior

### Removed
- **`docs/PRICE_SOURCE_ARCHITECTURE.md` and `docs/DATA_SOURCE_ARCHITECTURE_ANALYSIS.md`**
  - Documents advocated hybrid yfinance/Alpaca approach for trading engine
  - No longer accurate after migration to Alpaca-only trading
  - Impact: Cleaner docs, no misleading architecture guidance

- **`docs/YFINANCE_ELIMINATION_PLAN.md` and `memory/alpaca-migration-plan.md`**
  - Planning documents for full yfinance elimination
  - Superseded by actual implementation (trading engine Alpaca-only, reports/tools keep yfinance)
  - Impact: Removed obsolete planning documents

- **`scripts/midday_scan.py` eliminated — duplicate of `entry_signals.py`**
  - Both scripts performed Stage 2 scoring → entry score calculation → tier ranking → HTML/CSV export
  - `midday_scan.py` used stale yfinance data (15-min delayed); `entry_signals.py` uses real-time Alpaca API
  - Unique feature (dollar volume filter) not worth separate script maintenance
  - Consolidated all scanning to single source of truth
  - Lines removed: 557
  - Impact: Cleaner codebase, real-time data only, no duplication

- **`scripts/analyze_ticker.py` and `scripts/analyze_watchlist.py` consolidated into `entry_signals.py`**
  - Both scripts duplicated analysis logic already present in `entry_signals.py`
  - Used yfinance (15-min delay) instead of Alpaca real-time API
  - Migration: `analyze_ticker.py TICKER` → `entry_signals.py --ticker TICKER`
  - Migration: `analyze_watchlist.py --csv` → `entry_signals.py --export-csv`
  - Migration: `analyze_watchlist.py --html` → `entry_signals.py --export-html`
  - Lines removed: 472 (142 + 330)
  - Lines added to `entry_signals.py`: 168
  - Impact: Single source of truth, real-time data, consistent risk config integration

- **`scripts/migrate_watchlist_stages.py` eliminated — one-time migration complete**
  - Migrated watchlist from 4-point to 7-point Stage 2 scoring system
  - Migration was already completed; all current entries use 7-point system
  - `watchlist_manager.py` and `entry_signals.py` now use `calculate_stage2_score()` natively
  - Lines removed: 69
  - Impact: Removed obsolete one-time utility script

- **`scripts/clean_trade_log.py` consolidated into `clean_test_trades.py`**
  - Merged detection rules: test_mode flag, AAPL@$150 pattern, validation_failed + test tickers
  - Added `--auto` flag to `clean_test_trades.py` for non-interactive mode (replaces `clean_trade_log.py`)
  - Simplified backup to always create `.jsonl.backup` extension
  - Lines removed: 68
  - Impact: Single cleanup script with all detection patterns

- **`scripts/temp_portfolio_status.py` eliminated**
  - Duplicated `paper_portfolio.py status` command functionality
  - Used deprecated yfinance (15-min delay) vs Alpaca real-time API
  - Had hardcoded account values, no trade log integration
  - Lines removed: ~50
  - Impact: Use `python3 scripts/paper_portfolio.py status` instead

- **`RELEASE_NOTES.md` eliminated**
  - Outdated release notes (v0.3.1 from 2026-04-09) vs current CHANGELOG.md (v0.3.15)
  - Avoids duplication and maintenance burden of dual files
  - Lines removed: 64
  - Impact: Single source of truth for release history

- **Orphaned JSON data files removed**
  - `data/portfolio.json` — Stale, superseded by `paper_positions.json`
  - `data/regime_tracker.json` — Stale, regime tracked in `memory/` now
  - `data/screening_criteria.json` — Orphaned, scanners use `risk_config.yaml`
  - Files removed: 3
  - Impact: Clean data directory, no stale files

- **`scripts/paper_engine.py` eliminated — superseded by `paper_engine_alpaca.py`**
  - Legacy yfinance-based engine (prototype) replaced by Alpaca-powered production engine
  - `paper_engine.py` used stale yfinance data (15-min delay) vs Alpaca real-time API
  - `paper_engine_alpaca.py` has all modern features: WebSocket, order manager, FINDING fixes
  - Per `YFINANCE_ELIMINATION_PLAN.md`: "Refactor to use `paper_engine_alpaca.py`"
  - Lines removed: ~443
  - Impact: Single production trading engine using real-time Alpaca data

### Added
- **Order Storm Protection (FINDING-004) in `order_manager.py`**
  - Submission queue with TPS limiting to prevent rate limit 429 errors during signal bursts
  - QueuedOrder dataclass with priority support for urgent orders
  - Background worker thread for async queue processing
  - Configurable max orders per second (default 2.0 TPS)
  - Graceful shutdown with `wait_for_queue_empty()`
  - Queue stats tracking: submitted, queued, rejected, errors
  - Lines added: ~310
  - Impact: Prevents API rate limits during high-frequency signals, prioritizes critical orders

### Fixed
- **`clean_test_trades.py` unrealistic price threshold raised**
  - Changed from $400 to $5000 to prevent false flagging of legitimate high-priced stocks
  - CAT (~$788), META, AMZN were incorrectly flagged as test data
  - Now only flags extreme test data errors while preserving legitimate entries
  - Impact: Legitimate high-priced stock trades no longer filtered as test data

### Changed
- **Reorganize library modules — proper package structure**
  - `scripts/trading_exceptions.py` → `traderlib/trading_exceptions.py` (library module)
  - `scripts/rate_limiter.py` → `traderlib/rate_limiter.py` (library module)
  - `scripts/generate_fixtures.py` → `tests/generate_fixtures.py` (dev utility)
  - `scripts/sync_state.py` — kept in scripts/ (user-facing utility)
  - Updated all imports: 12 files referencing trading_exceptions, 10 files referencing rate_limiter
  - Updated documentation: `docs/runbooks/api_outage.md`
  - Impact: Clear separation between library code (`traderlib/`), user scripts (`scripts/`), and test utilities (`tests/`)

- **Consolidate configuration files into single `config/` directory**
  - Moved `data/config/alpaca_config.json` → `config/secrets/alpaca_config.json`
  - Moved `data/config/example.alpaca_config.json` → `config/secrets/example.alpaca_config.json`
  - App settings remain at `config/risk_config.yaml`
  - Updated `alpaca_client.py` and `setup_alpaca.py` CONFIG_DIR paths
  - Updated `.gitignore` to ignore credentials in new location
  - Deleted empty `data/config/` directory
  - Benefits: Single config location, clear secrets/ subdir separation
  - Impact: Cleaner project structure, easier to find all configuration

## [0.3.15] - 2026-04-10

### Fixed
- **`paper_engine_alpaca.py` using stale Equity value instead of live Account Value**
  - Was using `get_equity()` which calculated position values using stale `entry_price`
  - Caused discrepancy between engine status and actual market values
  - Fix: Calculate Account Value using live prices from Alpaca API (WebSocket cache → cached price → live price)
  - Also renamed label from "Equity" to "Account Value" for consistency with `paper_portfolio.py`
  - Impact: Status now shows real-time account value matching Alpaca UI

- **Test mocks missing 'discrepancies' and 'synced' keys in `test_paper_engine_coverage.py`**
  - Tests were returning incomplete `sync_positions` mock data with `'modified'` instead of `'synced'`
  - Caused `KeyError: 'discrepancies'` when `_sync_with_alpaca()` tried to access the missing keys
  - Fixed all 3 test mocks to include correct keys: `'added'`, `'removed'`, `'discrepancies'`, `'synced'`
  - Impact: Tests no longer generate false exception log entries

- **CI/CD test failures after `paper_account.json` elimination (v0.3.14)**
  - Tests still referenced `paper_state.ACCOUNT_FILE` which no longer exists
  - Fixed 4 occurrences in `test_integration_paper_engine.py`
  - Fixed 7 occurrences in `test_paper_state_recovery.py`
  - Updated `test_paper_portfolio.py` to mock AlpacaClient and `load_json_file` properly
  - Impact: All 417 tests now pass in CI/CD pipeline

## [0.3.14] - 2026-04-10

### Removed
- **`paper_account.json` eliminated**
  - File stored stale cash values that caused discrepancies with Alpaca
  - All cash now fetched live from Alpaca API (`get_account()['cash']`)
  - Daily counters (entries_today, trade_count) now calculated from trade log
  - `last_entry_reset` moved to new `daily_tracker.json` file
  - Impact: No more stale local state; account value always matches Alpaca UI

### Changed
- **`paper_portfolio.py` refactored to remove account file dependency**
  - All commands now use Alpaca API or trade log as source of truth
  - `cmd_status()`: Cash from Alpaca, day stats calculated from trades
  - `cmd_live()`: Removed stale account reference
  - `cmd_report()`: Stats calculated from trade log only
  - `cmd_reconcile()`: Uses constant initial_capital, reconciles from log

### Added
- **`daily_tracker.json` for daily reset tracking**
  - Stores only `last_entry_reset` date to persist across engine restarts

### Added
- **`scripts/clean_trade_log.py` - permanent test data removal**
  - Removes test trades from `paper_trades.jsonl` at source
  - Detects: `_meta.test_mode`, AAPL@$150 pattern, validation_failed patterns
  - Creates timestamped backup before cleaning
  - Eliminates need for runtime filtering; source is now clean
  - Cleaned 11 test trades, 17 production trades remaining

## [0.3.13] - 2026-04-10

### Fixed
- **`paper_portfolio.py` using yfinance instead of Alpaca**
  - Was using yfinance for EOD prices, bypassing the fixed `get_latest_price()`
  - Caused $62.85 account value discrepancy (position values correct, cash sync stale)
  - Fix: Now imports and uses `AlpacaClient` for real-time pricing
  - Fix: Calls `alpaca.get_latest_price(ticker, use_fallback=False)` for all positions
  - Impact: Portfolio status now shows Alpaca real-time prices; matches Alpaca UI exactly

- **`paper_portfolio.py` cash now fetched from Alpaca API**
  - Was using stale `cash` value from local `paper_account.json` file
  - Caused $62.85 discrepancy ($9,664.27 local vs $9,727.12 Alpaca live)
  - Fix: `cmd_status()` now calls `alpaca.get_account()['cash']` for live cash balance
  - Fix: Shows `(Alpaca Live)` or `(Local (stale))` indicator next to cash display
  - Impact: Account value now 100% accurate; no more stale cash discrepancies

## [0.3.12] - 2026-04-10

### Fixed
- **`get_latest_price()` using wrong endpoint**
  - Was using `StockTradesRequest` which returned stale/after-hours trade prices
  - Caused $142 account value discrepancy vs Alpaca UI (e.g., AMD $236.35 vs $245.50)
  - Fix: Now uses position API `current_price` first (marked-to-market) for held positions
  - Fix: Falls back to `StockLatestQuoteRequest` (bid/ask midpoint) for non-positions
  - Impact: All prices now match Alpaca UI exactly; eliminated price source discrepancy

## [0.3.11] - 2026-04-10

### Fixed
- **`initial_risk: 0` bug in positions**
  - All 11 open positions had `initial_risk: 0` stored in JSON, breaking R-multiple calculations
  - Root cause: Position creation during sync wasn't properly persisting calculated `initial_risk`
  - Fix: Added validation/recalculation in `Position.from_dict()` - if `initial_risk` is 0 but valid entry/stop/shares exist, recalculate it
  - Fix: Data migration script recalculated and fixed all existing positions
  - Impact: Trailing stop logic (breakeven, +1.5R, +3R) now works correctly

### Tests
- **Updated 5 tests to align with security fixes**
  - `test_entry_submission_creates_pending_order`: Updated for new `submit_entry` signature with metadata
  - `test_full_workflow_entry_to_exit`: Updated to simulate fill confirmation before position creation
  - `test_order_success_records_order_and_signals`: Renamed and updated for deferred position creation
  - `test_status_with_account_data`: Updated assertion for EOD pricing format
  - `test_deleted_mid_session`: Fixed trade log data to use realistic tickers/prices

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
