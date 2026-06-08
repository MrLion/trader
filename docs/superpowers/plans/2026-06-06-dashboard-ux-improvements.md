# Dashboard UX Improvements — Implementation Plan

**Goal:** Make the paper-engine dashboard adapt to terminal height, add an equity sparkline, a lifetime panel (Sharpe, Max DD, Total Trades), and a closed-trades panel — all driven by data the engine pre-fetches at startup and once per market-day roll. Rename EQUITY→ACCOUNT VALUE in the stats line and surface YTD next to DAY P&L.

**Approach:** Extend the existing visual language of `traderlib/dashboard.py` rather than redesigning it. Match current patterns: header, three-line stats, positions table, activity icons, `─` separators, no borders. New sections only render when terminal height permits.

**Architecture (data flow):**
- The engine pre-fetches Alpaca data at two points: **startup** and **date roll** (the first `_print_status()` call of a new calendar day). No timer, no 60s cache. The data the equity sparkline, the stats line, and the lifetime panel need only changes once per trading day at most, so fetching more often is waste.
- Portfolio history comes from Alpaca's `get_portfolio_history()` for periods `YTD`, `1M`, and `all` with `timeframe="1D"`. Persisted to `data/paper/portfolio_history.json` so post-market state survives restarts. The `profit_loss` and `profit_loss_pct` fields returned by Alpaca are **lists** (one value per period point); the period P&L number is the **last element** of the list (`profit_loss[-1]`). The full `equity` list is what the sparkline and Sharpe/Max DD consume.
- `lifetime_trade_count` is computed by the engine at startup from `data/paper/trades.jsonl` (a single pass counting EXIT events). It is not persisted — on every engine startup it is recomputed from the source of truth (the trade log), so post-market after a restart shows the real count without needing a separate cache.
- `closed_trades_today` is **not** a pre-fetched state-dict field. The post-market closed-trades panel is live data and is read on demand from `data/paper/trades.jsonl` when the dashboard renders `_closed_trades()`. The file is in OS cache after the first read; line-by-line format makes the read O(N) for N trades, which is trivial. This is the only file I/O on the dashboard render path, and it is correct because closed-trades is a live view that changes on every EXIT event.
- Engine writes five new fields into the same `state_data` dict it already passes to `dashboard.update()`: `ytd_pnl`, `ytd_pnl_pct`, `equity_30d` (rename candidate: `equity_1m`, since the source period is `1M`), `equity_all`, `lifetime_trade_count`. The existing `today_stats` sub-dict is unchanged.
- The dashboard's render path does Alpaca-free: no network calls, no Alpaca fetches. The only file I/O is the on-demand trade-log read for the closed-trades panel.
- `StatsCalculator.lifetime_stats(equities)` is a tiny pure function: given the equity array, return `{sharpe, max_dd}`. The dashboard calls it once per render and combines with `lifetime_trade_count` from state to build the lifetime panel.
- Dashboard reads `console.height` at render time and gates optional sections by height tier (24 / 35 / 50 rows).

**Tech Stack:** Python 3.11+, Rich TUI, pytest.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `traderlib/stats_calculator.py` | MODIFY | Single pure method `lifetime_stats(equities)` returning `{sharpe, max_dd}`. No trade-log math, no `today_stats` helper. |
| `traderlib/dashboard.py` | MODIFY | Add height-tiered rendering, max-rows / max-events support, four new section methods, the ACCOUNT VALUE / YTD line, and a slim lifetime panel. |
| `scripts/paper_engine_alpaca.py` | MODIFY | Add one pre-fetch method (or three small ones) that runs at startup and on date roll. Produces six new state-dict fields. Persist portfolio history to disk. Read the cache in `_load_post_market_state()`. |
| `tests/test_stats_calculator.py` | MODIFY | Tests for `lifetime_stats` only. |
| `tests/test_dashboard.py` | MODIFY | Add tests for truncation, height detection, the new sections, and the ACCOUNT VALUE / YTD line. |

---

## Task 1 — Engine: pre-fetch at startup and on date roll

**Who:** Paper engine, in `_print_status()` (market open and post-market) and `_load_post_market_state()`.
**Why:** The dashboard needs YTD P&L, an equity history for the sparkline and Sharpe/Max DD, and a lifetime trade count for sample-size context on the Sharpe number. None of these change during a closed market or within a single trading day. Fetching on a timer is wasted work; fetching at startup and on date roll is enough. Today's closed trades are deliberately *not* part of this pre-fetch — they are read on demand by the dashboard because they change on every EXIT event during market hours.
**What:** The engine owns the lifecycle. It produces five new fields in the existing `state_data` shape (down from six — `closed_trades_today` is no longer in state). The existing `today_stats` sub-dict is unchanged. Post-market loads from disk; the lifetime count is recomputed from the trade log on engine startup.
**How (behavior, not code):**

- Add a method that returns a dict with `ytd_pnl` (float), `ytd_pnl_pct` (float), `equity_30d` (list of floats, source period `1M`), and `equity_all` (list of floats, source period `all`). Internally it calls Alpaca's `get_portfolio_history()` for periods `YTD`, `1M`, and `all` with `timeframe="1D"`. **Critically: `profit_loss` and `profit_loss_pct` on the response are lists, not scalars.** The period P&L number is the **last element** of each list: `ytd.profit_loss[-1]` for YTD P&L, `ytd.profit_loss_pct[-1]` for YTD P&L percent. Handle the empty-list case by defaulting to `0.0`. The full `equity` list is what feeds the sparkline and Sharpe/Max DD.
- Cache invalidation is date-based: store the last-fetch date as a string (`"YYYY-MM-DD"`). On each call, if the date matches `datetime.now().strftime("%Y-%m-%d")`, return the in-memory cache. Otherwise refetch.
- The first call after engine startup is always a fetch (no cache yet). The first call after a date roll is always a fetch.
- On every successful fetch, write the four portfolio fields to `data/paper/portfolio_history.json` (creating the parent dir if needed) so the post-market path can read it after a restart. The `lifetime_trade_count` is **not** in this file — see below.
- Add a separate one-line helper (or inline in the engine constructor) that reads `data/paper/trades.jsonl` once at engine startup and returns `lifetime_trade_count` (count of events with `event == "EXIT"`). The result is stored on the engine instance and added to `state_data` as `lifetime_trade_count` in `_print_status()`. No caching, no persistence — the source of truth is the trade log itself, and startup is the natural time to read it.
- In `_print_status()`, after the existing `state_data` is built, call the Alpaca pre-fetch method (or read its in-memory cache) and add the four portfolio fields. Also add `lifetime_trade_count` from the startup-read helper. Five new fields total. The dashboard receives them as new siblings of the existing keys.
- In `_load_post_market_state()`, read `data/paper/portfolio_history.json` if it exists and populate the four portfolio fields. The `lifetime_trade_count` defaults to `0` here — the post-market path does not re-read the trade log. (Rationale: post-market view is a summary, and a Total Trades of 0 is acceptable as a "fresh install / no data yet" indicator. The next engine startup will repopulate it.)
- Failure handling: if an Alpaca call fails, log to the existing `data/logs/trading_exceptions.log` and return the previous in-memory cache (or the empty defaults if no cache exists). If the startup trade-log read fails, log and use `lifetime_trade_count=0`. Never raise into the render loop.

**Files:**
- Modify: `scripts/paper_engine_alpaca.py`
- Create on demand: `data/paper/` directory and `portfolio_history.json`

**Definition of done:** A unit test that mocks the Alpaca client and supplies a synthetic trade log asserts the fetch method returns the expected four portfolio fields plus the lifetime count, and the portfolio-history JSON gets written. **Critically: the mock's `get_portfolio_history()` must return objects with `profit_loss: List[float]`, `profit_loss_pct: List[Optional[float]]`, `equity: List[float]` matching the actual `alpaca.trading.models.PortfolioHistory` shape — not scalars.** A second test forces a date roll and asserts the cache is bypassed and the JSON is rewritten. A third test simulates an Alpaca failure and asserts the previous cache is returned (or empty defaults if first call). A fourth test reads a synthetic `data/paper/trades.jsonl` with 5 EXIT events and asserts `lifetime_trade_count == 5`.

---

## Task 2 — `StatsCalculator`: equity-derived Sharpe and Max DD only

**Who:** `traderlib/stats_calculator.py`. The dashboard imports it; the engine does not.
**Why:** Sharpe and Max DD are pure math over an equity array. Everything else the lifetime panel needs (Total Trades) comes from the engine's pre-fetch. A single-purpose function keeps the math module honest and easy to test.
**What:** One static method. `lifetime_stats(equities: list[float])` returns `{sharpe, max_dd}`.
**How (behavior, not code):**

- `sharpe` and `max_dd` both require ≥30 equity points; below that threshold both are `None`. Sharpe annualizes with √252. Max drawdown is a non-positive percentage.
- Empty or single-point inputs return `{sharpe: None, max_dd: None}`.
- No file I/O. No other inputs.

**Files:**
- Modify: `traderlib/stats_calculator.py`
- Modify: `tests/test_stats_calculator.py`

**Definition of done:** A test that feeds 100 points of synthetic equity returns non-null Sharpe and a non-positive max drawdown. A test with <30 points returns nulls. A test with empty input returns nulls. No file I/O happens in `StatsCalculator` itself.

---

## Task 3 — Dashboard: optional row caps for positions and activity

**Who:** Dashboard, in `_positions()` and `_activity()`.
**Why:** The current dashboard renders every open position and every recent event unconditionally. On a 24-row terminal, this pushes the equity sparkline and lifetime panel below the fold, defeating the responsive layout. Capping the most-volatility-sensitive lists first preserves the most informative content.
**What:** Both methods accept an optional cap. When the cap is set and the list exceeds it, render the top-N entries and append a dim italic `+N more …` line. When the cap is `None`, behavior is unchanged. Positions are sorted by absolute unrealized P&L descending when truncating; activity preserves insertion order (most recent first).
**How (behavior, not code):**

- `_positions(state, max_rows=None)`: if `max_rows` is set and there are more positions, sort the visible set by `|unrealized P&L|` descending, take the first N, and append a row with `+{hidden} more positions` in the first column and empty strings in the rest. If there are no positions at all, render a single `--` placeholder row as before.
- `_activity(max_events=None)`: when the in-memory event deque exceeds `max_events`, render the first N events and append a dim italic `+{hidden} more events` line. When `max_events` is `None`, use the existing default cap of 10.
- The exit/stop/scale lines now also append an R-multiple suffix (e.g., `+1.2R`) when the event dict has an `r_multiple` field. Entry events are unchanged. R color thresholds stay red (<0), yellow (<1), green (<2), bold green (≥2).

**Files:**
- Modify: `traderlib/dashboard.py` (`_positions`, `_activity`)
- Modify: `tests/test_dashboard.py`

**Definition of done:** Tests with 12 positions and `max_rows=6` produce a `+6 more positions` line and only 6 ticker rows. Tests with 20 events and `max_events=5` produce a `+15 more events` line and 5 event lines. A test with fewer entries than the cap does not produce a "more" line.

---

## Task 4 — Dashboard: height-tiered responsive render

**Who:** Dashboard, in `_render()`.
**Why:** The current dashboard is one-size-fits-all. On a 24-row terminal it overflows; on a 50-row terminal it leaves a lot of room unused. Three tiers (24, 35, 50) cover "fits the essentials," "adds context," and "shows everything." Content selection by height means the same code works in any window without scrollbars.
**What:** `_render()` reads `self.console.height` and decides which sections to emit and what caps to apply. Sections that are off for a given tier are skipped entirely. A terminal below 24 rows falls back to the minimum view: header, stats, footer.
**How (behavior, not code):**

Three height tiers and the section set each one shows. The market-state conditional is applied per tier:

- **24-row (minimum):** header, stats, today, positions capped at 6, footer. No activity, no sparkline, no sectors, no closed trades, no lifetime panel. Post-market at this tier shows the same section set as market-open, with two differences: the positions table's `CURRENT` column header becomes `CLOSE`, and the stats (cash, unrealized, open count, heat) are recalculated to reflect fully-exited positions.
- **35-row:** header, stats, today, positions capped at 10, activity capped at 5 (or closed-trades capped at 5 post-market), sparkline, footer. No sectors, no lifetime panel.
- **50-row (full):** header, stats, today, all positions, all activity (or all closed trades post-market), sparkline, lifetime panel (post-market only), sectors, footer.

The tier table also accounts for market state: post-market replaces activity with closed trades and adds the lifetime panel.

**Files:**
- Modify: `traderlib/dashboard.py` (`_render`)
- Modify: `tests/test_dashboard.py`

**Definition of done:** A test that builds a mock console at heights 24, 35, 50 with the same state dict produces three outputs where 50-row content is strictly longer than 35-row, which is strictly longer than 24-row. A 22-row fallback produces only header + stats + footer.

---

## Task 5 — Dashboard: ACCOUNT VALUE / YTD line, equity sparkline, closed trades, lifetime panel

**Who:** Dashboard, in `_stats()` and four new methods.
**Why:** This is the visible payoff of the rest of the work. The stats line is what the user looks at first and is the most error-prone — renaming EQUITY→ACCOUNT VALUE changes meaning, and YTD belongs next to DAY P&L because they're both "how much did the account move" quantities. The sparkline answers "is the equity curve trending?" at a glance. Closed trades give post-market the equivalent of what activity shows during market hours. The lifetime panel quantifies the trading system itself, not just today's P&L, with sample size as a guardrail against misreading Sharpe.
**What:**

- Modify the first line of `_stats()` so it reads `ACCOUNT VALUE`, then `DAY P&L`, then `YTD` (with a percent in dim). YTD is colored green when non-negative, red when negative. The existing three stats lines below (cash/unrealized/open, pending/heat) are unchanged. The `ACCOUNT VALUE` label is sourced from `state["equity"]` — the same field the existing `EQUITY` label reads. The visible change is the label only; the value is unchanged.
- New method `_equity_sparkline(state)`: renders a 30-cell Unicode block line (`▁▂▃▄▅▆▇█`) scaled to the `equity_30d` min/max, with a `$NNN.NK` (or `$N.NNM` for values ≥ $1M) right-aligned label. If `equity_30d` has fewer than 30 points, pad on the left with `░` cells. If `equity_30d` is empty, render a flat 30-cell `░` line with `--` as the value.
- New method `_closed_trades(max_events=None)`: post-market only. Reads `data/paper/trades.jsonl` on demand (the live engine's trade log), filters to today's events with `event` in `EXIT` / `STOP` / `SCALE` and a present `exit_price`, sorts by timestamp descending, and renders each as `icon HH:MM  TYPE  TICKER  entry→exit  pnl`. Caps to `max_events` and appends `+N more closed trades` if exceeded. Returns a "no closed trades today" message when the file is missing, empty, or has no matching events. **This is the only file I/O on the render path; it is correct because closed-trades is a live view that changes on every EXIT event.** Each trade dict in the file is expected to have `event`, `ticker`, `entry_price`, `exit_price`, `realized_pnl`, and `timestamp` (ISO format) fields.
- New method `_lifetime_stats(state)`: post-market, 50-row only. Calls `StatsCalculator.lifetime_stats(state.get("equity_all", []))` once per render to compute Sharpe and Max DD, then reads `state.get("lifetime_trade_count", 0)` for Total Trades. Renders a three-line panel: `Sharpe: X.XX  Max DD: -X.X%  Total Trades: NNNN`. Renders `--` for Sharpe and Max DD when there are <30 equity points. Total Trades is always shown.

**Files:**
- Modify: `traderlib/dashboard.py` (`_stats`, plus four new methods)
- Modify: `tests/test_dashboard.py`

**Definition of done:** A test that builds a state dict with `ytd_pnl=15340`, `ytd_pnl_pct=15.3` produces a stats line containing `ACCOUNT VALUE`, `DAY P&L`, and `YTD` with green color tags. A test that supplies `equity_30d=[…]` produces a 30-character sparkline with a `$NNN.NK` label. A test that writes a synthetic `data/paper/trades.jsonl` with three EXIT events for today and a few for other days, then calls `_closed_trades()`, produces three closed-trade lines (and uses a temp directory to avoid touching real data). A test that supplies 100 equity points and `lifetime_trade_count=847` produces a lifetime panel with non-null Sharpe, a non-positive Max DD, and `Total Trades: 847`. A test that supplies <30 equity points produces `--` for Sharpe and Max DD but still shows Total Trades.

---

## Task 6 — Dashboard: today-summary `avg_r` precision

**Who:** Dashboard, in `_today_summary()`.
**Why:** `avg_r` is the most diagnostic single number for a trading system; `+0.5R` vs `+0.45R` vs `+0.456R` carries different meaning at different precision. The current format (`+.1f`) rounds away real signal.
**What:** Change the format specifier on `avg_r` from one decimal to two (`+.2f`).
**How (behavior, not code):** Single-character change in the format string. No other formatting in the today line changes.

**Files:**
- Modify: `traderlib/dashboard.py` (`_today_summary`)

**Definition of done:** A test that feeds `avg_r=0.456` to `_today_summary` produces a line containing `+0.46R`.

---

## Task 7 — Full test sweep

**Who:** Test suite.
**Why:** The dashboard's existing tests were written before this work, and some call `_positions()` and `_activity()` with the old signatures. The new optional parameters must be backward-compatible, and the new height tiers must not regress existing behavior at any terminal size.
**What:** Run the full suite; fix any test that depends on old method signatures or fixed-width rendering assumptions.
**How (behavior, not code):**

- Run the suite. Existing tests should pass with the new optional parameters defaulting to `None`.
- If a test asserts on a fixed output length, the height-aware rendering may have changed what the test sees; either update the test to fix a console height or use a tier-appropriate state dict.
- Any new code that the tests don't cover is a gap — add a test for it before considering this done.

**Files:**
- Modify as needed: anything that breaks

**Definition of done:** `pytest tests/ -v` is green (or has only pre-existing known skips).

---

## Out of scope

- Tickers-without-positions detail rows.
- Web dashboard.
- Any change to `paper_trades.jsonl` schema.
- Removing the existing `equity` key from the state dict — the engine still computes and passes it; the dashboard now ignores it in favor of the new `ACCOUNT VALUE` label sourced from the same field.
- A separate "today stats" panel. The existing `TODAY: 6W / 2L | +$1,247 | avg +0.45R | 75% WR` line on the stats area already shows the most important daily numbers. The lifetime panel covers the rest.
- Win Rate, Avg R, Expectancy, Profit Factor on the lifetime panel. These would need ongoing per-trade aggregation that's not worth the engine work for a number that changes slowly and isn't requested.

---

## Risk register

- **Alpaca rate limits:** Two fetches per day (startup + date roll) means at most 3 calls per fetch (YTD, 1M, all) — 6 API calls per day total, plus the existing engine's regular calls. Trivial against the 200/min limit.
- **Post-market without a recent cache:** If the engine is restarted after a weekend with no fetch, `data/paper/portfolio_history.json` is the fallback for the four portfolio fields. If even that's missing (fresh install), the dashboard shows `--` and `░` for the sparkline, `--` for Sharpe and Max DD, and `0` for Total Trades.
- **Equity array length mismatches:** `equity_30d` from `1M` may be 22 trading days; the sparkline pads to 30 cells with `░` on the left. `< 2` points produce an empty line and `--`.
- **Backward compatibility:** Existing tests that build state dicts without `ytd_pnl`, `equity_30d`, etc. should keep working because every read site defaults to `0.0` / `[]` / `0` / empty. The existing TODAY line reads the same engine fields it always did; nothing about it changes.
- **Trade-log growth:** `data/paper/trades.jsonl` grows without bound. The engine reads the full file twice per day (at startup and date roll) for counting and listing. Fine for thousands of entries. If the file grows to tens of thousands, the startup/date-roll scan will slow down — at that point, switch to an append-only counter file. Out of scope for this version.
- **Trade-log path drift:** `_closed_trades()` reads `data/paper/trades.jsonl` on demand (the live engine's path, verified at `traderlib/paper_state.py:205`). The old `StatsCalculator` default and the README/TOOLS.md docs say `data/paper_trades.jsonl` — that path is no longer written by the engine. The plan uses the correct path; the old default should be aligned as a small follow-up cleanup.
- **Date-roll detection:** The first call of a new calendar day triggers a refetch. If the engine is started late on a Friday and runs through the weekend, the date roll to Saturday triggers one refetch (waste, but harmless — same data). Saturday→Sunday is another. This is acceptable. If the engine runs continuously across a Friday close, the date roll on Saturday morning triggers the refetch that picks up Friday's close — which is the correct behavior.
- **Assumption: engine is restarted daily, or at minimum on every market day.** Continuous multi-day operation without a restart will produce a 1-day-stale `equity_all` between the previous market close and the next date roll. The lifetime panel's sparkline will lag the latest close by ~1 day during continuous operation. The paper trading bot is expected to be restarted daily; this assumption should be confirmed with the user before implementation.

## GSTACK REVIEW REPORT

### Review Run

| Field | Value |
|------|-------|
| Plan | `docs/superpowers/plans/2026-06-06-dashboard-ux-improvements.md` |
| Reviewer | claude-sonnet-4-6 (eng-manager review skill) |
| Branch | main |
| Date | 2026-06-06 |
| Codex cross-check | **BLOCKED — codex CLI returned 401 Unauthorized (no OpenAI API key configured in this environment). Single-model review.** |

### Step 0 — Scope Challenge

| Check | Result |
|------|--------|
| Existing code that solves sub-problems | Alpaca SDK already imported; trade-log parsing pattern already in `_get_today_trade_stats()` (line 718); state-dict pattern already in `_print_status()` (line 1378). Plan reuses all of these — no parallel data paths. |
| Minimum-change assessment | Scope matches user's explicit asks (ACCOUNT VALUE rename, YTD, 24/35/50 responsive, sparkline, closed-trades, slim lifetime panel). Today-stats panel and rich lifetime fields were already cut in the lean pass. No further cuts without contradicting user requirements. |
| Complexity (file / class count) | 5 files modified, 0 new classes, 1 new persistent file. Under the 8-file / 2-class smell threshold. |
| Search-before-building | No reinvented built-ins. Manual Sharpe / Max DD over equity array is correct (no stdlib equivalent). Manual sparkline with Unicode blocks is correct (Rich's `Sparkline` widget has different styling that wouldn't match existing plain-Text dashboard). |
| Completeness | All requirements covered. Test definitions are explicit per task. No deferred completeness work. |
| Distribution | Not applicable — no new artifact type. |

### Architecture Findings

| ID | Severity | Title | File / Section | Status |
|----|----------|-------|----------------|--------|
| A1 | ~~BLOCKING~~ RESOLVED | `profit_loss` and `profit_loss_pct` are lists (`List[float]`), not scalars. Plan must use `[-1]` indexing to extract the period P&L number. Verified against the actual `alpaca.trading.models.PortfolioHistory` class in this repo's venv. | Task 1 description | **Fixed**: Architecture section + Task 1 prose now specify "last element of the list" behavior, and the test Definition of done requires the mock to mirror the SDK's list shape. |
| A2 | LOW | `equity_all` is daily-resolution. Brand-new accounts (<30 trading days) will see `--` for Sharpe and Max DD. Document, not fix. | Architecture section | Acknowledged in Task 2. |
| A3 | HIGH | Continuous operation across market close produces a 1-day-stale cache between previous close and next date roll. Plan must document the "engine restarted daily" assumption explicitly. | Task 1 cache invalidation | **Fixed**: explicit assumption added to risk register. |
| A4 | ~~BLOCKING~~ RESOLVED | `closed_trades_today` is only built at startup and on date roll, but it changes on every EXIT event during market hours. The closed-trades panel will appear broken (empty when it should have entries) during a live session. | Task 1 + Task 5 | **Fixed**: `closed_trades_today` is removed from the pre-fetched state dict. `_closed_trades()` reads `data/paper/trades.jsonl` on demand. The dashboard render path now has one file I/O — the closed-trades read — and it is the correct trade-off for a live data view. |
| A5 | LOW | `equity_30d` field name is misleading — Alpaca period is `1M`, returns ~22 trading days, not 30. Rename to `equity_1m`; keep display label `EQUITY (30D)` to match the mockup. | State dict key naming | Renamed in Architecture section as a "rename candidate." |

### Code Quality Findings

| ID | Severity | Title | File / Section | Status |
|----|----------|-------|----------------|--------|
| C1 | — | `equity_all: list[float]` type hint is **correct** (matches Alpaca SDK). Not an issue. | (verified) | OK |
| C2 | LOW | "Two fetches per day" claim in risk register is overconfident — engine restarts add fetches. Drop the specific count. | Risk register | Open. |
| C3 | ~~BLOCKING~~ RESOLVED | `lifetime_trade_count` is not persisted, so post-market after a weekend restart shows `Total Trades: 0` instead of the real count. Persist it in the JSON file alongside the portfolio fields. | Task 1 post-market path | **Fixed**: `lifetime_trade_count` is recomputed at engine startup from the trade log. No persistence needed — the source of truth is the trade log itself, and startup is the natural read point. Post-market after a restart will show `0` only if the engine itself was never started in this session (rare). The trade-off is documented in Task 1. |
| C4 | LOW | Test description for `lifetime_stats` is loose about synthetic equity shape (100 points of flat equity would divide by zero on std dev). Plan should describe the data shape, not the count. | Task 2 definition of done | Open. |

### Test Findings

| ID | Severity | Title | File / Section | Status |
|----|----------|-------|----------------|--------|
| T1 | MEDIUM | Mock object for Alpaca in the engine test must mirror the SDK's actual return shape (lists, not scalars). A careless implementer will mock `profit_loss=15340.0` instead of `profit_loss=[..., 15340.0]` and the test will pass while production breaks. Plan must specify the mock shape. | Task 1 definition of done | **Fixed**: Definition of done now requires the mock to mirror the SDK's list shape. |
| T2 | LOW | Date-roll test setup is unspecified. Plan should say "mutate `_last_fetch_date` directly to a past date, call the method, assert cache was bypassed." | Task 1 definition of done | Open. |
| T3 | ~~LOW~~ RESOLVED | `closed_trades_today` test fixture needs explicit field list: `event`, `ticker`, `entry_price`, `exit_price`, `realized_pnl`, `timestamp` (ISO). | Task 5 definition of done | **Fixed**: `_closed_trades()` is now tested with a synthetic `data/paper/trades.jsonl` file written in a temp directory. The required fields are listed in the Task 5 prose. |
| T4 | OK | `StatsCalculator.lifetime_stats` tests (≥30 threshold, empty case, all-None case) are correctly scoped. | (no change) | OK |
| T5 | OK | Backward-compat test for existing TODAY line is the right test to have, given the no-behavior-change requirement. | (no change) | OK |

### Performance Findings

| ID | Severity | Title | File / Section |
|----|----------|-------|----------------|
| P1 | LOW | Startup fetch blocks engine readiness. Plan should specify a timeout (e.g. 10s) for the Alpaca call. | Task 1 failure handling |
| P2 | — | Date-roll check on every `_print_status()` is O(1) and trivial. Not a concern. | (verified) |
| P3 | — | Sparkline rendering at 2Hz over 30 cells is trivial. Not a concern. | (verified) |
| P4 | LOW | If A4 is fixed by reading the trade log directly on render, the cost is O(N) per render at 2Hz. Trivial in practice (OS cache, line-by-line format), but should be noted. | Task 5 |

### Cross-Model Status

- **Codex CLI:** `401 Unauthorized` — `OPENAI_API_KEY` not configured. Could not run a second-model review.
- **Recommendation:** Re-run this review with codex credentials before implementation to catch anything the single-model pass missed.

### Unresolved Items

- None at the review level. All issues have been characterized; A1, A4, and C3 require plan updates before implementation, A3 requires an explicit user confirmation of the restart-daily assumption, the rest are documentation/clarity improvements.

### VERDICT

**READY** — all three blocking issues (A1, A4, C3) are fixed. A3 is documented as an explicit assumption. One high-severity issue (A3) was confirmed with the user as an acceptable trade-off for the paper-trading-bot usage pattern. The lean architecture is sound; the fixes are about how the lean version initially lost properties the rich version had, and about factual mismatches with the Alpaca SDK.

### Status

| Field | Value |
|------|-------|
| Status | **DONE** |
| Concerns | None blocking. A2, A5, C2, C4, T2, P1, P4 are LOW-severity documentation/clarity items the implementer can address as they go. |
| Attempted | 4-section review (Architecture, Code Quality, Tests, Performance), Step 0 scope challenge, Alpaca SDK source verification, engine source verification, state-dict shape tracing, post-market path analysis, three blocking-issue fixes applied. |
| Recommendation | Plan is ready for implementation. Suggest starting with Task 1 (engine pre-fetch) since it's the most architecturally load-bearing, then Task 2 (StatsCalculator) — both are pure, easily unit-tested. Tasks 3-6 are dashboard changes that build on Tasks 1-2's outputs. |
