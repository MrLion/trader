## [0.6.19.18] — 2026-06-19 — Improvement — Trend screener UX overhaul: setup/buy point 1:1 pairing + interactive HTML

### Changed
- **`scripts/trend_screener.py`** — `--entry-mode` choices renamed from `any/pocket/pivot/volume` to `any/pp/20d`. Pocket pivot is now the default priority in `any` mode (pp → 20d range → volume → trend fallback).
- **`scripts/trend_screener.py`** — Setup types merged: `pivot`, `volume`, and `trend` all use the same buy point (20-day range high), so they now render as a single `20d` badge. Only `pp` (pocket pivot) has a distinct buy point.
- **`scripts/trend_screener.py`** — `_try_pocket_pivot_setup()` now sets `pivot_price` to the pocket pivot price. Previously this was missing, causing the Buy Point column to show "—" for pocket pivot stocks.
- **`scripts/trend_screener.py`** — Section classification includes `pp` stocks in Ready Now (was excluded — only `pivot` and `volume` qualified).
- **`scripts/trend_screener.py`** — HTML export rewritten to match the approved mockup design:
  - Two badges only: `pp` (red) and `20d` (blue). No secondary pocket badge.
  - Section-aligned filter tabs: `All | Ready Now | Near Pivot | Extended | No Setup` (replaces orthogonal setup-type tabs).
  - `data-section` attribute on each row for section-based filtering.
  - Clickable summary bar with live-updating counts.
  - Active-filter banner with "Show all" link.
  - Detail rows survive filtering (only hidden stocks' details close).
  - URL hash persistence (`#ready`, `#near`, etc.).
  - Sortable columns with blue arrow indicator.
  - Dynamic denominator (reads from DOM, not hardcoded).
  - No Setup section always rendered with empty state.
  - Removed unused CSS classes (badge-pivot/trend/volume/pocket, signal-badge/pocket).
- **`tests/test_trend_screener.py`** — Updated pocket mode tests for `setup_type='pp'` and `pivot_price` fix. Updated any-mode test to assert pocket pivot is now primary. Added test for `--entry-mode 20d`. Added `TestHtmlOutput` class verifying badges, no secondary pocket badge, and `data-section` attributes.

### Added
- **`plans/trend-screener-ux-overhaul.md`** — Implementation plan documenting the setup/buy point 1:1 pairing design, entry mode changes, HTML UX improvements, and testing requirements.

---

## [0.6.19.17] — 2026-06-19 — Fix — Pocket pivot as signal overlay, VCP removed, rich HTML export restored

### Fixed
- **`scripts/trend_screener.py`** — Pocket pivot no longer overrides the primary `setup_type` in `--entry-mode any`. It is detected separately and rendered as a `pocket $price` signal badge, matching the original scan design. The primary setup priority in `any` mode is restored to 20-day range pivot → volume spike → trend fallback.
- **`scripts/trend_screener.py`** — Restored the rich interactive HTML export (filters, summary cards, grouped sections, detail rows with MA stack) that had been replaced by the plain pandas `to_html()` output.
- **`scripts/trend_screener.py`** — Removed all remaining VCP references now that VCP has been retired from the project: dropped `--entry-mode vcp`, `--detect-vcp`, VCP-specific CLI args, VCP filter logic, and VCP styling from the HTML export.

### Changed
- **`scripts/trend_screener.py`** — Result dict now includes `pivot_price` (the relevant buy point for the selected setup) to power the HTML "Buy Point" column.
- **`tests/test_trend_screener.py`** — Renamed `test_any_mode_prefers_pocket_pivot_over_trend` to `test_any_mode_detects_pocket_pivot_as_signal_overlay` and updated assertions to reflect that `any` mode keeps pocket pivot as a signal, not the primary setup. Removed obsolete VCP-specific tests.
- **`plans/add-pocket-pivot-to-trend-screener.md`** — Updated to document signal-overlay behavior, VCP retirement, and rich HTML export.

---

## [0.6.19.16] — 2026-06-19 — Improvement — Pocket pivot entry mode in trend screener

### Added
- **`scripts/trend_screener.py`** — New `--entry-mode pocket` uses the shared `traderlib.pivot_detection.detect_pivot(..., technique='pocket_pivot')` library. When a pocket pivot is detected within `--pivot-proximity`, the result is marked `entry_ready=True` with `setup_type='pocket'`.
- **`scripts/trend_screener.py`** — Result dict now includes `has_pocket_pivot` and `pocket_pivot_price` for downstream CSV/HTML consumers.

### Changed
- **`scripts/trend_screener.py`** — `--entry-mode any` now tries actionable setups in priority order (VCP → pocket pivot → 20-day range pivot → volume spike) before falling back to `setup_type='trend'`. Previously it only tried the 20-day pivot and immediately fell back to trend, which was user-unfriendly and caused valid pocket-pivot stocks to be labeled "No Setup".
- **`scripts/trend_screener.py`** — Cleaned up stale module and class docstrings that still referred to the removed "MA convergence" feature.
- **`tests/test_trend_screener.py`** — Added `TestPocketPivotEntryMode` covering pocket-pivot detection, proximity gating, any-mode priority, and trend fallback.
- **`plans/add-pocket-pivot-to-trend-screener.md`** — Updated to document the Option B `any`-mode redesign.

---

## [0.6.19.15] — 2026-06-10 — Fix — Dashboard activity panel empty after restart

### Fixed
- **`scripts/paper_engine_alpaca.py:_seed_dashboard_events`** — After engine
  restart, today's trades were missing from the activity panel because events
  only lived in memory. Now seeds ENTRY, EXIT, and scale-out events from the
  on-disk trade log on startup.
- **`scripts/paper_engine_alpaca.py`** — Live engine `log_event()` calls for
  EXIT and scale-out now include the exit reason (e.g. `[STOP_HIT]`,
  `[SCALE_OUT_3.0R]`) in the detail field for consistent format across events
  and across live vs seeded paths.

---

## [0.6.19.14] — 2026-06-10 — Fix — YTD trade-log fallback gated on wrong condition

### Fixed
- **`scripts/paper_engine_alpaca.py:_prefetch_portfolio_data`** — The trade-log fallback was gated on ALL portfolio history calls failing (`fetch_failed`). The 1M and 'all' calls succeed (providing sparkline data), so YTD was the only one failing and the condition was never met. Now gates on YTD specifically: if YTD from Alpaca is 0.0 or None, the trade-log fallback runs regardless of whether other calls succeeded.

---

## [0.6.19.13] — 2026-06-09 — Fix — Open market YTD always $0 when portfolio history API unavailable

### Fixed
- **`scripts/paper_engine_alpaca.py:_prefetch_portfolio_data`** — Added trade-log fallback for YTD P&L when Alpaca portfolio history API fails (same pattern as post-market path). Derives YTD pct from current Alpaca equity.
- **`scripts/paper_engine_alpaca.py:_print_status`** — ACCOUNT VALUE no longer double-counts cash (same fix as post-market v0.6.19.11, applied to open-market path).

### Changed
- **`tests/test_paper_engine_prefetch.py`** — Added `_make_spy_bars` helper, SPY bar mock in `test_print_status_includes_portfolio_fields`, and trade-log cleanup in YTD-zero tests to isolate from test ordering.

---

## [0.6.19.12] — 2026-06-09 — Fix — Open market ACCOUNT VALUE double-counted cash

### Fixed
- **`scripts/paper_engine_alpaca.py:_load_post_market_state`** — Alpaca's `get_account()` returns `equity` as total value (cash + positions). The dashboard computes `ACCOUNT VALUE = cash + equity`, so storing Alpaca's total equity caused cash to be counted twice (reported $159K vs actual $107K). Now subtracts cash to store position-only equity.
- **`scripts/paper_engine_alpaca.py:_load_post_market_state`** — When `get_portfolio_history()` fails, YTD pct stayed 0.0% even though YTD dollar value was correctly computed from the trade log. Now derives YTD pct from current Alpaca equity.

### Changed
- **`tests/test_post_market_state.py`** — Updated equity assertion to reflect new position-only convention.

---

## [0.6.19.10] — 2026-06-08 — Improvement — Simplify post-market state code

### Changed
- **`scripts/paper_engine_alpaca.py:_load_post_market_state`** — Merged 3 separate trades.jsonl scans (today_stats, lifetime count, YTD fallback) into a single file pass. Replaced brittle `api_failures >= 4` counter with direct boolean check.
- **`traderlib/dashboard.py:_stats`** — YTD sentinel changed from `ytd_pnl != 0.0` to `ytd_pnl is not None`, so a genuine $0 YTD is shown while absent data is hidden.
- **`tests/test_post_market_state.py`** — Updated YTD assertions to expect `None` (not `0.0`) when no data is available.
- **`tests/test_dashboard.py`** — Added `test_dashboard_ytd_shows_when_zero_real`; renamed YTD-hidden test to reflect None sentinel.

---

## [0.6.19.9] — 2026-06-08 — Fix — Post-Market Dashboard Shows Real Account Data

### Fixed
- **`scripts/paper_engine_alpaca.py:_load_post_market_state`** — Rewrote the standalone function to fetch real data from Alpaca instead of fabricating numbers. The function now creates its own `AlpacaClient`, makes 4 API calls (get_account, get_latest_prices_batch, get_portfolio_history, get_historical_bars), and reads `trades.jsonl` for trade statistics. Each field falls back independently on failure. (Fixes: CASH $0.00, ACCOUNT VALUE = positions only, DAY P&L $0.00, YTD $0.0%, TODAY: no closed trades yet, Total Trades: 0)
- **`scripts/paper_engine_alpaca.py:_print_status`** — Extracted inline regime detection into `_compute_regime(spy_hist, vix)` helper at module level, now callable from both the open-market and post-market paths.
- **`traderlib/dashboard.py:_stats`** — YTD line is hidden when `ytd_pnl` is $0 (indicates fallback failure or no data), avoiding a misleading "YTD $0 (+0.0%)" display.

### Added
- **`tests/test_post_market_state.py`** — 12 tests covering Alpaca data sourcing, trade log integration, fallback paths, regime detection, and missing-file edge cases.

### Changed
- **`tests/test_dashboard.py`** — Added `test_dashboard_ytd_hidden_when_zero` to verify YTD omission.

---

## [0.6.19.8] — 2026-06-07 — Fix — Dashboard ACCOUNT VALUE = Cash + Equity

### Fixed
- **`traderlib/dashboard.py:_stats`** — The top-line "ACCOUNT VALUE" was rendering `state["equity"]` directly, but the engine's `equity` field is the market value of open positions, not the total account. The formula is `account value = cash + equity (positions)`. The dashboard now computes the sum and displays the result as ACCOUNT VALUE, so the label matches the number.

### Changed
- **`tests/test_dashboard.py::test_stats_shows_equity_and_day_pnl`** — Renamed to `test_stats_shows_account_value_and_day_pnl` and updated the expected value to reflect the corrected formula. mock_state has `cash=45200, equity=103420.50`, so the rendered ACCOUNT VALUE is now `148,620.50` (was `103,420.50`).

---

## [0.6.19.7] — 2026-06-07 — Improvement — Dashboard UX (Height-Tiered, Sparkline, Lifetime)

### Added
- **`traderlib/dashboard.py`** — Height-tiered responsive render: short (24-row) terminals see equity, positions, today summary, and activity; medium (35-row) adds today's closed trades; full (50-row) adds the lifetime panel (Sharpe / Max DD / Total Trades). The dashboard adapts to whatever terminal size you give it.
- **`traderlib/dashboard.py`** — New top line: `ACCOUNT VALUE $X  DAY P&L ▲ $X  YTD $X (+X.X%)`. YTD is sourced from Alpaca's portfolio history so it matches your account, not a local cache.
- **`traderlib/dashboard.py`** — 30-cell Unicode block sparkline (`▁▂▃▄▅▆▇█`) of last 30 daily equity points, with a `K`/`M` shorthand current-value label.
- **`traderlib/dashboard.py`** — Post-market closed-trades section. Reads `data/paper/trades.jsonl` for today's EXIT/STOP/SCALE rows and renders `icon HH:MM TYPE TICKER entry->exit pnl`. Capped with a `+N more` overflow line.
- **`traderlib/dashboard.py`** — Lifetime panel (post-market 50-row only): `Sharpe / Max DD / Total Trades`. Sharpe and Max DD show `--` until 30+ equity points are available; Total Trades is always shown.
- **`traderlib/dashboard.py`** — Row caps on positions and activity. Long lists scroll instead of pushing the rest of the dashboard off-screen. `+N more positions` / `+N more events` overflow indicators.
- **`traderlib/dashboard.py`** — `avg_r` precision tightened to 2 decimals (was 1). Activity log rows now include the trade's R-multiple.
- **`traderlib/stats_calculator.py`** (new) — `StatsCalculator.lifetime_stats(equities)` returning `{sharpe, max_dd}`. Annualizes Sharpe with `sqrt(252)`, uses sample std dev. Returns `None` for both metrics below the 30-point threshold.
- **`traderlib/alpaca_client.py`** — `get_portfolio_history(period, timeframe)` method. The SDK returns lists (not scalars); this method normalizes the response.
- **`scripts/paper_engine_alpaca.py`** — Engine pre-fetches portfolio history at startup (YTD + 30D + all-time) and persists to `data/{mode}/portfolio_history.json` for cross-process reuse. Refetches on date roll; falls back to previous in-memory cache on Alpaca failure.
- **`scripts/paper_engine_alpaca.py`** — `_count_lifetime_exits()` counts EXIT events from the trade log, with test-trade filtering so test runs do not pollute lifetime stats.
- **`scripts/paper_engine_alpaca.py`** — Five new `state_data` fields wired into `_print_status`: `ytd_pnl`, `ytd_pnl_pct`, `equity_30d`, `equity_all`, `lifetime_trade_count`.
- **`traderlib/paths.py`** (new) — `data_dir()` and `project_root()` centralization. `data_dir()` honors the `PAPER_TRADING_DATA_DIR` env var so test runs never touch production data.
- **`tests/test_dashboard.py`** — 24 new tests covering row caps, height tiers, account value/YTD, equity sparkline, closed trades, and lifetime stats (32 tests total in this file).
- **`tests/test_stats_calculator.py`** (new) — 14 tests for Sharpe / Max DD / threshold behavior.
- **`tests/test_paper_engine_prefetch.py`** (new) — 10 tests for engine pre-fetch (first call, date roll, Alpaca failure fallback, lifetime exit counting).

### Design
- Pre-fetch happens at engine startup, not on every dashboard refresh, so the dashboard renders instantly and the API gets a single batch call per day.
- Failures (Alpaca down, malformed payload) degrade gracefully: empty defaults, previous cache, or `--` for incomplete metrics. No crashes.
- The trade log path uses `data_dir() / 'paper' / 'trades.jsonl'`, so per-mode isolation is automatic and tests can route to a temp dir via `PAPER_TRADING_DATA_DIR`.

---

## [0.6.19.3] — 2026-05-31 — Improvement — Discovery Progress Indicators

### Added
- **`traderlib/universe_builder.py`** — Optional `progress_callback` parameter on all slow I/O methods (`_get_current_prices`, `_compute_dollar_volumes`, `_fetch_sectors_from_fmp`, `build_universe`, `load_universe`). Callback receives a `ProgressUpdate` TypedDict (`step`, `current`, `total`, `message`). Library emits raw updates; callers decide how to render.
- **`traderlib/sector_resolver.py`** — `PROGRESS_STEP_SECTORS` constant and time-throttled progress callback in `prefetch_from_fmp()`. Emits every 2 seconds during 1,300-ticker FMP batch to avoid log spam while keeping users informed during tail latency.
- **`scripts/trend_screener.py`** — Discovery mode now prints indented progress lines (`    Fetching prices X/Y`, `    Computing liquidity X/Y`, `    Fetching sectors X/Y`) during the 4+ minute pipeline. No dead silence.
- **`tests/test_universe_builder.py`** — `TestProgressCallback` with 3 tests verifying callback invocation at unit level (`_get_current_prices`, `_compute_dollar_volumes`) and integration level (`build_universe` propagation).

### Design
- `ProgressUpdate` TypedDict avoids brittle positional arguments and is extensible (add `eta_seconds` later without breaking callers).
- All callback parameters default to `None`; existing callers (paper engine, backtest, tests) require zero changes.
- Fallback notices when Alpaca batch/chunk fails provide visibility during slower individual fetches.

---

## [0.6.19.2] — 2026-05-31 — Fix — Remove Non-Functional Convergence Scoring

### Removed
- **`scripts/trend_screener.py`** — Removed convergence scoring and grade grouping. The scoring formula was mathematically incompatible with momentum filters, producing zero Grade A results across all profiles. Grade A/B/C grouping and convergence score columns removed from output.
- **CLI args removed:** `--min-convergence-score`, `--cluster-spread-pct`, `--min-cluster-size`, `--hide-grade-c`, `--rank-by convergence`
- **`config/screener_config.yaml`** — Removed `min_convergence_score` from large_cap and high_octane profiles
- **`config/strategies/example_trailing.yaml`** — Removed `min_convergence_score` reference
- **`tests/test_trend_screener.py`** — Removed convergence-specific tests; ranking tests rewritten for `setup` and `rs` criteria

### Changed
- **Default ranking** changed from `convergence` to `setup` (entry-ready stocks first, then proximity, then Stage 2 score)
- **`setup_type` label** changed from `'convergence'` to `'trend'` when no VCP/pivot is detected
- **Output format** is now a single ranked table instead of Grade A/B/C groups
- **Default export** changed to CSV (`--export csv`). Results are saved to `scans/trend_screen_YYYYMMDD.csv` automatically. Use `--export none` to opt out.

### Preserved
- `calculate_convergence_score()` and `get_convergence_grade()` remain in `traderlib/stage2_utils.py` for use by `entry_signals.py` and other single-ticker analysis tools
- `tests/test_ma_convergence.py` unchanged

---

## [0.6.19.1] — 2026-05-31 — Fix — Sync Merge Position State + Minimal Audit Logging

### Fixed
- **`scripts/paper_engine_alpaca.py:260-331`** — Sync loop now **merges** existing positions instead of replacing them. Previously, `_sync_with_alpaca()` destroyed `initial_stop_price`, `entry_date`, and `scale_out_history` by creating a brand new `Position` object. The merge path updates only mutable fields (`shares`, `stop_price`, `target_price`, `current_stop_type`, `entry_price`, `initial_risk`) while preserving immutable entry facts.

### Added
- **`traderlib/paper_state.py`** — Minimal audit logging at state chokepoints:
  - `STATE_LOAD` / `STATE_LOAD_EMPTY` / `STATE_LOAD_FAIL` — logs position count, file size, and load errors on engine startup
  - `STATE_SAVE_VERIFY` / `STATE_SAVE_VERIFY_FAIL` — lightweight post-save count verification
  - `INTEGRITY_TRADE_LOG` — cross-references trade log `ENTRY`/`EXIT` counts against loaded positions to detect missing tickers
- **`traderlib/trading_exceptions.py`** — `log_operational()` class method for non-exception state events (sync merge, new position, integrity warnings).
- **`tests/test_paper_engine_sync.py`** — Proves `initial_stop_price` survives sync merge and object identity is preserved.
- **`tests/test_paper_state_logging.py`** — Tests for `STATE_LOAD`, `STATE_SAVE_VERIFY`, and `INTEGRITY_TRADE_LOG` emissions.

### Changed
- **`docs/superpowers/specs/2026-05-30-operational-state-logging-design.md`** — Marked as implemented.
- **`docs/superpowers/plans/2026-05-30-sync-merge-audit-logging-plan.md`** — Marked as implemented.

---

## [0.6.19.0] — 2026-05-26 — Refactor — Remove VCP Strategy Plugin System

### Removed
- **`traderlib/strategies/`** — Deleted the entire strategy plugin architecture (`Strategy` ABC, registry, `VCPBreakout` strategies, `CompositeStrategy`). This system was unused in production, duplicated existing systems (`entry_signals.py` for entries, `ExitEngine` for exits), and had caused bugs (R-calculation bug, exit override issue).
- **`config/strategies/vcp_large_cap.yaml`** and **`vcp_high_octane.yaml`** — VCP strategy config files.
- **`tests/test_strategy_abc.py`**, **`test_vcp_strategy.py`**, **`test_composite_strategy.py`**, **`test_vcp_breakout.py`**, **`test_rdw_regression.py`** — Tests for the deleted strategy plugin system. Dashboard frozen indicator tests moved to `test_dashboard.py`.
- **`docs/strategies/OVERVIEW.md`** and **`VCP_BREAKOUT.md`** — Strategy plugin documentation. Moved to `docs/archive/`.
- **`strategy.manage_exits` toggle** — Removed from `config/risk_config.yaml` and `traderlib/risk_config.py`. This was a temporary safety measure added in 0.6.18.2; it is now unnecessary because the feature it gated no longer exists.

### Changed
- **`traderlib/backtest/strategy.py`** — Inlined `EntrySignal`, `StrategyContext`, and `Strategy` ABC from the deleted `traderlib/strategies/__init__.py`. The backtest system is now self-contained with no dependency on a separate strategies module. `ExitAction`/`ExitActionType` imported directly from `traderlib/paper_exits.py`.
- **`scripts/paper_engine_alpaca.py`** — Removed `--strategy` CLI flag, `_load_strategy()`, `_build_context()`, `_process_exit_action()`, and the strategy plugin branch in `_check_exits()`. The engine now uses only the legacy `ExitEngine` path for exits.
- **`scripts/backtest.py`** — `--strategy` flag deprecated (no-op with warning). Always instantiates `Stage2MomentumStrategy` regardless of flag value.
- **`docs/ARCHITECTURE.md`**, **`README.md`**, **`CLAUDE.md`** — Removed all strategy plugin architecture references.
- **`traderlib/strategy_config.py`** — Updated docstrings to use `stage2_momentum` as the example instead of `vcp_large_cap`/`vcp_high_octane`.

---

## [0.6.18.2] — 2026-05-26 — Fix — VCP R-Calculation, Dashboard Stale Data, Strategy Exit Override

### Fixed
- **`traderlib/strategies/vcp_breakout.py`** — R-multiple calculation now uses `position.initial_stop_price` instead of `position.stop_price`. Previously, when a trailing stop ratcheted to breakeven, `stop_price == entry_price` caused `initial_risk = 0`, making `r_multiple = 0` forever and preventing Phase 2 EMA trailing from ever triggering.
- **`scripts/paper_engine_alpaca.py`** — Main loop reordered so `_check_exits()` runs **before** `_print_status()`. Previously the dashboard rendered stale stop data from the previous 30-second cycle, hiding exit updates for up to 30 seconds (permanently if the market closed in that window).
- **`traderlib/dashboard.py`** — Added red "Data frozen since HH:MM:SS" indicator to the header when `market_status != "OPEN"`, preventing confusion from stale terminal output after market close.

### Added
- **`config/risk_config.yaml`** — New `strategy.manage_exits` toggle (default: `true`). When set to `false`, the legacy `ExitEngine` (hybrid mode, EMA trailing, scale-outs from `risk_config.yaml`) handles all positions regardless of loaded strategy plugin.
- **`traderlib/risk_config.py`** — `StrategyConfig` dataclass with `manage_exits: bool`, wired into `RiskConfig` and parsed from YAML.
- **`tests/test_rdw_regression.py`** — Regression tests covering all three bugs: VCP R-calculation with breakeven positions, dashboard frozen indicator, and strategy config toggle parsing.

## [0.6.18.1] — 2026-05-18 — Fix — Progress Bar + Category Leaders Output

### Fixed
- **`scripts/sector_scan_comprehensive.py`** — Replaced verbose per-ticker print wall with a transient `rich` progress bar (spinner, bar, percentage, elapsed time). TOP 10 output now shows all timeframes (1W/1M/3M/6M), category, rank score, and Stage 2 score in a tabular format. Added "TOP 3 BY CATEGORY" section grouping results by the 8 ETF categories for rotation analysis at a glance. Default top N reduced from 15 to 10.

## [0.6.18.0] — 2026-05-18 — Enhancement — Categorized Sector Scan ETF Config

### Added
- **`config/sector_etfs.yaml`** — New ETF configuration file with 148 tickers organized across 8 categories: US Sector (11 GICS), US Sub-sector (60), Commodities (11), International (20), Bonds (15), Factors/Style (21), Thematic (7), REITs (3). Replaces the hardcoded ETF list.
- **`Category` column** — Scan CSV output now includes a Category column populated from the config, enabling category-based filtering and analysis in the premarket report HTML/console output.

### Changed
- **`scripts/sector_scan_comprehensive.py`** — ETF universe now loads from `config/sector_etfs.yaml` instead of a hardcoded tuple list. Loop unpacks (ticker, name, category) triples. Category written to results dict and CSV output.
- **`scripts/premarket_report.py`** — `load_comprehensive_scan()` reads Category column from CSV. HTML sector leaders table and console output display ETF category.
- **`docs/scripts/sector_scan.md`** — Updated ETF count from 131 to 148. Category column documented in CSV output reference.

### Fixed
- **Duplicate ETF removal** — Removed 13 redundant tickers (BND, XPH, HACK, WCLD, XAR, XTN, XHB, SCHH, IYR, PSR, MORT, PAVE, RGI) keeping the more liquid/representative alternative in each pair.
- **`scripts/watchlist_manager.py`** — Stale reference to deleted `sector_scan.py` corrected to `sector_scan_comprehensive.py`.
- **`tests/test_sector_scan.py`** — Removed (tested a deleted module).

### Added
- **`tests/test_sector_scan_comprehensive.py`** — New test class `TestETFConfigLoading` verifies config loads correctly, all entries are (ticker, name, category) triples, and all 8 expected categories are present.

## [0.6.17.6] — 2026-05-17 — Bug Fix — FMP 429 Retry + Reduced Concurrency

### Fixed
- **`traderlib/sector_resolver.py`** — FMP sector fetch now retries HTTP 429 responses up to 5 times with jittered exponential backoff. Reduced `ThreadPoolExecutor` workers from 5 to 2 to avoid triggering FMP's server-side rate limit. Added sequential cleanup pass for stragglers. Resolution rate improved from 66% (459/697) to 99.7% (695/697) across a full universe build.

## [0.6.17.5] — 2026-05-17 — Bug Fix — Sector Cache Poisoning

### Fixed
- **`traderlib/sector_resolver.py`** — `SectorResolver` no longer caches `"Unknown"` from failed FMP API calls. Previously, when batch-fetching 697 tickers during universe build, ~40% of FMP calls would fail (timeout/rate-limit), and the `"Unknown"` result was stored in the in-memory cache permanently. All future scans for those tickers returned `"Unknown"` even though FMP had the data. Now only successful (non-Unknown) results are cached, allowing retries on subsequent lookups. Reduced `ThreadPoolExecutor` workers from 10 to 5 for better API stability.

## [0.6.17.4] — 2026-05-17 — Enhancement — Animated Spinner for Setup Phase

### Changed
- **`scripts/entry_signals.py`** — Setup phase status messages now display with an animated `rich` dots spinner instead of plain static text. The spinner appears while earnings prefetch and market conditions run in parallel, giving clear visual feedback that the script is active.

## [0.6.17.3] — 2026-05-17 — Enhancement — Parallel Setup + Status Messages

### Changed
- **`scripts/entry_signals.py`** — Earnings prefetch and market conditions check now run in parallel via `ThreadPoolExecutor(max_workers=2)`, reducing the silent delay before the scan progress bar appears by approximately 50%.
- **`scripts/entry_signals.py`** — Added status messages before setup phase so the user knows what's happening: `📅 Prefetching earnings for N tickers...` and `📊 Checking market conditions...`.

## [0.6.17.2] — 2026-05-17 — Enhancement — Rich Progress Bar + Silent Stop Logging

### Changed
- **`scripts/entry_signals.py`** — Scan loop now displays a `rich.progress` bar with animated spinner, progress bar, percentage, running signal count, and elapsed timer. The progress bar is transient (disappears cleanly when the scan completes, leaving only the dashboard output).
- **`traderlib/ticker_analyzer.py`** — Three internal stop-decision `print()` messages (pocket_pivot stop looser than ATR/MA, outside bounds, clamped to bounds) converted to `logger.debug()`. These are no longer visible during normal scans; enable with `python3 scripts/entry_signals.py --debug` or `LOG_LEVEL=DEBUG` to see them for troubleshooting.

## [0.6.17.1] — 2026-05-17 — Bug Fix — Dashboard Unknown Sector Display

### Fixed
- **`traderlib/dashboard.py`** — `_sector_exposure()` now correctly uses the dict key (ticker symbol) as the ticker identifier when live-re-resolving "Unknown" sectors. Previously it checked `pos.get("ticker")` which was always `None` because `positions_data` uses ticker as the dict key, not a field inside the position dict. This caused old positions (entered before sector enrichment) to always display as "Unknown" in the sector exposure chart.

## [0.6.17.0] — 2026-05-17 — Feature — Sector Enrichment + Shared SectorResolver

### Added
- **`traderlib/sector_resolver.py`** — New shared `SectorResolver` with 3-tier fallback: watchlist CSV → universe CSV → FMP API `/stable/profile`. Includes `ThreadSafeRateLimiter` (token-bucket, `threading.Lock`-protected) for FMP's 300 req/min budget. In-memory cache prevents redundant lookups across calls.
- **`traderlib/universe_builder.py`** — Universe CSV files now include a `Sector` column. FMP sector fetch runs after dollar-volume filter (~600 tickers) during `build_universe()`, cached with 4h TTL.
- **`tests/test_sector_resolver.py`** — 14 tests covering rate limiter thread safety, 3-tier fallback chain, caching, FMP fail-open, and normalization of ETF noise (`"—"`, `"ETF"`, `""` → `'Unknown'`).

### Changed
- **`traderlib/ticker_analyzer.py`** — Sector lookup now delegates to `SectorResolver` instead of reading watchlist directly. `set_universe_path()` passes universe CSV to resolver for Tier 2 fallback.
- **`scripts/entry_signals.py`** — Scan from universe profile (`--source large_cap`) now passes universe path to analyzer for sector resolution.
- **`scripts/trend_screener.py`** — Output now includes `sector` via `SectorResolver`.
- **`scripts/paper_engine_alpaca.py`** — Sector lookup replaced with `SectorResolver.resolve()`. Watchlist `Stop_Level`/`Pivot_Price` lookups preserved.
- **`scripts/paper_portfolio.py`** — Sector lookup replaced with `SectorResolver.resolve()`. Watchlist `Stop_Level` fallback restored after review.
- **`traderlib/strategies/vcp_breakout.py`** — `_get_sector()` implemented via `SectorResolver` (instance reused from `__init__`).
- **`traderlib/backtest/strategy.py`** — Fixed PascalCase column bug: watchlist DataFrame columns normalized to snake_case before sector lookup.

### Fixed
- **PascalCase column normalization** in backtest strategy `watchlist_df` lookup — previously `'sector'` (snake_case) was checked against PascalCase DataFrame columns, always returning `'Unknown'`.


## [0.6.16.9] — 2026-05-17 — Fix — Pre-Existing Test Failures in paper_portfolio

### Fixed
- **`tests/test_paper_portfolio.py`** — 8 pre-existing test failures resolved. `TestLoadTrades` updated to pass `trades_file` directly (function signature changed from module-level constant to parameter). `TestDataPaths` imports `DEFAULT_DATA_DIR` (renamed from `DATA_DIR`). `test_env_override` tests `_get_data_dir()` instead of the hardcoded constant. `test_status_shows_alpaca_data` no longer asserts initial capital is printed directly.


## [0.6.16.8] — 2026-05-12 — Enhancement — Pocket Pivot Default Entry Mode

### Changed
- **`scripts/entry_signals.py`** — Default pivot mode changed from `auto` (VCP→pocket→20d fallback chain) to `pocket_pivot`. `--pivot-mode` now defaults to `pocket_pivot` when running without the flag. Tickets without a detectable pocket pivot still fall back to 20d range high (existing fallback at `ticker_analyzer.py:267`).


## [0.6.16.7] — 2026-05-11 — Bug Fix — Scale-Out Fill Closes Entire Position (Ghost Exit)

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `_process_pending_orders()` no longer calls `close_position()` for scale-out exit fills. Previously, any scale-out order fill would delete the entire position from local state. On the next engine restart, `_sync_with_alpaca()` would recreate the position from Alpaca without `scale_out_history`, causing the same R-level trigger (e.g. 3.0R) to fire repeatedly — once per engine restart cycle. Now scale-out fills update cash, log the partial exit with the correct shares sold, and keep the remaining position open with its `scale_out_history` intact.

### Changed
- **`scripts/paper_engine_alpaca.py`** — Added `_handle_scale_out_fill()` method to handle partial exit fills separately from full position closes. Trade EXIT events now record `partial_exit: True` and `remaining_shares` in `_meta` for scale-outs.


## [0.6.16.6] — 2026-05-10 — Enhancement — DIST Column Replaced with R-Multiple

### Changed
- **`traderlib/dashboard.py`** — Post-market dashboard `DIST` column replaced with `R` column showing `+1.6R` format instead of distance-to-stop percentage. Uses same R-multiple calculation already driving row color coding, directly answering "how many R's is this trade up?"

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `_load_post_market_state()` now includes `initial_stop_price` in the serialized position state, ensuring the post-market dashboard can compute R-multiple correctly.


## [0.6.16.5] — 2026-05-06 — Bug Fix — Test Isolation Leak & Portfolio Display

### Fixed
- **`tests/test_order_manager.py`** — `tearDown()` no longer pops `PAPER_TRADING_DATA_DIR` env var. It now saves and restores the original value, preventing subsequent tests from losing data isolation and writing to production `data/paper/`.
- **`tests/test_paper_portfolio.py`** — All `Mock()` args objects now include `mode='paper'` so `_get_data_dir()` resolves correctly instead of crashing on `Path / Mock()`.

### Changed
- **`scripts/paper_portfolio.py`** — Account section redesigned for clarity: shows Cash, Positions Value, Account Value, Buying Power (with 4× margin label), and P&L instead of the old Initial Capital / Account Value / Available Cash format.

### Restored
- **`data/paper/positions.json`** — Recovered 8 positions from Alpaca after test-suite corruption. Stop prices and types reconstructed from trade log + dashboard data.
- **`data/paper/trades.jsonl`** — Cleaned 30 test entries (`test_mode: true`) that leaked from the test suite.


## [0.6.16.4] — 2026-05-05 — Bug Fix — Eliminate Optimistic Exit Close (Ghost Exit)

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `_execute_exit()` no longer calls `state.close_position()` optimistically on order submission. The position is now closed ONLY when Alpaca confirms the fill in `_process_pending_orders()`. This eliminates "ghost exits" where a trade was logged locally (with realized P&L, trade log entry, and dashboard event) but Alpaca never actually filled the order, leaving the position open in the broker account. On next engine restart, `_sync_with_alpaca()` would silently recreate the position with Alpaca's `avg_entry_price`, causing stale phantom positions. Also moves dashboard logging, cooldown tracking, and P&L printout to the confirmed-fill path.


## [0.6.16.3] — 2026-05-05 — Bug Fix — Post-Market Dashboard Uses Mode-Specific Paths

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `_load_post_market_state()` now accepts a `mode` parameter and reads from `data/{mode}/positions.json` instead of the hardcoded legacy `data/paper_positions.json`. The pre-market wait loop passes `args.mode` so the dashboard shows the correct positions for paper vs live. Previously the post-market summary loaded stale pre-migration data, causing exited positions (e.g. PRIM after earnings) to incorrectly appear as still open.


## [0.6.16.2] — 2026-05-05 — Bug Fix — Paper Portfolio Mode-Aware Data Paths

### Fixed
- **`scripts/paper_portfolio.py`** — Now resolves data paths to mode-specific subdirectories (`data/paper/`, `data/live/`) introduced in 0.6.16.0. Previously hardcoded to the legacy flat `data/paper_positions.json`, causing the CLI to read stale pre-migration positions instead of the engine's actual state. All commands (`status`, `live`, `today`, `history`, `report`, `close`, `reconcile`) respect the `--mode` flag.
- **`scripts/paper_portfolio.py`** — `AlpacaClient` and `PaperState` now initialized with the correct `mode` parameter so `close` and `reconcile` operate on the right account.
- **`scripts/paper_portfolio.py`** — Header and help text updated to reflect paper/live support.


## [0.6.16.1] — 2026-05-02 — Documentation — Live State Isolation Coverage

### Added
- **`docs/trading-modes.md`** — New guide covering paper vs live modes, data isolation, risk config separation, dashboard mode badge, migration from v0.6.15.x, and safety guardrails.

### Changed
- **`README.md`** — Updated repo tree to show mode-partitioned `data/` and `config/` directories; trading scripts table links to trading-modes.md.
- **`docs/ARCHITECTURE.md`** — File organization tree updated with `data/paper/`, `data/live/`, `config/paper/`, `config/live/` structure.
- **`docs/getting-started.md`** — Trade log paths updated to `data/paper/trades.jsonl`; engine start examples include `--mode` flag; links to trading-modes.md.
- **`docs/RISK_GUIDE.md`** — Added mode-specific config section with paper vs live defaults comparison table.
- **`docs/config/configuration-reference.md`** — Updated config file references to `config/paper/risk_config.yaml` (default) with live variant noted.
- **`docs/DEPLOYMENT.md`** — Updated persistent file paths and `PAPER_TRADING_DATA_DIR` documentation.
- **`docs/scripts/paper_portfolio.md`** — Updated file path references.
- **`docs/runbooks/data_quality.md`** — Updated cleanup path.
- **`docs/runbooks/partial_fill.md`** — Updated code example path.


## [0.6.16.0] — 2026-05-02 — Live State Isolation

### Added
- **`scripts/paper_engine_alpaca.py`** — Mode-specific data directories (`data/paper/`, `data/live/`) fully isolate state between paper and live trading. One-time migration on startup moves existing flat files into `data/paper/`.
- **`config/paper/risk_config.yaml`** — Paper risk config (same as before, from `config/risk_config.yaml`).
- **`config/live/risk_config.yaml`** — Live risk config with conservative defaults (0.25% risk/trade, 1% daily loss limit, 5% max position).
- **`traderlib/dashboard.py`** — Dashboard header now shows a color-coded mode badge (blue **PAPER** / green **LIVE**) so the active account is always visible.

### Changed
- **`traderlib/paper_state.py`** — `PaperState.__init__` accepts `data_dir` and `mode` parameters for mode-specific file paths. Falls back to module-level globals when not provided (backward compatible).
- **`traderlib/order_manager.py`** — `OrderManager.__init__` accepts optional `data_dir` parameter. Order file renamed from `alpaca_orders.json` to `orders.json`.
- **`scripts/paper_engine_alpaca.py`** — Engine constructs and passes `data/{mode}/` to `PaperState` and `OrderManager`, and `config/{mode}/risk_config.yaml` to `RiskConfigManager`.

### Fixed
- **`traderlib/paper_state.py`** — Removed stale `DATA_DIR` reference in `_log_trade` metadata.
- **`config/risk_config.yaml`** — Removed (migrated to `config/paper/risk_config.yaml`).


## [0.6.15.33] — 2026-05-02 — Fix 20 Test Failures, Stabilize CI

### Fixed
- **`traderlib/economic_calendar.py`** — `EconomicEvent.country` field now defaults to `'US'`, fixing 13 test failures where tests constructed events without specifying a country.
- **`traderlib/pivot_detection.py`** — `detect_range_20d_pivot()` now computes `target_price` (2× range risk) instead of leaving it `None`, fixing `TypeError` in pivot comparison tests.
- **`scripts/paper_engine_alpaca.py`** — `_sync_with_alpaca()` initializes `r_mult = 2.0` before the watchlist-lookup try block, fixing `UnboundLocalError` when no watchlist stop is found. This also fixed 3 downstream position-sync test failures.
- **`scripts/watchlist_manager.py`** — Test assertion updated to match actual `[WARN]` prefix output when `NO_COLOR` is set.
- **`tests/test_alpaca_integration.py`** — `MockAlpacaClient` now generates UUID order IDs instead of `test-order-N`, fixing stale-order cleanup conflict in `check_order_status`. Test isolation improved by clearing persisted orders between tests.
- **`tests/test_paper_engine_alpaca_additional.py`** — Added `metadata = {}` to exit-signal mock, fixing `'Mock' object is not subscriptable` error.


## [0.6.15.32] — 2026-05-01 — Fix Dashboard DIST and avg_r Accuracy

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `_print_status()` now passes `initial_stop_price` to dashboard positions dict, fixing DIST column showing 0% for all positions.
- **`traderlib/dashboard.py`** — `_positions()` risk_per_share calculation now falls back to current stop when `initial_stop_price` is unavailable.
- **`traderlib/paper_state.py`** — `_log_trade()` now records `initial_stop_price` and `initial_risk` (dollar amount risked at entry) in EXIT trade log records.
- **`scripts/paper_engine_alpaca.py`** — `_get_today_trade_stats()` R-multiple calculation now uses actual initial risk from trade log instead of broken proxy (`abs(entry - exit) * 1.5`), fixing wildly inaccurate avg_r display.

## [0.6.15.31] — 2026-05-01 — Fix Dashboard Auto-Restart After Market Close

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Dashboard now recreates after each engine shutdown instead of reusing the same disabled object. `engine.run()` calls `dashboard.stop()` at market close which permanently sets `enabled=False`. A fresh `Dashboard()` is constructed after `run()` returns so the next day's engine starts with a live TUI instead of falling back to plain text mode.
- **`scripts/entry_signals.py`** — Stop labeling improved: shows `Entry Stop` with distance-to-pivot annotation, `Risk from Current`, `Raw ATR` with percentage-below-current, and `Raw MA` with percentage-below-current. Disambiguates the intermediate ATR/MA values from the final entry stop.

## [0.6.15.30] — 2026-04-30 — Fix Dashboard: Initial Stop for Risk Calculations

### Fixed
- **`traderlib/dashboard.py`** — `_heat_gauge()` now uses `initial_stop_price` with fallback to `stop_price` for portfolio heat calculation. Heat gauge correctly reflects entry-time risk, not current trailing stop level.
- **`traderlib/dashboard.py`** — `_today_summary()` shows a placeholder line (`"no closed trades yet"`) instead of disappearing entirely when no stats or closed trades exist.
- **`traderlib/dashboard.py`** — `avg_r` display clamped to [-10, +10] range to prevent extreme outlier values from breaking layout.
- **`traderlib/dashboard.py`** — `_heat_gauge()` returns 100% filled bar when equity <= 0, making zero/negative equity visually alarming instead of silently blank.

## [0.6.15.29] — 2026-04-30 — Fix PaperState: Live Equity, Loss Limits, Persistence Order

### Fixed
- **`traderlib/paper_state.py`** — `get_equity()` now accepts optional `current_prices` dict and computes equity = cash + market value when prices are available, instead of cash + cost basis. Falls back to entry prices when no live prices provided (backward compatible).
- **`traderlib/paper_state.py`** — `can_enter_position()` daily loss limit now uses current equity instead of frozen `initial_capital`. Grows/shrinks with the account instead of staying at startup baseline.
- **`traderlib/paper_state.py`** — Fallback `max_position_pct` corrected from 20% to 5%, matching `risk_config.py` default.
- **`traderlib/paper_state.py`** — `from_dict`: target price uses `entry_min_r` instead of hardcoded 2R. `initial_risk` uses `initial_stop_price` instead of current (trailed) stop. Legacy `initial_stop_price` derived from target/entry_min_r when possible.
- **`traderlib/paper_state.py`** — `close_position()` now persists state AFTER removing position from memory (log before delete, save after delete). Crash during save can't leave cash inflated with no position.
- **`traderlib/paper_state.py`** — `DEFAULT_DATA_DIR` uses `Path.home()` instead of hardcoded user path.
- **`traderlib/paper_state.py`** — `get_stats()` uses current equity for `day_return_pct` instead of `initial_capital`.
- **`traderlib/paper_state.py`** — `_is_test_trade()` removed ticker/price heuristics (AAPL@$150, MSFT/GOOGL). Only checks `test_mode` flag and `validation_failed` metadata.
- **`scripts/paper_engine_alpaca.py`** — Added `_get_current_prices_map()` helper. All PaperState method calls now pass WebSocket price cache for live equity.

## [0.6.15.28] — 2026-04-30 — Exit Engine Uses Alpaca Bars, Not yfinance

### Fixed
- **`scripts/paper_engine_alpaca.py`** — `evaluate_exit` calls now pass Alpaca historical daily bars as `historical_data` instead of letting the exit engine fall back to yfinance. EMA10/EMA21 trailing stop calculations during live trading use real-time Alpaca data instead of 15-minute-delayed yfinance data.
- **`scripts/paper_engine_alpaca.py`** — Added `_get_historical_for_exits()` helper that fetches daily bars from Alpaca via `get_bars()` and caches them per ticker for the session lifetime. Daily bars don't change intraday, so one fetch per ticker suffices.
- **`traderlib/paper_exits.py`** — yfinance fallback path in `_get_ema_values` is now only hit by standalone scripts (reports, tools) — never by the live paper engine.

## [0.6.15.27] — 2026-04-30 — Fix Paper Exits Audit: 10 Logic & Hardcoded Value Issues

### Fixed
- **`traderlib/paper_exits.py`** — Flattened `elif` chain to independent `if`-blocks in `evaluate_exit` and `evaluate_exit_action`. Lower-tier trailing stops (EMA10, breakeven) now still apply when higher-tier EMA hasn't caught up (e.g., at +3R with ema21 below current stop, EMA10 still fires).
- **`traderlib/paper_exits.py`** — Fixed cache age check from `.seconds` to `.total_seconds()` in `_get_cached_data`. Previously wrapped at 86400, making caches older than 1 day appear fresh.
- **`traderlib/paper_exits.py`** — `evaluate_exit` now delegates to `TrailingExitEngine` when trailing/hybrid mode is active, matching `evaluate_exit_action` behavior. Both methods return consistent decisions for the same position.
- **`traderlib/paper_exits.py`** — Exit profit-target check now uses `position.entry_min_r` (stored at entry time) instead of live config `min_r_multiple`. Entry/exit parity: a position entered at 3R target won't exit prematurely at 2R.
- **`traderlib/paper_exits.py`** — Removed `max(shares, 10)` floor from fallback `calculate_position_size`. Now returns 0 for rejected sizes, consistent with the main triple-constraint path.
- **`traderlib/paper_exits.py`** — Per-ticker cache timestamps (`cache_timestamps` dict) replace single global `cache_timestamp`. Fetching AAPL no longer resets the TTL clock for TSLA.
- **`traderlib/paper_exits.py`** — `get_position_summary` now uses `initial_stop_price` (immutable) instead of `position.stop_price` (current, possibly trailed) for R-multiple calculation.
- **`traderlib/paper_exits.py`** — Removed position mutation from `evaluate_exit_action`. Scale-out info is now returned in ExitAction metadata; the caller applies mutations.
- **`traderlib/paper_exits.py`** — `_get_cached_data` minimum bars check now uses `ema_long_period` (configurable, default 21) instead of hardcoded 50. Injected data and yfinance paths have consistent validation.
- **`traderlib/paper_exits.py`** — EMA column names are now dynamic (`EMA{period}`) instead of hardcoded `EMA10`/`EMA21`.

### Added
- **`traderlib/paper_state.py`** — `Position` dataclass gains `entry_min_r` field to store the `min_r_multiple` from risk config at entry time.
- **`scripts/paper_engine_alpaca.py`** — `entry_min_r` is now stored on position creation and synced on partial fills. Scale-out handling in `check_exits` and `check_exits_during_stream`.
- **`tests/test_exit_engine.py`** — Updated tests for independent if-block behavior (breakeven/EMA10 fallback when higher-tier EMA doesn't apply). Per-ticker cache timestamp tests.

## [0.6.15.26] — 2026-04-30 — Fix Order Manager Hardcoded Values & Logic

### Fixed
- **`traderlib/order_manager.py`** — `_submit_exit_to_alpaca()` now calls `submit_market_order(ticker, shares, 'sell')` instead of `close_position(ticker)`. Partial exits (e.g., hybrid mode scaling out at 3R) now work correctly instead of liquidating the entire position.
- **`traderlib/order_manager.py`** — Hardcoded absolute path replaced with project-root-relative derivation (`Path(__file__).resolve().parent.parent / 'data'`).
- **`traderlib/order_manager.py`** — Added `shares > 0` validation to `submit_entry()`, `submit_stop_entry()`, and `submit_exit()`.
- **`traderlib/order_manager.py`** — Added `pivot_type` and `entry_mode` optional params to `submit_entry()`. Market entries now track technique/entry-mode telemetry the same as stop entries.
- **`tests/test_order_manager.py`** — Updated `test_submit_exit_direct_calls_alpaca` to assert `submit_market_order` instead of `close_position`.

## [0.6.15.25] — 2026-04-30 — Fix Target Price R-Multiple Math

### Fixed
- **`traderlib/pivot_detection.py`** — `detect_range_20d_pivot()` no longer sets a `target_price`. The 20-day range width was used as "risk" to compute the target even when the engine rejected that stop in favor of a tighter ATR/MA stop, producing wildly inflated targets (e.g., 8R+ instead of 2R). Target is now computed in `ticker_analyzer.py` from the actual risk per share using `min_r_multiple` from the risk config.
- **`scripts/paper_engine_alpaca.py`** — Replaced hardcoded `2` in target R-multiple calculations (migration sync, order fill, and position update paths) with `self.risk_config.profit_target.min_r_multiple`. Changing `min_r_multiple` in `config/risk_config.yaml` now propagates consistently everywhere.

### Changed
- **`MEMORY.md`** — Added Roadmap Management section with versioning, plan-linking, and who-why-what-how narrative guidelines.
- **`plans/roadmap-2026.md`** — Revamped format: split Design/Plan columns, added version-anchored decision log, added who-why-what-how narratives for all versions, marked 0.6.15.0 as partially shipped.
- **`docs/superpowers/plans/dashboard-ux-improvements.md`** — Marked P0 and P1 items as shipped.
## [0.6.15.20] — 2026-04-29 — Fix Post-Market State Path

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Post-market dashboard now loads positions when running from `scripts/` directory. Used relative path `data/paper_positions.json` which failed when CWD was `scripts/`. Changed to `Path(__file__).parent.parent / 'data' / 'paper_positions.json'` to resolve from repo root regardless of where the script is launched.

---

## [0.6.15.19] — 2026-04-29 — Post-Market Dashboard Summary

### Added
- **`scripts/paper_engine_alpaca.py`** — Post-market dashboard summary. When market closes, the dashboard now shows a "POST-MARKET SUMMARY" view with the final portfolio state instead of clearing the screen:
  - Engine returns final `state_data` dict to `main()` on graceful exit
  - Dashboard stays alive with preserved equity, positions, P&L, sector exposure
  - Header shows yellow `POST-MARKET SUMMARY` badge
  - User sees how the day ended and can review positions until market reopens

### Changed
- **`traderlib/dashboard.py`** — `_header()` supports `market_status="POST"` rendering with yellow `POST-MARKET SUMMARY` label
- **`scripts/paper_engine_alpaca.py`** — Removed `dashboard.stop()` from engine cleanup; lifecycle managed by `main()` instead

---

## [0.6.15.15] — 2026-04-29 — Economic Calendar TBD Filter + Mobile Layout

### Fixed
- **`scripts/premarket_report.py`** — Filter out events with unknown time (TBD) from economic calendar. FMP returns many events without time stamps; these cluttered the report and provided no actionable value.

### Changed
- **`scripts/premarket_report.py`** — Mobile-responsive CSS for economic calendar table:
  - Horizontal scroll instead of overflow
  - Estimate/Previous columns hidden under 768px
  - Event names truncate with ellipsis at 160px max-width
  - Time column compacted (50px, 0.75rem font)
  - Block headers use tighter padding

---

## [0.6.15.14] — 2026-04-29 — Economic Calendar UX Improvements

### Added
- **`scripts/premarket_report.py`** — Economic calendar HTML output overhaul:
  - **Time block grouping** — Events grouped into Pre-Market, Market Hours, After Hours, and Time TBD sections
  - **Time status indicators** — Past (dimmed), Immediate (yellow highlight, within 2h), Upcoming, Unknown — with inline icons
  - **Smart value formatting** — Auto-adds units: `%` for CPI/PPI/rates, `M` for housing, `K` for claims, `$B` for durable goods/retail
  - **Deduplication** — Removes generic "Press Conference" when "Fed Press Conference" exists, etc.
  - **Known-time fallback** — Maps common events (FOMC, CPI, Nonfarm) to standard ET times when API returns empty time
  - **Tomorrow preview** — Uses formatted time and robust impact detection

### Fixed
- **`scripts/premarket_report.py`** — `_classify_economic_risk` case-sensitivity bug: `e.impact == 'high'` → `e.impact.lower() == 'high'` so FOMC events now correctly trigger red risk badge
- **`scripts/premarket_report.py`** — `fetch_economic_calendar` now fail-open: returns empty events on network/API errors instead of crashing
- **`tests/test_reports.py`** — Updated `TestFetchEconomicCalendar` to mock `EconomicCalendar` instead of deprecated `urllib.request.urlopen`

### Changed
- **`scripts/premarket_report.py`** — Event filtering now includes ALL US events sorted by impact (high→medium→low) then time, instead of only high-impact

---

## [0.6.15.13] — 2026-04-29 — Fix Regime and Sector Dashboard Bugs

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Two dashboard data bugs:
  - **Market regime stuck on "UNKNOWN"** — regime computation code was missing; replaced hardcoded `"UNKNOWN"` with live SPY 50MA/200MA + VIX calculation
  - **All sectors showing "Unknown"** — `positions_data` dict was missing the `"sector"` key; now passes `pos.sector` through to dashboard state

---

## [0.6.15.12] — 2026-04-29 — Fix Graceful Shutdown Signal Handler Leak

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Signal handlers leaked after engine exit, causing Ctrl+C during market-closed wait loop to force-exit via `os._exit(1)` and corrupt the terminal (Rich alternate screen buffer stuck):
  - `_cleanup()` method restores original SIGINT/SIGTERM handlers
  - Called from `run()` before returning and from `main()` after `engine.run()`
  - Prevents phantom "no output" on subsequent engine runs

---

## [0.6.15.12] — 2026-04-29 — Fix Economic Calendar Detection

### Fixed
- **`scripts/premarket_report.py`** — Fixed economic calendar events never appearing. FMP API returns dates with time suffix (`"2026-04-29 01:30:00"`) but the code compared them as `str == date` objects — always `False`. Changed comparison to `str.startswith(isoformat())` to handle both type and format mismatches.

---

## [0.6.15.11] — 2026-04-29 — Dashboard P2 UX Improvements

### Added
- **`traderlib/dashboard.py`** — Four medium-effort UX improvements:
  - **Sector exposure bar chart** — Horizontal bars showing % of equity per GICS sector with position counts
  - **Activity log → scrollable timeline** — Single-column chronological flow with event icons (+ x * - ! ?) and inline P&L
  - **Stats visual hierarchy** — Equity and Day P&L bold/white with up/down arrows; cash, unrealized, open, pending, heat dimmed
  - **Market regime indicator** — BULL/BEAR/NEUTRAL badge in header derived from SPY vs 50MA/200MA + VIX
- **`scripts/paper_engine_alpaca.py`** — Data feeds for new dashboard elements:
  - `sector` field added to `positions_data`
  - SPY 50MA/200MA + VIX regime computation (`BULL`/`BEAR`/`NEUTRAL`)

### Changed
- **`docs/superpowers/plans/dashboard-ux-improvements.md`** — Marked items 6–9 as complete

---

## [0.6.15.10] — 2026-04-29 — Dashboard UX Improvements

### Added
- **`traderlib/dashboard.py`** — Five quick-win UX improvements for the paper engine dashboard:
  - **R-multiple column** in positions table — shows risk-adjusted return per position
  - **Row color bands by R-level** — red (<0R), yellow (0–1R), green (1–2R), bright green (2R+)
  - **At-risk banner** — surfaces tickers within 0.5R of their stop or below entry
  - **Portfolio heat gauge** — 10-char bar showing total at-risk dollars / equity vs 6% max
  - **Today's results summary** — wins/losses, dollar P&L, avg R, win rate
  - **Cooldown visibility** — active re-entry cooldowns shown in footer
- **`scripts/paper_engine_alpaca.py`** — Dashboard data feeds:
  - `_get_active_cooldowns()` — computes remaining cooldown minutes per ticker
  - `_get_today_trade_stats()` — reads trade log for today's win/loss/R stats
  - Both values passed through `state_data` to the dashboard

### Changed
- **`docs/METHODOLOGY.md`** — Aligned with code: 10-point Stage 2 scoring, updated tier thresholds (Tier 1: Stage 2 ≥8, Tier 2: ≥6), hybrid trailing stops, position caps, sector limits, and penalty explanation
- **`README.md`** — Updated Stage 2 description to 10-point, tier thresholds, and risk rules
- **`plans/roadmap-2026.md`** — Added v0.6.17.0 Dashboard UX section, bumped downstream versions

### Fixed
- **`tests/test_dashboard.py`** — Fixed pre-existing test bugs: separator row indexing caused off-by-one errors in row count and cell style assertions

---

# Changelog

All notable changes to this project will be documented in this file.

## [0.6.15.9] — 2026-04-28 — Clean Ctrl+C Shutdown

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Ctrl+C now stops the engine immediately instead of running through remaining entry checks and printing a misleading countdown:
  - `_check_entries()` ticker loop checks `self.running` and breaks mid-scan on shutdown
  - Countdown is skipped entirely when `self.running` is `False`
  - Event loop exception handler is suppressed during WebSocket cleanup to prevent Python 3.14 shielded-future `ConnectionClosedError` traceback

---

## [0.6.15.8] — 2026-04-28 — Rollback VIX Changes

### Changed
- **`scripts/paper_engine_alpaca.py`** — Rolled back VIX changes from v0.6.15.5–v0.6.15.7. VIX display restored to pre-change behavior: dashboard shows `None` (rendered as `--`), fallback path fetches via yfinance. No yfinance calls added to the live dashboard path.

---

## [0.6.15.7] — 2026-04-28 — VIX Data Source Correction (REVERTED in v0.6.15.8)

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Removed yfinance VIX fetch from the live trading path. yfinance has a 15-minute delay and is disallowed for live trading per `CLAUDE.md`. Dashboard now shows `VIX --` honestly; fallback path prints `VIX: unavailable (Alpaca does not provide VIX index)`.

---

## [0.6.15.6] — 2026-04-28 — WebSocket Status Fix

### Fixed
- **`traderlib/alpaca_client.py`** — WebSocket now shows "connected" immediately on engine startup. `last_ws_message` is initialized to `now()` when the connection is established, so `is_ws_healthy()` no longer returns `False` during the first 30-second cycle while waiting for the first trade message.

---

## [0.6.15.5] — 2026-04-28 — Paper Engine Bug Fixes

### Fixed
- **`traderlib/paper_state.py`** — `day_pnl` is now recovered from today's trade log on engine restart. Previously, exiting and relaunching during the same session reset `day_pnl` to 0, hiding today's realized gains/losses.

### Changed
- **`scripts/paper_engine_alpaca.py`** — VIX display changed from hardcoded `None` to honest `--`. (Previous attempt to fetch via yfinance was reverted in v0.6.15.7; yfinance is disallowed in live trading paths per `CLAUDE.md`.)

---

## [0.6.15.4] — 2026-04-28 — Dashboard Shutdown UX

### Fixed
- **`scripts/paper_engine_alpaca.py`** — Shutdown signal now provides immediate visual feedback:
  - Restores normal terminal screen before printing shutdown message (no more invisible text trapped under `rich.live.Live` alternate screen buffer)
  - Shows clear two-line confirmation: "🛑 Shutdown signal received. Stopping gracefully..." and "(Press Ctrl+C again to force exit)"
- **`traderlib/dashboard.py`** — Added `stop_now()` method for immediate screen restoration from signal handlers

---

## [0.6.15.3] — 2026-04-28 — Dashboard Column Fix

### Changed
- **`traderlib/dashboard.py`** — Removed `R` column from positions table. Values were meaningless for `BREAKEVEN` positions (denominator was zero, so it showed raw dollar PnL masquerading as an R-multiple) and provided no actionable signal.

---

## [0.6.15.2] — 2026-04-28 — Dashboard Cleanup

### Changed
- **`traderlib/dashboard.py`** — Removed redundant `PHASE` column from positions table. Stop type (`HARD`, `BREAKEVEN`, `TRAIL`) and price already convey the same information; `P1`/`P2` labels added no actionable signal.

---

## [0.6.15.1] — 2026-04-28 — Dashboard Fixes

### Fixed
- **`traderlib/dashboard.py`** — Static clock and countdown:
  - Added background `threading.Thread` timer that re-renders every second
  - Clock (`09:04:19 ET`) ticks live instead of freezing between engine updates
  - `next_scan_seconds` countdown computes from monotonic target time, counts down live
- **`traderlib/dashboard.py`** — Rate limit display accuracy:
  - Market-closed state shows `API: --` and `Rate limit: --` instead of fabricated `0/500`
  - Running engine uses actual `10000` limit (paid tier config) instead of hardcoded `500`
- **`scripts/watchlist_manager.py`** — Added `sys.path.insert()` so `traderlib` imports work when spawned as subprocess from `mcstock_scraper.py --populate-watchlist`
- **`traderlib/dashboard.py`** — Restored missing `market_color`, `vix_color`, `ws_color` variables in `_header()` after rate limit fix

### Chore
- **`scripts/mcstock_scraper.py`** — Merged historical scraper into unified script with `--mode single` / `--mode historical`
- **`scripts/mcstock_historical_scraper.py`** — Removed (functionality merged)
- **`CLAUDE.md`** — Updated MC Stock Charts commands to unified `--mode` syntax

---

## [0.6.15.0] — 2026-04-27 — TUI Dashboard for Paper Engine

### Added
- **`traderlib/dashboard.py`** — Live TUI dashboard using `rich`:
  - Full-width, single-screen display with `rich.live.Live` screen mode
  - Header band with timestamp, market status (color-coded), VIX, WebSocket status, API usage
  - Stats block with equity, cash, day P&L, unrealized P&L, open positions, pending orders
  - Positions table with color-coded current price, unrealized P&L, and R-multiple
  - Activity log showing last 8 events in 2 columns (entries, exits, stops, skips)
  - Footer band with next scan countdown, market close countdown, connection status, rate limit
  - Color coding: green for profit/connected, red for loss/disconnected, yellow for warnings, cyan for entries
- **`tests/test_dashboard.py`** — Dashboard unit tests:
  - Initialization and render tests
  - Stats and positions display verification
  - Color coding validation (green/red for profit/loss)
  - Activity log with events
  - Disabled mode and fallback without `rich` tests
- **`scripts/demo_dashboard.py`** — Standalone demo script for dashboard rendering validation

### Changed
- **`scripts/paper_engine_alpaca.py`** — Replaced scrolling `print()` output with live dashboard:
  - `_print_status()` now builds state dict and updates dashboard
  - Event logging calls `dashboard.log_event()` with structured event data
  - Plain-text fallback preserved when `rich` is unavailable or terminal is non-TTY
  - Dashboard init wrapped in `try/except` to prevent engine crash on startup
- **`TOOLS.md`** — Added "Paper Engine Dashboard" section documenting sections, color coding, and fallback mode
- **`pyproject.toml`** — Added `rich>=13.0.0` dependency

### Technical
- Defensive import pattern: dashboard degrades to no-op if `rich` is not installed
- TTY detection: auto-disables screen mode when output is piped
- Bounded event queue: `deque(maxlen=20)` prevents memory growth
- `_last_state` caching ensures dashboard renders correctly on event-only updates

---

## [0.6.14.1] — 2026-04-27 — Remove Redundant Scripts

### Removed
- **`scripts/stage2_rs_screen.py`** — Removed redundant Stage 2 RS screener
  - Functionality overlaps with `entry_signals.py` and `trend_screener.py`
  - Both existing scripts also evaluate Stage 2 criteria
  - CLI: `python3 scripts/trend_screener.py` or `python3 scripts/entry_signals.py`
- **`tests/test_stage2_rs_screen.py`** — Removed associated tests
- **`docs/scripts/stage2_rs_screen.md`** — Removed documentation

### Changed
- **`CLAUDE.md`** — Removed `stage2_rs_screen.py` references
- **`README.md`** — Removed from scans table
- **`TOOLS.md`** — Removed Stage 2 RS Screen section
- **`docs/README.md`** — Removed from documentation index
- **`docs/getting-started.md`** — Replaced command references with alternatives

---

## [0.6.14.0] — 2026-04-27 — FMP Economic Calendar Integration

### Added
- **`traderlib/economic_calendar.py`** — New Financial Modeling Prep (FMP) Economic Calendar integration:
  - `EconomicEvent` dataclass with impact classification (HIGH, MEDIUM, LOW)
  - `EconomicCalendar` class with rate-limited API calls
  - High-impact event detection for market awareness
  - `get_events()` convenience method with date filtering
  - Integration with rate limiter to prevent API throttling
- **`scripts/premarket_report.py`** — Economic calendar section in pre-market report:
  - Shows today's high-impact economic events (Fed decisions, CPI, employment, etc.)
  - Displays event time, country, and volatility impact
  - Warns when major market-moving events are scheduled
- **Impact classification** — Events categorized by market impact:
  - HIGH: Fed decisions, CPI, Non-Farm Payrolls, GDP, FOMC statements
  - MEDIUM: Industrial production, retail sales, housing data
  - LOW: Minor reports with limited market impact

### Technical
- Rate limiting: 300 requests/minute to FMP API
- Circuit breaker: Automatic failover on API errors
- Caching: Event data cached per session
- Exports: `EconomicCalendar` and `EconomicEvent` available from `traderlib`

### Tests
- Initialization and configuration tests
- Rate limiting integration tests
- High-impact event detection tests
- Impact classification validation
- Convenience method tests
- Pre-market report integration verification

## [0.6.13.2] — 2026-04-27 — Paper Engine Test Order Fix

### Fixed
- **`traderlib/order_manager.py`** — Moved test order cleanup BEFORE Alpaca API call to prevent UUID validation errors
  - Stale `test-order` entries with non-UUID format now purged before API validation
  - Prevents engine crash when `process_all_pending()` encounters old test orders
- **`data/alpaca_orders.json`** — Removed stale `test-order` entry causing crashes

## [0.6.13.1] — 2026-04-27 — Backtest Config Tracking Fix

### Fixed
- **`scripts/backtest.py`** — Restored equity curve CSV export that was inadvertently omitted in v0.6.13.0
  - `equity.csv`: Daily equity curve with columns: date, equity
  - Aligns with legacy `to_csv()` behavior that exported both trades and equity

## [0.6.13.0] — 2026-04-27 — Backtest Configuration Tracking

### Added
- **`scripts/backtest.py`** — Auto-save backtest results with self-identifying configuration:
  - Folder format: `YYYY-MM-DD_HHMMSS_MMM_risk_profile_profit_mode_strategy/`
  - Millisecond precision prevents collision on rapid successive runs
  - Folder name includes: risk_profile (conservative/aggressive), profit_mode (target/trailing/hybrid), strategy (stage2/vcp)
  - `trades.csv`: Clean trade data with columns: ticker, entry_date, exit_date, entry_price, exit_price, shares, pnl, r_multiple, exit_reason, pivot_price
  - `config.txt`: Human-readable configuration + results summary including:
    - Risk profile details (risk per trade %, max position %, daily loss limit %)
    - Strategy and profit target mode with scale-out rules
    - Stop loss configuration (ATR multiplier, method)
    - Execution settings (slippage bps, earnings filter status)
    - Backtest parameters (date range, initial capital, max positions)
    - Results (total return %, win rate %, avg R-multiple, Sharpe ratio, trade count)
- **`--no-save` flag** — Skip saving backtest results to disk for quick testing/debugging

### Changed
- Default behavior: backtests now auto-save instead of requiring explicit `--csv` export
- Results directory: `data/backtests/` (auto-created if missing)

## [0.6.12.1] — 2026-04-26 — FMP API Key Security Fix

### Fixed
- **`traderlib/earnings_calendar.py`** — Added `load_dotenv()` to load FMP_API_KEY from `.env` file
  - Previously relied on shell environment variable set in `.zshrc`
  - Now self-contained: loads `.env` automatically when module is imported
  - Fixes `premarket_report.py` and other scripts that import `EarningsCalendar` without loading `.env` first

### Security
- Moved FMP_API_KEY from `.zshrc` to `.env` file (gitignored)
  - Prevents API key from being exposed in shell history
  - Follows same pattern as Alpaca credentials

## [0.6.12.0] — 2026-04-25 — Configurable Trailing Exit System

### Added
- **`traderlib/trailing_exits.py`** — New configurable trailing exit engine supporting three modes:
  - `target` mode: Fixed R-multiple exit (backward compatible, default)
  - `trailing` mode: Dynamic trailing stops with stage-based or continuous bands
  - `hybrid` mode: Scale-out partial positions + trail remainder
  - Configure via `profit_target.mode` and `profit_target.trailing_stages` in `risk_config.yaml`
- **`traderlib/paper_state.py`** — Added `scale_out_history` to Position for tracking executed scale-outs
- **`traderlib/risk_config.py`** — Extended `ProfitTargetConfig` with trailing configuration:
  - `mode`: "target" | "trailing" | "hybrid"
  - `trailing_mode`: "stage_based" | "continuous"
  - `trailing_stages`: List of R-level triggered stages (breakeven, trail_ema)
  - `scale_out_steps`: Hybrid mode partial profit-taking configuration
  - Validation: Increasing stage R-values, non-overlapping bands, total fraction ≤ 1.0
- **`traderlib/paper_exits.py`** — Integrated trailing engine into ExitEngine
- **`config/strategies/example_trailing.yaml`** — Example trailing exit strategy configuration
- **`tests/test_trailing_exits.py`** — 23 engine tests covering all three modes
- **`tests/test_trailing_integration.py`** — 3 integration tests with ExitEngine
- **`tests/test_backtest_trailing.py`** — 2 backtest integration tests

### Fixed
- Scale-out with 0 shares no longer blocks future triggers (minimum shares guard)
- Invalid YAML config now raises SystemExit instead of silently falling back to defaults
- Float precision safety for scale-out deduplication (6 decimal places)

### Documentation
- **`docs/RISK_GUIDE.md`** — Updated trailing stops section with new configurable modes
- **`docs/METHODOLOGY.md`** — Updated exit strategy documentation
- **`TOOLS.md`** — Updated exit engine and profit target descriptions
- **`config/risk_config.yaml`** — Added comprehensive trailing mode documentation with examples
- **`docs/superpowers/specs/2026-04-25-configurable-trailing-exits-design.md`** — Marked unimplemented methods as "Not implemented"

### Code Quality
- **`traderlib/risk_config.py`** — Removed dead `fraction` field from `TrailingStageConfig` (was unused, scale-out uses `ScaleOutStepConfig`)

## [0.6.11.0] — 2026-04-25

### Changed
- **`scripts/entry_signals.py`** — Redesigned console output for improved scannability and information hierarchy:
  - **Clustered columns**: Combined PRICE/PIVOT/STOP/TYPE into single `ENTRY → STOP` column (e.g., `$162.22 → $157.35 ATR`), reducing cognitive load
  - **Inline section counts**: Section headers now show ticker count inline (`🔥 READY NOW  (2)`) with criteria (`score≥60 · dist≤±3%`)
  - **Simplified footer**: Two-line layout with pivot source legend and configuration summary
  - **Removed redundant summary bar**: Section headers now serve dual purpose
  - Total columns reduced from 10→6 for better horizontal scanning

## [0.6.10.5] — 2026-04-25

### Changed
- **`scripts/entry_signals.py`** — Added STOP and TYPE columns to the main entry signals table output. Users can now see the calculated stop price and stop type (ATR, MA, VCP, etc.) directly in the scan results, making it easier to understand which stop is being used when technique-specific stops are overridden by tighter ATR/MA stops.

## [0.6.10.4] — 2026-04-25

### Fixed
- **`traderlib/ticker_analyzer.py`** — When explicit `--pivot-mode` is requested (e.g., `vcp`) but pattern detection fails, the system now warns the user (`⚠️ TICKER: vcp pivot not found, using 20d range fallback`) and displays the requested technique's badge (`[v]`) instead of silently falling back to `[r]` (range20d). This clarifies that VCP was requested but not found, while still using a safe fallback price from the 20-day range.
- **`scripts/entry_signals.py`** — Added `_fallback` variants (`vcp_fallback`, `pocket_pivot_fallback`, `range_20d_fallback`) to `_SOURCE_LABEL` mapping so they display with their original technique's badge (`[v]`, `[p]`, `[r]`).

## [0.6.10.3] — 2026-04-25

### Fixed
- **`traderlib/backtest/report.py`** — Phase 4: Use `pivot_price` for R-multiple calculation in backtest reports. Previously calculated R-multiples from `entry_price (T+1 open) → stop`, which produced tighter R-values than live trading when stocks gapped up. Now calculates from `pivot → stop` when `pivot_price` is available, aligning backtest with live breakout entry logic. Measured impact: avg R-multiple changed from 0.35R to 0.36R (+2.9%) on 2025-05-01 to 2025-12-31 backtest with tight_stops profile — within acceptable threshold.

## [0.6.10.2] — 2026-04-25

### Documentation
- **`TOOLS.md`** — Removed stale `--ticker` CLI flag documentation from Entry Signals section. Added `--watchlist`, `--universe`, `--use-universe`, and `--pivot-mode` flags to the CLI options table. Documented `--top N` flag for Sector Scan (was incorrectly listed as "No CLI options"). Added `max_vix` to the Risk Config market section.
- **Deleted `TODOS.md`** — File no longer maintained; task tracking moved to issue tracker and project memory.

## [0.6.10.1] — 2026-04-25

### Fixed
- **`scripts/entry_signals.py`** — Fixed single-ticker deep dive returning no analysis when history had fewer than 200 bars. Root cause: `analyze_single()` explicitly requested `days=252` (calendar days ≈ ~180 trading days), but `rolling(200)` needs 200 trading days. Fixed by removing the explicit `days=252` parameter so it uses the default 365 calendar days (~250 trading days), matching `TickerAnalyzer.analyze()`.
- **`scripts/entry_signals.py`** — Removed redundant `--ticker` CLI flag. `--tickers` now handles both single-ticker deep dive (1 ticker → `analyze_single`) and multi-ticker scan (2+ tickers → summary table).
- **`traderlib/ticker_analyzer.py`** — Fixed ATR stop calculation anchoring to `current` price instead of `pivot` on breakout setups, which caused stop-loss to appear above the entry price. Added `stop_anchor = pivot if pivot < current else current` for stop/bounds computation, with hard guard forcing stop below pivot when needed. Risk and target calculations remain anchored to `current` for correct position sizing.

### Changed
- **`scripts/entry_signals.py`** — Removed `--ticker` argument. Updated epilog examples to show `--tickers` usage.

## [0.6.10.0] — 2026-04-25

### Changed
- **`scripts/sector_scan_comprehensive.py`** — Added `--top N` CLI flag to control how many top-ranked ETFs are printed to the console (default: 15). The CSV output still contains the full universe.
- Consolidated redundant `sector_scan.py` functionality into `sector_scan_comprehensive.py`; the simple scan is now superseded by the comprehensive scan with filtering.

### Documentation
- **`README.md`** — Updated scripts table: removed deleted `sector_scan.py`, added `sector_scan_comprehensive.py`, `show_positions.py`, `clean_test_trades.py`, `sync_state.py`. Re-labeled AGENTS.MD as "AI assistant instructions."
- **`docs/README.md`** — Added new script documentation links, new core docs (TESTING.md, DEPLOYMENT.md, CONTRIBUTING.md), fixed AGENTS.MD description.
- **`AGENTS.MD`** — Added header clarifying purpose as AI assistant instructions.
- **`TOOLS.md`** — Added header clarifying internal developer notes.
- **New `docs/scripts/` directory** — 7 script guides:
  - `sector_scan.md` — Comprehensive ETF scan with `--top` flag
  - `show_positions.md` — Position viewer
  - `utility_scripts.md` — Doctor, setup, validate, sync, cleanup
  - `watchlist_manager.md` — Watchlist operations
  - `stage2_rs_screen.md` — RS screen usage
  - `mcstock_scraper.md` — MC Stock scrapers
  - `paper_portfolio.md` — Paper portfolio CLI
- **New core docs:**
  - `docs/TESTING.md` — Test suite guide (running, writing, mocks, coverage)
  - `CONTRIBUTING.md` — PR process, commit format, code style, versioning
  - `docs/DEPLOYMENT.md` — Production deployment, cron jobs, systemd, monitoring

## [0.6.9.3] — 2026-04-25

### Fixed
- **`tests/test_alpaca_client_extended.py`** — Patched `rate_limiter.max_requests = 200` in all `setUp` methods so rate-limit tests work against the paid-tier default (10000/min). Changed `test_get_order_failure` to raise `ConnectionError` (matches actual `get_order` exception contract).
- **`tests/test_backtest_execution.py`** — Rewrote to match actual `ExecutionConfig` (only `slippage_bps: float = 5.0`) and `FillResult` (no commission field). Removed all commission-related assertions.
- **`tests/test_backtest_strategy.py`** — Updated to use unified `BacktestStrategyContext` for `evaluate_entries()` and `manage_exits()`. Changed `ExitDecision` to `ExitAction` with required `action=ExitActionType.EXIT`.
- **`tests/test_backtest_stop_calc.py`** — Updated all `evaluate_entries()` calls to use `BacktestStrategyContext` via helper.
- **`tests/test_backtest_engine.py`** — Excluded `engine_module` from `test_no_yfinance_in_backtest` since the engine intentionally imports yfinance for VIX prefetch (fails open).
- **`tests/test_rate_limiter.py`** — Updated expected `max_requests` from 200 to 10000 to match paid-tier default.
- **`tests/test_vcp_pattern_detection.py`** — Fixed `test_invalid_wide_progression` ratio from 80% to 88% so it clearly exceeds the 0.80 threshold.
- **`tests/test_watchlist_manager.py`** — Updated expected print string to include emoji (`📭 Watchlist is empty`).
- **`tests/test_paper_portfolio.py`** — Fixed AlpacaClient patch path from `'paper_portfolio.AlpacaClient'` to `'traderlib.alpaca_client.AlpacaClient'`.
- **`tests/test_chaos.py`** — Fixed indentation bug that caused `AlpacaClient` patch context to exit before `assertRaises(RuntimeError)` block.
- **`tests/test_integration_paper_engine.py`** — Removed call to deleted `_refresh_spy_cache()` method in `test_spy_cache_removed`.
- **`tests/test_paper_engine_integration.py`** — Kept `_check_market_hours_for_trading` and `_check_cooldown` patches active for entire tests via `self.enterContext`. Added `self.engine.running = True` before `_check_exits()` in the full-workflow test.
- **`tests/test_paper_engine_alpaca_additional.py`** — Restructured `engine` fixture so init-only patches are restored after `__init__`, while `_check_market_hours_for_trading` / `_check_cooldown` mocks persist as instance attributes.
- **`tests/test_paper_engine_extended.py`** — Added instance-level mocks for `_check_market_hours_for_trading` and `_check_cooldown` in `TestPaperEngineExecuteEntry.setUp`.

## [0.6.9.2] — 2026-04-24

### Changed
- Removed 21 redundant `sys.path.insert(0, ...)` lines from 20 test files. `tests/conftest.py` already adds project root, `scripts/`, and `traderlib/` to `sys.path` centrally.
- Verified `tests/generate_fixtures.py` produces offline fixtures (AAPL, SPY, synthetic stocks) in `tests/fixtures/`.

## [0.6.9.1] — 2026-04-24

### Added
- `tests/test_earnings_calendar.py` — 35 tests covering `EarningsCalendar` init, `_prev_trading_day`, cache hit/miss, blackout detection, force-exit logic, prefetch, invalidate, and rate limiting.
- `tests/test_earnings_provider.py` — 39 tests covering `HistoricalEarningsProvider` cache round-trip, disk TTL, prefetch, `get_next_earnings`, blackout/force-exit with trading-day awareness, and rate limiting.
- `tests/test_universe_builder.py` — 23 tests covering `UniverseBuilder` config loading, cache logic, ETF detection, marginable filtering, and full pipeline build.
- `tests/test_strategy_config.py` — 12 tests covering `load_strategy_config` and `get_param` nested traversal.
- `tests/test_doctor.py` — 26 tests covering `scripts/doctor.py` Python version checks, dependency checks, Alpaca credentials, directory existence, watchlist validation, Telegram config, and git hooks.
- `tests/test_reports.py` — 35 tests covering retry decorator, Telegram reporter, file validation, config loading, earnings badge formatting, gap detection, and HTML report generation.
- `tests/test_backtest_cli.py` — 11 tests covering `scripts/backtest.py` argparse behavior, dry-run path, invalid strategy handling, watchlist resolution, and date parsing.

### Fixed
- `scripts/backtest.py` — Moved `argparse.ArgumentParser` to module level so CLI tests can import it. Removed nested `import sys` inside `main()` that caused `UnboundLocalError` when `sys.exit()` was called before the local import.

## [0.6.9.0] — 2026-04-24

### Added
- **`traderlib/alpaca_client.py`** — Added `submit_stop_order()` and `submit_limit_order()` methods for Alpaca SDK buy-stop and limit order support. Includes rate limiting, auth error handling, and health monitoring.
- **`traderlib/alpaca_client.py`** — Added SDK capability guards `STOP_ORDER_AVAILABLE` and `LIMIT_ORDER_AVAILABLE` for graceful fallback on older SDK versions.
- **`traderlib/order_manager.py`** — Added telemetry fields to `Order` and `QueuedOrder` dataclasses: `pivot_type`, `entry_mode`, `trigger_price`.
- **`traderlib/order_manager.py`** — Added `submit_stop_entry()` for buy-stop (breakout) orders, `cancel_stop_entry()` for cancelling resting breakout orders, and `_submit_stop_entry_to_alpaca()` internal handler.
- **`tests/test_order_manager_stop.py`** — Comprehensive test coverage for stop-entry submission, queueing, cancellation, telemetry serialization, and AlpacaClient stop/limit order methods.

## [0.6.8.4] — 2026-04-24

### Fixed
- **`traderlib/ticker_analyzer.py`** — Removed redundant `pivot_source` field from `TickerAnalysis` dataclass; `pivot_type` already carries the same information. Updated `entry_signals.py` and all tests to use `pivot_type` exclusively.
- **`traderlib/ticker_analyzer.py`** — Changed `atr_risk_pct` sentinel from `999.0` to `Optional[float] = None`. Changed `ma_risk_pct` computation to return `None` instead of `999.0` when stop is not below current. Added formatting guards in `entry_signals.py` to display "N/A" when risk values are `None`.
- **`tests/test_paper_engine_extended.py`** — Added `rate_limiter.get_status` mock to `create_engine_with_mocks`, fixing `TypeError: '>' not supported between instances of 'MagicMock' and 'int'` in `_print_status`.
- **`tests/test_paper_engine_alpaca_additional.py`** — Removed `TestSPYCache` class and `spy_cache` assertions since `_refresh_spy_cache()` was deleted. Fixed `test_get_account_value_fallback` to expect `RuntimeError` instead of silent `$100,000` fallback.
- **`tests/test_paper_engine_integration.py`** — Removed all `_refresh_spy_cache` mock references.
- **`tests/test_paper_engine_extended.py`** — Removed references to deleted `TestPaperEngineSPYCache` and `TestPaperEngineEntryFilters` from `run_tests()` suite loader.

## [0.6.8.3] — 2026-04-24

### Fixed
- **`traderlib/ticker_analyzer.py`** — `risk_pct` now reflects the actual stop after `recent_low` override, not the raw ATR stop. Previously a tighter `recent_low` stop was used for stop placement but the looser ATR risk was passed to scoring, causing tickers to be downgraded incorrectly.
- **`traderlib/ticker_analyzer.py`** — SPY return failure now prints a visible warning (`⚠️ SPY return unavailable`) instead of silently returning `0.0` and corrupting all RS calculations.
- **`traderlib/ticker_analyzer.py`** — VIX fetch failure now prints a visible warning (`⚠️ VIX fetch failed — volatility gate OPEN`) so users know the gate is bypassed.
- **`traderlib/ticker_analyzer.py`** — ATR calculation failure now prints a visible warning and logs the exception before falling back to the 2% heuristic.
- **`scripts/paper_engine_alpaca.py`** — `_get_account_value()` no longer silently falls back to hardcoded `$100,000`. If the Alpaca account fetch fails, the engine now logs the error and raises `RuntimeError`, preventing phantom-equity position sizing.

## [0.6.8.2] — 2026-04-24

### Fixed
- **`traderlib/validation.py`** — Removed 24 confirmed real ticker symbols from `TICKER_FALSE_POSITIVES` that were incorrectly blocked as common words: `A`, `AN`, `AS`, `BE`, `BY`, `DO`, `GO`, `HE`, `IN`, `IT`, `ON`, `OR`, `SO`, `ALL`, `NOW`, `OIL`, `ONE`, `OUT`, `RUN`, `SEE`, `ARE`, `LIVE`, `NEXT`, `REAL`.

### Added
- **`tests/test_validation.py`** — `test_previously_blocked_real_tickers_now_valid` covering all 24 restored tickers.

## [0.6.8.1] — 2026-04-23

### Fixed
- **`traderlib/pivot_detection.py`** — Pocket pivot bounds bug: `range(i - 10, i)` could access `closes[-1]` via negative index when `j=0`. Changed to `range(max(1, i - 10), i)`.
- **`traderlib/ticker_analyzer.py`** — Technique-specific stop override referenced `min_stop` before it was defined. Moved sanity-check bounds computation before the override block and added `tech_stop <= max_stop` guard.
- **`scripts/paper_engine_alpaca.py`** — `_refresh_spy_cache()` now uses Eastern timezone for cache key, matching `TickerAnalyzer._get_spy_return_6m()`.

### Added
- **`scripts/entry_signals.py`** — `--pivot-mode` CLI flag (`auto`, `range_20d`, `vcp`, `pocket_pivot`) threaded through `EntrySignalScanner` → `TickerAnalyzer.analyze()`.
- **`tests/test_ticker_analyzer.py`** — `test_analyze_technique_stop_override` verifies that a detected VCP stop replaces the ATR stop when tighter and within bounds.

## [0.6.8.0] — 2026-04-23

### Added
- **`traderlib/pivot_detection.py`** — New unified pivot detection module supporting multiple breakout techniques:
  - `PivotSignal` dataclass with standardized fields: `pivot_price`, `pivot_type`, `confidence`, `stop_price`, `target_price`, `entry_mode`, `context`
  - `detect_range_20d_pivot(hist)` — 20-day range high with confidence based on position within range
  - `detect_vcp_pivot(hist)` — wrapper around existing `detect_vcp_pattern()`, requires valid pattern + declining volume
  - `detect_pocket_pivot(hist)` — up-day with volume spike above max down-volume in prior 10 days
  - `detect_pivot(ticker, hist, technique='auto')` — dispatcher that tries all techniques and returns highest-confidence signal
- **`tests/test_pivot_detection.py`** — New test suite (16 tests) covering all detectors and the dispatcher

### Changed
- **`traderlib/ticker_analyzer.py`** — Integrated automatic pivot detection:
  - `TickerAnalysis` dataclass: removed `hist` field (R0.2), added `pivot_type` and `entry_mode` fields
  - `analyze()` now calls `detect_pivot(ticker, hist, technique='auto')` when no manual watchlist pivot exists
  - Technique-specific stop override: detected signal's `stop_price` replaces ATR/MA stop when tighter (higher) but still valid
  - Entry mode per pivot type: `vcp` → `breakout`, `manual` → `breakout`, `range_20d` → `immediate`, `pocket_pivot` → `immediate`
  - Ultimate fallback to 20-day range high when no technique produces a valid signal
- **`scripts/entry_signals.py`** — Updated `_SOURCE_LABEL` to include `vcp` (`v`) and `pocket_pivot` (`p`) badges

## [0.6.7.0] — 2026-04-23

### Added
- **`traderlib/ticker_analyzer.py`** — New shared `TickerAnalyzer` module extracted from duplicated analysis logic in `entry_signals.py` and `paper_engine_alpaca.py`:
  - `TickerAnalyzer` class with `analyze()`, `check_market_conditions()`, `_get_spy_return_6m()`, `_get_current_price()`
  - `TickerAnalysis` dataclass with `to_dict()` for backward compatibility
  - Combines best of both original implementations: paper engine's `recent_low` support + entry signals' comprehensive field set
  - Standardized analysis output used by both entry scanner and paper trading engine

### Changed
- **`scripts/entry_signals.py`** — Refactored to use `TickerAnalyzer`:
  - Removed duplicated `_get_spy_return_6m`, `_get_current_price`, `_check_market_conditions`, `_analyze_ticker`
  - `scan()` and `analyze_single()` now delegate to `self.analyzer`
- **`scripts/paper_engine_alpaca.py`** — Refactored to use `TickerAnalyzer`:
  - Removed duplicated `_get_spy_return_6m`, `_check_market_conditions`, `_analyze_ticker`
  - Kept engine-specific `_get_current_price` (exit logic) and `_refresh_spy_cache` (main loop logging)
  - `_check_entries()` delegates analysis to `self.analyzer.analyze()`
- **Tests updated** — `test_entry_signals.py`, `test_paper_engine_coverage.py`, `test_paper_engine_alpaca_additional.py`, `test_paper_engine_extended.py`, `test_paper_engine_new_coverage.py`, `test_integration_paper_engine.py`, `test_chaos.py` all updated to reference `analyzer` methods instead of removed engine methods
- **`tests/test_ticker_analyzer.py`** — New test suite (15 tests) covering `_get_spy_return_6m`, `_get_current_price`, `check_market_conditions`, and `analyze`

## [0.6.6.11] — 2026-04-20

### Changed
- **Postmarket report UX** — Removed "⚡ Key Levels for Tomorrow" section from both HTML and console output. The section displayed index support/resistance levels from daily highs/lows, but these short-term levels had limited predictive value for the next trading session.

## [0.6.6.10] — 2026-04-20

### Fixed
- **Postmarket report tier calculation** — `analyze_watchlist_performance()` now uses the same comprehensive `get_entry_score()` function as the premarket report:
  - Previously used simplified logic: `tier = '1' if stage >= 6 else '2' if stage >= 4 else '3'` based only on watchlist CSV Stage field
  - Now calculates full entry score using: Stage 2 score, risk %, distance to pivot, 6M return, and MA penalties (below 50MA/20MA)
  - Fixed tier mismatch: postmarket was showing all watchlist stocks as Tier 3 (red), now correctly shows 14 Tier 1 / 1 Tier 2 matching premarket report

## [0.6.6.9] — 2026-04-20

### Added
- **Earnings data integration in premarket report** — Full integration of FMP earnings calendar data into daily premarket briefings:
  - **Earnings Calendar section** — New report section (after Economic Calendar) showing watchlist tickers with earnings TODAY and tickers requiring force exit (earnings tomorrow)
  - **Earnings column in Watchlist Analysis** — Added "Earnings" column to the watchlist table displaying proximity badges:
    - `⛔ today` — reporting today (entry blackout)
    - `🚨 1d` — reporting tomorrow (force exit today)
    - `⚠️ {days}d` — 2-7 days until earnings
    - `📅 {days}d` — 8-30 days until earnings
    - `—` — no earnings within 30 days
  - **Earnings action items** — Dynamic checklist entries showing counts of tickers reporting today, positions requiring exit, and tickers with earnings in next 7 days
  - Uses existing `EarningsCalendar` infrastructure with same fail-open behavior (gracefully skips if FMP_API_KEY not set)

## [0.6.6.8] — 2026-04-20

### Changed
- **Premarket report UX** — Removed the "Key Levels" section from both HTML and console output. The section displayed SPY/QQQ 50MA reclaim levels and VIX current price, but provided limited actionable value compared to the full Regime Assessment and Indices tables above it.

## [0.6.6.7] — 2026-04-20

### Added
- **VIX regime status in paper engine** — `_print_status()` now displays real-time VIX level with regime indicator:
  - 🟢 LOW (< 20), 🟡 ELEVATED (20-30), 🟠 HIGH (30-40), 🔴 EXTREME (> 40)
- **Earnings gate status in paper engine** — Each status refresh now shows:
  - `🚦 Earnings Gate: ON (N tickers cached)` when FMP_API_KEY is set
  - `🚦 Earnings Gate: OFF (FMP_API_KEY not set)` when disabled

## [0.6.6.6] — 2026-04-20

### Fixed
- **Graceful shutdown improvement** — Added `if not self.running: return` checks at the start of `_check_entries()` and `_check_exits()` in `scripts/paper_engine_alpaca.py`. Previously, pressing Ctrl+C during market hours would allow the full entry/exit scan to complete before shutting down. Now shutdown is immediate. Double Ctrl+C still force-exits via `os._exit(1)`.

## [0.6.6.5] — 2026-04-20

### Added
- **Sector scan automation** — Scheduled daily sector scan at 7:50 AM ET (weekdays) to ensure `scans/YYYY-MM-DD_sector_scan.csv` exists before premarket report generation. Prevents "no sector scan data found" warnings in premarket reports.

## [0.6.6.4] — 2026-04-20

### Fixed
- **High-octane universe pollution** — Added `max_dollar_volume: 150000000` to `high_octane` profile in `config/screener_config.yaml`. Universe builder now enforces upper bound on dollar volume, excluding large-cap stocks (DIS, AMD, NVDA) that were incorrectly appearing in high-octane universe. Universe size reduced from ~2,100 to ~1,300 tickers.
- **Premarket report missing import** — Added `from traderlib.stage2_utils import calculate_ma_support_stop` to `scripts/premarket_report.py`. Fixes runtime warning where MA support stop calculation was silently skipped for all watchlist tickers.

## [0.6.6.3] — 2026-04-20

### Added
- **VIX status message in backtest** — `BacktestEngine` now prints VIX gating status at startup:
  - `📈 VIX gating ON — max 35 (N days cached)` when `max_vix` is configured
  - `ℹ️ VIX gating OFF — max_vix not set in risk_config` when not configured

## [0.6.6.2] — 2026-04-19

### Added
- **Earnings filter status messages** — `BacktestEngine` now prints clear feedback:
  - `📊 Earnings gating ON — N tickers` when filter is active and FMP_API_KEY is set
  - `⚠️ Earnings filter enabled but FMP_API_KEY not set — earnings gating disabled` when key is missing

## [0.6.6.1] — 2026-04-19

### Fixed
- **Backtest earnings filter wiring** — `scripts/backtest.py` now loads `config/backtest_config.yaml` and passes `enable_earnings_filter` to `BacktestConfig`. Previously the config file existed but was never read, so earnings gating was inactive even with `earnings.enable_filter: true`.

## [0.6.6.0] — 2026-04-19

### Added
- **Earnings filtering in backtest** — Historical earnings gating for backtest simulations, matching live/paper trading behavior.
  - New `HistoricalEarningsProvider` class fetches earnings dates from FMP `/stable/earnings` endpoint
  - Disk caching with TTL (default 30 days) to avoid repeated API calls
  - Rate limited to 300 req/min (FMP paid plan)
  - Entry blackout: blocks new entries on earnings day
  - Force exit: exits positions the trading day before earnings (BMC assumption)
  - Fail-open: if FMP unavailable or key missing, trading continues ungated
  - Config via `config/backtest_config.yaml` — opt-in with `earnings.enable_filter: true`

### Changed
- **Strategy interface unified** — `Stage2MomentumStrategy` migrated from legacy interface to unified `StrategyContext` interface.
  - `evaluate_entries()` now accepts `StrategyContext` parameter
  - `evaluate_exits()` renamed to `manage_exits()` with `StrategyContext` signature
  - Removed `_uses_legacy_interface` detection from `BacktestEngine`
  - All strategies now use unified interface (consistent with VCP strategies)

### Files Added
- `traderlib/backtest/earnings_provider.py` — Historical earnings provider with caching
- `config/backtest_config.yaml` — Backtest-specific configuration

## [0.6.5.1] — 2026-04-19

> ⚠️ **AI fabrication notice** — v0.6.4.0 contained a change invented by Claude Sonnet 4.6 with no basis in any recognised trading methodology. The model presented a made-up concept (`range_20d` — 20-day rolling high as a VCP pivot proxy) as a legitimate fix, confidently committed it, and degraded strategy performance by 63% ($45K → $17K P&L). This release reverts that change.

### Fixed
- **Backtest pivot regression (reverted Phase 4)** — `Stage2MomentumStrategy.evaluate_entries()` was using `pivot_20d = hist['High'].tail(20).max()` as a pivot proxy, introduced in Phase 4 (v0.6.4.0). This penalised base-building setups (always below their recent high by definition) and rewarded extended stocks near peaks — the opposite of what the strategy targets. Total P&L dropped from $45K to $17K on identical trade count (172/256 entries changed). Reverted to `pivot = current` / `dist_to_pivot = 0.0` which neutralises proximity scoring in the backtest, since live watchlist pivot data is not available in a historical simulation. Baseline performance restored: 45.44% return, 53.5% win rate, 1.51 profit factor.

## [0.6.5.0] — 2026-04-19

### Fixed
- **Pivot inflation — live scanner** — `entry_signals.py` and `paper_engine_alpaca.py` both defaulted `pivot = current` when no `Pivot_Price` was set in the watchlist, giving every ticker a free +25 proximity score from `get_entry_score`. Both now default to `pivot = None`; `dist_to_pivot = None` flows through the scan and a 999.0 sentinel is passed to `get_entry_score` so proximity points are never awarded without an explicit pivot.
- **Risk % measurement** — ATR/MA risk was computed as distance from pivot to stop (`abs((stop - pivot) / pivot)`), which was wrong when `pivot != current`. Now measured from current price: `abs((current - stop) / current)`.

### Added
- **Pivot source attribution** — `entry_signals.py` now tracks `pivot_source` (`'manual'` / `'vcp_contraction'` / `'none'`) alongside every pivot. The DIST column shows a source badge (`[m]` manual, `[v]` vcp, `[r]` range20d) and displays `—` when no pivot is set. A footer legend explains the badges. `analyze_single()` (`--ticker` mode) displays the source badge or `— (no pivot set)` inline.
- **Strategy plugin exit routing** — `paper_engine_alpaca.py` now routes exits through the strategy plugin when one is loaded (`--strategy vcp_large_cap`). Added `_process_exit_action()` to bridge `ExitAction` → `ExitSignal`. `_check_exits()` follows a clear priority: earnings (always first) → strategy plugin → legacy `ExitEngine`.
- **Exit phase badges in status** — `_print_status()` prints one line per open position with a phase badge (`①` = Phase 1 ratchet, `②` = Phase 2 EMA trail), current price, stop, stop type, and unrealized P&L.
- **`Position.exit_phase` field** — `paper_state.py` adds `exit_phase: str = 'phase1'` to the `Position` dataclass. `update_stop()` accepts an optional `exit_phase` parameter so phase transitions are persisted alongside stop updates.
- **VCP strategy YAML wiring** — `VCPBreakoutBase._load_profile_params()` now uses a three-tier priority: `config/strategies/vcp_{profile}.yaml` (authoritative) → `risk_config.vcp[profile]` (deprecated legacy fallback) → hardcoded defaults. All VCP parameters (`trail_ema_period`, `phase2_trigger_r`, `max_pivot_proximity_pct`, etc.) are now configurable from YAML without code changes.
- **Consolidated VCP `manage_exits()`** — The two-phase exit logic (Phase 1: ratchet to swing lows; Phase 2: EMA trail) is now implemented once in `VCPBreakoutBase.manage_exits()`. `VCPBreakoutLargeCap` and `VCPBreakoutHighOctane` both inherit it; profile-specific behaviour (EMA period, phase2 R threshold) comes from `self.params`. All `ExitAction` objects now carry `metadata={'exit_phase': 'phase1'|'phase2'}`.

### Changed
- **`risk_config.yaml`** — `method: "atr_or_support"` removed from the top-level `stop_loss` block (stop method is now chosen per-strategy in `config/strategies/`). The `vcp:` section now carries a `[DEPRECATED]` notice pointing to the per-strategy YAML files.

## [0.6.4.0] — 2026-04-19

### Fixed
- **Backtest pivot inflation** — `Stage2MomentumStrategy.evaluate_entries()` used `pivot = current` and `dist_to_pivot = 0.0` as defaults, giving every ticker a free +25 proximity score from `get_entry_score` regardless of setup quality. Fixed by computing `pivot_20d = hist['High'].tail(20).max()` (20-day range high, mirroring the live screener's `range_20d` source) and deriving actual distance. Tickers more than 3% below their 20-day high now correctly score 0 proximity points.

### Added
- **Pivot flows into backtest position state** — `EntrySignal.metadata` now carries `{'pivot': pivot_20d}`. `BacktestState.enter_position()` accepts `pivot_price: Optional[float]`; `BacktestPosition` and `TradeRecord` store it. `engine._resolve_pending_fills()` extracts `signal.metadata.get('pivot')` and passes it through.
- **Accurate R-multiple reporting** — `_trade_initial_risk()` helper uses `TradeRecord.initial_stop_price` (actual stop) instead of the hardcoded 7%-of-entry approximation. `avg_r_multiple`, per-trade R in the all-trades table, and top-winners/losers now use real risk. Legacy records with `initial_stop_price == 0.0` fall back to the 7% approximation for backward compatibility.
- **Commission tracking** — `TradeRecord.commissions` field added (default 0.0). `BacktestState.close_position()` accepts `commission` parameter and deducts it from P&L. `BacktestReport.total_commissions` aggregates commissions across all trades.
- **Strategy YAML integration in backtest** — `Stage2MomentumStrategy.__init__()` now loads `config/strategies/stage2_momentum.yaml` via `strategy_config.load_strategy_config()`. ATR period/multiplier, stop bounds, Stage 2 minimum score, and entry score threshold are all driven by the YAML with hardcoded fallbacks.

## [0.6.3.1] — 2026-04-19

### Changed
- **`entry_signals.py` — dashboard UI + earnings visibility** (complete display rewrite)

  **Dashboard layout**
  - Header block: `━━━` border, title left / timestamp right, market status line (SPY%, VIX, mode, ticker count, scan duration). Market-blocked state shows `⛔ Entries paused` in the header instead of a multi-line paragraph.
  - Summary bar immediately below header: counts for every section visible before scrolling (`🔥 3 Ready · ⏳ 2 Near Pivot · ⚠️ 2 Near Earnings · 📊 8 Tier 2 · 📅 2 Blackout · …`).
  - Section dividers: `── 🔥 READY NOW ───────────────────────────────────` style, with fill to terminal width.
  - Unified table columns across **all** sections: `TICKER SCORE S2 DIST RISK% PRICE PIVOT EARNINGS`. Previously TIER 2 and TIER 3 dropped ATR%/MA%/Stop columns; now every section is consistent.
  - Distance column: `+0.4%↑` / `-1.2%↓` (single-char arrow) replacing `+0.4% 📈` (emoji misaligned columns).
  - Stop/ATR/MA% columns collapsed into single `RISK%` (best-stop risk wins).
  - Footer: `═══` border with criteria summary (`score ≥60 · dist ≤±2% · paper · profile: default`).
  - Init messages (`🔌 Initializing…` / `✅ Scanner ready`) removed from stdout.
  - Trailing `Found N entry signal(s)` block removed (summary bar covers this).

  **Earnings UX**
  - `EarningsCalendar.prefetch(tickers)` called once at scan start — eliminates per-ticker FMP HTTP calls during the scan loop.
  - Earnings blackout check moved from `_analyze_ticker()` to the scan loop; blackout tickers are collected and displayed in a dedicated `📅 EARNINGS BLACKOUT (skipped today)` section at the bottom.
  - `EARNINGS` column in every table row: `—` (none/>30d), `📅 Nd` (≤30d), `⚠️ Nd` (≤7d), `🚨 1d`, `⛔ today`.
  - **Near Earnings section**: tickers with earnings in 1–7 days and score ≥ 40 are moved out of their natural section into `⚠️ NEAR EARNINGS (1–7d — hold off on new entries)`. Tickers whose earnings are tomorrow (forced-exit day) get an inline `← paper engine exits today` note.
  - `--ticker` deep dive: `Next Earnings` row added to the metrics table with date + proximity badge.
  - `_export_html`: earnings column added with color-coded badges (red/yellow/gray).
  - `earnings_date` and `earnings_days` fields added to every analysis dict (available in CSV/JSON exports).

## [0.6.3.0] — 2026-04-19

### Changed
- **Alpaca credentials moved from JSON config file to environment variables**
  - `config/secrets/alpaca_config.json` is no longer used. All credential lookup now goes through the `.env` file (loaded by `python-dotenv`) or shell environment.
  - New mode-specific env vars: `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` for paper trading; `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` for live trading. Plain `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` remain supported as a fallback for backward compatibility.
  - `ALPACA_HISTORICAL_DAYS` env var controls historical bar fetch depth (default: 365).
  - `traderlib/alpaca_client.py`: removed `_load_config()`, `_load_config_int()`, `CONFIG_FILE`, `CONFIG_DIR`; key loading is now env-only.
  - `scripts/setup_alpaca.py`: rewritten to write credentials to `.env` instead of JSON. Detects legacy `alpaca_config.json` and offers auto-migration + optional deletion.
  - `scripts/doctor.py`: credential check now inspects env vars and `.env` via `dotenv_values()`; fixed pre-existing bug where it checked the wrong path (`data/config/` instead of `config/secrets/`).
  - `traderlib/trading_exceptions.py`: `APIKeyError` message updated to reflect env-var-only setup.
  - `.env.example`: updated with mode-specific key names and `FMP_API_KEY` for the earnings calendar filter.
  - `tests/test_alpaca_client_extended.py`: config tests rewritten to cover mode-specific vars, fallback to generic vars, priority ordering, and `ALPACA_HISTORICAL_DAYS`; removed JSON file tests.

## [0.6.2.9] — 2026-04-18

### Added
- **Earnings filter — blocks entries and forces exits around earnings events** (live/paper trading)
  - New module `traderlib/earnings_calendar.py`: `EarningsCalendar` class fetches upcoming earnings dates from FMP `/stable/earnings` API. In-memory cache per ticker (one call per session). Rate-limited to 300 calls/min matching FMP paid plan. Fail-open: if FMP is unreachable or `FMP_API_KEY` is unset, all gates are skipped.
  - **Entry blackout**: `is_earnings_blackout(ticker, today)` — returns `True` when today equals the earnings date. Applied in `entry_signals.py` and `paper_engine_alpaca.py` `_analyze_ticker()`: prints `📅 {ticker}: Skipping — earnings today` and skips signal generation.
  - **Force exit**: `should_force_exit(ticker, today)` — returns `True` when today equals the trading day before earnings (all reports treated as BMC/pre-market since FMP stable API does not expose AMC/BMC timing). Applied in `paper_engine_alpaca.py` `_check_exits()` before normal stop/target logic: exits position with reason `EARNINGS_EXIT`.
  - `FMP_API_KEY` loaded from environment variable (not config file). Set in shell profile or `.env` before starting the paper engine or scanner.
  - Backtest path not yet gated (historical earnings data requires a different FMP query pattern; deferred).

## [0.6.2.8] — 2026-04-18

### Added
- **VIX gate — blocks new entries when volatility exceeds `max_vix`** (`config/risk_config.yaml` → `market.max_vix`)
  - `^VIX` spot data fetched via yfinance (Alpaca does not carry the VIX index; ETF proxies VXX/VIXY have only 0.36 level correlation and are unsuitable for threshold gating)
  - **Backtest engine** (`traderlib/backtest/engine.py`): prefetches full-period VIX history at run start, caches by date, and gates Step 4 (entry evaluation) for both legacy (`Stage2MomentumStrategy`) and unified (VCP) strategies. VIX is also injected into `BacktestStrategyContext.vix_current` for strategies that want to reference it directly.
  - **VCP strategies** (`traderlib/strategies/vcp_breakout.py`): `LargeCap` and `HighOctane` both check `context.vix_current` vs `risk_config.market.max_vix` at the top of `evaluate_entries` — covers paper/live execution paths where the engine doesn't gate.
  - **Paper engine** (`scripts/paper_engine_alpaca.py`) and **entry signals** (`scripts/entry_signals.py`): `_check_market_conditions()` fetches live VIX via `yf.Ticker("^VIX").history(period="2d")` and returns early with a human-readable message when above threshold. VIX level is appended to the SPY status string when within limit.
  - Fail-open on all paths: if yfinance is unavailable or VIX fetch fails, trading continues unblocked.
  - `max_vix` defaults to `None` (gate disabled) in `MarketFilterConfig`; opt-in per risk profile in YAML.

## [0.6.2.7] — 2026-04-18

### Fixed
- **VCP exits and stop updates silently no-ops** — `traderlib/strategies/__init__.py` defined its own `ExitActionType` and `ExitAction` classes, duplicating those in `paper_exits`. The backtest engine imports from `paper_exits`; VCP strategies imported from `strategies`. Because Python enum identity is class-bound, `action.action == ExitActionType.UPDATE_STOP` always evaluated `False` across the two class hierarchies — meaning `_apply_exit_actions` never applied any stop updates and never queued any EXIT fills. Every VCP position held to year-end regardless of stop hits. Fix: removed duplicate definitions from `strategies/__init__.py`; the module now re-exports `ExitAction` and `ExitActionType` directly from `paper_exits`, ensuring a single canonical class identity across all callers.

## [0.6.2.6] — 2026-04-18

### Fixed
- **VCP exit logic — three bugs causing all positions to hold until year-end liquidation**
  1. **No stop enforcement** — `manage_exits()` never checked `current <= stop_price` before phase logic. Phase 1 always emitted `HOLD`/`UPDATE_STOP`; Phase 2 only checked inside an `else` branch that was never reached. The engine does not auto-enforce stops; strategy must emit `EXIT`. Added explicit stop check at top of both `manage_exits` loops in `LargeCap` and `HighOctane`.
  2. **`_find_recent_higher_low` returned wrong value** — was `max(Low[-20:])` (highest daily low of last 20 bars), which approaches current price in a rally and produces a stop above entry. Replaced with proper 3-bar swing detector over last 40 bars; returns the highest swing low above `current_stop` and below `current_price × 0.97`, or `None` to hold stop unchanged.
  3. **`_find_last_swing_low` returned minimum of last 10 bars** — deepest recent dip, the opposite of a trailing stop reference. Replaced with 5-bar swing detector over last 60 bars; returns the most recent qualifying swing low, or `None` so Phase 2 falls back to EMA-only trailing.

## [0.6.2.5] — 2026-04-18

### Fixed
- **Backtest prefetch silently drops tickers after #200** — `AlpacaDataProvider` always created `RateLimiter(max_requests=200)` regardless of account tier. With a watchlist > 200 tickers all remaining tickers were marked `rate_limited` and skipped, leaving the simulation with no data for those stocks. `AlpacaClient` already loads the correct limit from `screener_config.yaml` (default 10,000/min for paid tier). Fix: `AlpacaDataProvider` now accepts `max_requests_per_min` param; `backtest.py` reads `alpaca.rate_limiter.max_requests` and passes it through.

## [0.6.2.4] — 2026-04-18

### Fixed
- **VCP strategy generates zero trades in backtest** — two root causes compounding to near-zero joint probability across the five serial entry filters:
  1. **Breakout volume check removed** (`volume_ratio >= 1.4×`) — this is a live-trading "confirm breakout now" filter. In daily-bar backtesting it fires on <15% of bars and combined with the other filters brought the joint probability to ~0. Removed from both `VCPBreakoutLargeCap` and `VCPBreakoutHighOctane`. T+1 fill realism is preserved by the engine; VCP pattern + Stage 2 + convergence score are the quality gatekeepers.
  2. **VCP progression ratio loosened** — `max_size_ratio` in `validate_vcp_progression` changed from `0.70` to `0.80` (band: 40-80% of prior contraction). The strict 70% limit is theoretically ideal but real-world VCPs frequently run 71-80% and are still valid setups.

## [0.6.2.3] — 2026-04-18

### Fixed
- **`AttributeError: 'VCPBreakoutLargeCap' object has no attribute 'evaluate_exits'`** — backtest engine always called the legacy `(sim_date, positions, data_provider, ...)` interface; VCP strategies implement the unified `(context: StrategyContext)` interface
  - Added `_uses_legacy_interface` detection at engine init: presence of `evaluate_exits` method → legacy path (Stage2Momentum), absence → unified path (VCP and future strategies)
  - Added `_build_context()` helper to wrap `DataFrameProvider` into a `BacktestStrategyContext` for unified strategies
  - Both `Stage2MomentumStrategy` and VCP strategies now work in the backtest engine without changes to either strategy

## [0.6.2.2] — 2026-04-18

### Fixed
- **VCP strategies generate zero signals in backtest** — `_get_watchlist_tickers()` was a stub returning `[]`; root cause was that `watchlist_tickers` and `watchlist_df` were never wired through
  - `VCPBreakoutBase.__init__()` now accepts `watchlist_tickers` and `watchlist_df` params
  - `_get_watchlist_tickers()` reads from instance vars; handles `week_start`-aware historical watchlists and plain ticker lists (trend screener output) identically to `Stage2MomentumStrategy`
  - `VCPBreakoutLargeCap` and `VCPBreakoutHighOctane` forward both params to `super()`
  - `backtest.py` `strategy_kwargs` now passes `watchlist_tickers` and `watchlist_df` for all registered strategies

## [0.6.2.1] — 2026-04-18

### Fixed
- **`entry_signals.py` tier thresholds updated for 10-point scale** — Tier 1 now requires `stage2 >= 8` (was 6), Tier 2 requires `stage2 >= 6` (was 5); proportionally equivalent to old 8-point thresholds (75% and 62.5%)
- **`/8` display strings updated to `/10`** — `entry_signals.py` print statements, HTML templates, and `premarket_report.py` watchlist line all showed stale `stage2/8` denominator

## [0.6.2.0] — 2026-04-18

### Changed
- **Stage 2 scoring formalized as 10-point system** — `calculate_stage2_score()` now matches `get_stage2_details()` which already computed 10 criteria; scores of 9–10 in production output were correct all along, docs and code said "8-point" incorrectly
  - Added criterion 4: **Price > 150 MA** (long intermediate trend)
  - Added criterion 7: **Extended MA stacking: 50 > 100 > 150 > 200**
  - `get_entry_score()` thresholds rescaled: ≥9=30pts, ≥8=25pts, ≥7=20pts, ≥6=15pts, ≥5=10pts, ≥4=5pts
  - `min_stage2_score` in config: `large_cap` 5→6, `high_octane` 4→5 (proportional to 10-pt scale)
  - Hardcoded thresholds in `backtest/strategy.py` and `strategies/vcp_breakout.py`: 5→6
  - All docstrings, comments, and test file updated from "8-point" to "10-point"
- **Test suite updated** — `tests/test_stage2_8point.py` rewritten for 10-point system; 46 tests all passing

## [0.6.1.8] — 2026-04-18

### Changed
- **`null` as universal disable for numeric filters** — set any filter to `null` in `screener_config.yaml` to skip it entirely; replaces the `-1` sentinel for `min_convergence_score` and extends the pattern to `min_price_vs_10ma`, `rs_near_high_pct`, `min_stage2_score`, `min_price`
  - Config: `min_convergence_score: null` (both `large_cap` and `high_octane` profiles updated)
  - Python: all filter checks now guard with `if value is not None` — `None` from config or CLI skips the filter
  - CLI `--min-convergence-score` default changed from `-1` to `None`; not passing the flag uses the profile config value
- **Filter breakdown now shows active thresholds** — each rejection line displays the value that caused rejections (e.g. `price vs 10MA (≥6%)`, `RS near high (≤5%)`, `conv score (≥10)`)
- **MA stack labels clarified** — `MA stack (short)` → `MA stack (10>20>50)`, `MA stack (long)` → `MA stack (50>150>200)`
- **Grade C shown by default** — `--hide-grade-c` now defaults to `False`; use `--hide-grade-c` flag to suppress; summary shows `(hidden — rerun with --no-hide-grade-c to show)` when suppressed

## [0.6.1.7] — 2026-04-18

### Fixed
- **`--export-path` now works without `--export`** — format is inferred from file extension (`.csv`, `.json`, `.html`); previously required both flags or the file was silently not written

## [0.6.1.6] — 2026-04-18

### Changed
- **Renamed `config/scraper_config.yaml` → `config/screener_config.yaml`** — name now reflects actual purpose (screener configuration, not scraping)
  - Updated all references across `traderlib/`, `scripts/`, `CLAUDE.md`, `README.md`, `TOOLS.md`, and all `docs/` files

## [0.6.1.5] — 2026-04-18

### Changed
- **Config-driven profiles** — `screener_config.yaml` is now the single source of truth for all profile parameters; no hardcoded values remain in Python
  - Profile YAML blocks now include screener structural filter defaults alongside universe pre-filter thresholds: `stack_short`, `stack_long`, `rs_near_high_pct`, `min_price_vs_10ma`, `min_share_volume`, `min_stage2_score`, `min_convergence_score`
  - `large_cap`: `stack_long=true`, `rs_near_high_pct=5`, `min_price_vs_10ma=6`, `min_share_volume=1M`, `min_stage2_score=5`
  - `high_octane`: `stack_long=false`, `rs_near_high_pct=12`, `min_price_vs_10ma=4`, `min_share_volume=400K`, `min_stage2_score=4`
  - `--profile` now accepts any string — add custom profiles as YAML blocks in `screener_config.yaml` without touching Python
  - CLI flags override config values per-run (e.g. `--rs-near-high 8` overrides the profile's `rs_near_high_pct`)
  - `UniverseBuilder.get_profile_config()` new method — returns full profile dict for a given profile name

## [0.6.1.4] — 2026-04-18

### Changed
- **Trend Screener UX overhaul** — Three buckets of improvements across prefiltering, scanning, and console output

#### Prefiltering
- `large_cap.min_price` raised from $10 → $30 in `config/screener_config.yaml` to align universe pre-filter with screener floor (was wasting API calls on tickers that failed immediately)
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
- **Rate limiter now configurable via `config/screener_config.yaml`**
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
  `config/screener_config.yaml` for min price, market cap, history days, and
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
