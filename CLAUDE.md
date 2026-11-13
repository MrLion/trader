# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## User-First Principle

Whatever you do — brainstorming, planning, coding, or executing — always ask:

**"Why am I doing this, and what value does this bring to users?"**

This is a tool for traders, not developers. Every plan, every line of code, every error message must answer to the person using it.

## Git Operations
- **Never perform autonomous git operations (commits, pushes, version bumps, changelog updates) without explicit user request. Always ask: 'Should I commit these changes?'
- **Exception:** When using a skill-driven workflow (e.g., `executing-plans`, `subagent-driven-development`), commits are part of the defined process. Authorization at workflow start covers commits within that workflow.

## Planning vs Implementation' 
- **When user asks for a 'plan', 'analysis', or 'review', provide text analysis ONLY. Do not write code, edit files, or create branches unless explicitly instructed to 'implement', 'fix', or 'do it'

### Common Commands
- **Entry Signals (Watchlist Scan):** `python3 scripts/entry_signals.py`
- **Single Ticker Analysis:** `python3 scripts/entry_signals.py --ticker TICKER`
- **Watchlist Management:**
    - Add: `python3 scripts/watchlist_manager.py add TICKER [NOTES]`
    - List: `python3 scripts/watchlist_manager.py list`
    - Remove: `python3 scripts/watchlist_manager.py remove TICKER`
    - Populate: `python3 scripts/watchlist_manager.py populate /path/to/scan.csv`
- **Market Scans:**
    - Sector Scan: `python3 scripts/sector_scan_comprehensive.py`
    - Trend Screener: `python3 scripts/trend_screener.py`
- **MC Stock Charts:**
    - Today's Report: `python3 scripts/mcstock_scraper.py --mode single`
    - Specific Date: `python3 scripts/mcstock_scraper.py --mode single --date 2026-04-06`
    - Historical Range: `python3 scripts/mcstock_scraper.py --mode historical --start 2024-01-01 --end 2025-04-01`
- **Backtesting:**
    - Default: `python3 scripts/backtest.py`
    - Custom range: `python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31`
    - With risk profile: `python3 scripts/backtest.py --risk-profile conservative`
- **Reports:**
    - Pre-market: `python3 scripts/premarket_report.py` (add `--html` for HTML output)
    - Post-market: `python3 scripts/postmarket_report.py` (add `--html` for HTML output)

## Python Async Patterns
- **For Python trading/engineering code involving async/await: always verify sync-to-async boundaries, check for blocking calls in async functions, and confirm event loop handling before claiming fixes are complete.

### External Communications
- **Telegram Posting:** Use `python3 scripts/deliver_report.py --chat-id [ID] --caption "[TEXT]" --file [PATH]`
    - Sandbox: `-4872065090`
    - Channel: `-1002556195363`
    - Discussion: `-1002652699578`
- **Media Attachments:** pass charts and HTML reports via `--file`; they are sent as documents.

### Scheduled Automation
- **Sector Scan:** Daily at 7:50 AM ET (weekdays) — runs `python3 scripts/sector_scan_comprehensive.py` to generate sector rankings before premarket report

## Architecture & Structure

### Repository Layout

**Scripts & Tools (`scripts/`):**
- Entry analysis: `entry_signals.py`, `trend_screener.py`
- Market scans: `sector_scan_comprehensive.py`
- Reports: `premarket_report.py`, `postmarket_report.py`, `deliver_report.py`
- Trading engine: `paper_engine_alpaca.py`, `paper_portfolio.py`, `show_positions.py`
- Data scraping: `mcstock_scraper.py`
- Utilities: `watchlist_manager.py`, `backtest.py`, `doctor.py`, `sync_state.py`
- Setup: `setup_alpaca.py`, `validate_alpaca.py`

**Core Library (`traderlib/`):**
- API & data: `alpaca_client.py`, `earnings_calendar.py`, `market_hours.py`
- Order & position management: `order_manager.py`, `paper_state.py`, `paper_exits.py`
- Risk & config: `risk_config.py`, `rate_limiter.py`, `trading_exceptions.py`
- Analysis: `ticker_analyzer.py`, `pivot_detection.py`, `vcp_utils.py`, `stage2_utils.py`
- Exits: `trailing_exits.py`
- Universe & validation: `universe_builder.py`, `validation.py`
- Paths: `paths.py` (single source of truth for `project_root()` and `data_dir()`; use this in all production code that needs to locate `data/`)
- Backtesting: `backtest/` (data_provider, engine, execution, state, strategy, report)

**Configuration (`config/`):**
- `risk_config.yaml` — Account and position risk settings
- `screener_config.yaml` — Scan thresholds and filters
- `backtest_config.yaml` — Backtest parameters
- `strategies/` — Strategy-specific YAML configs

**Data & Output:**
- `data/` — Watchlist, positions, trades, logs, cache
- `scans/` — Generated CSV scan results
- `reports/` — Generated HTML market reports

**Documentation (`docs/`):**
- `ARCHITECTURE.md`, `METHODOLOGY.md`, `BACKTESTING_GUIDE.md`
- `getting-started.md`, `CONTRIBUTING.md`
- Subdirectories: `entry_signals/`, `trend_screener/`, `patterns/`

**Project Context (`memory/`):**
- Daily logs: `YYYY-MM-DD.md`
- Plans & specs: `roadmap-*.md`, `plan-*.md`
- Curated: `MEMORY.md` (index), `feedback_*.md`, `project_*.md`

**Tests (`tests/`):**
- 70+ test files covering: backtest, paper engine, order lifecycle, exits, risk config
- Integration tests, unit tests, fixtures
- **Test isolation:** A conftest session-scope autouse fixture snapshots `data/` and fails the run if any test mutates production data. Tests that need to write to `data/` redirect via `PAPER_TRADING_DATA_DIR=<tmp_path>` or mark with `@pytest.mark.allow_production_writes`. Run with `--no-isolation-check` to disable. See TOOLS.md "Test Isolation" section for details.

**Key Reference Files:**
- `AGENTS.MD` — Trading playbook, daily rhythm, sector reference
- `TOOLS.md` — Script usage, yfinance patterns
- `SOUL.md`, `USER.md`, `IDENTITY.md` — AI assistant context
- `CLAUDE.md` — This file (coding guidelines, architecture)

### Core Logic & Workflow
The system follows a strict trading operating rhythm:
1. **Pre-Market:** Regime check $\rightarrow$ Calendar check $\rightarrow$ Gap scan (sector-enriched via universe cache) $\rightarrow$ Watchlist review $\rightarrow$ Portfolio heat check (sector exposure from resolved sectors).
2. **Market Hours:** Execution per entry protocol (Pivot, Volume, Market confirmation). New entries carry sector from `SectorResolver` (watchlist → universe → FMP fallback).
3. **Post-Market:** Trade logging $\rightarrow$ New scans (sector-enriched CSV/HTML output) $\rightarrow$ Breadth logging.

**Sector data flow:** Universe CSVs (`data/universes/*.csv`) now carry a `Sector` column populated at build time via FMP API. `SectorResolver` provides unified lookup across `entry_signals`, `trend_screener`, `paper_engine`, `dashboard`, and `backtest`. No per-scan API calls — sectors resolve from cache or universe CSV.

### Technical Dependencies

**Critical Runtime Dependencies:**
- **alpaca-py** (≥0.15.0) — Trading API client for orders, positions, market data
- **pandas** (≥2.0.0) — Data structures for price data, analysis results, trade tracking
- **numpy** (≥1.24.0) — Numerical calculations, required by pandas
- **yfinance** (≥0.2.28) — Fallback data for reports and analysis (15-min delay, not for live trading)
- **websockets** (≥12.0) — Real-time price streaming from Alpaca
- **python-dotenv** (≥1.0.0) — API key management from .env file
- **pytz** (≥2023.3) — Timezone handling for market hours
- **beautifulsoup4** (≥4.12.0) — HTML parsing for MC Stock scraper

**Data Sources:**
- **Primary (Trading):** Alpaca API exclusively — real-time WebSocket + REST for live/paper trading
- **Secondary (Analysis):** yfinance — allowed for reports and backfill (delayed, no fallback for trading)

**Infrastructure:**
- Python ≥3.11 required
- All API credentials via environment/.env (ALPACA_API_KEY, ALPACA_SECRET_KEY, FMP_API_KEY)


## Code Style
- **Before creating any new script, utility, or module, search the entire codebase for existing implementations of the same or similar functionality. Prefer extending existing code over creating new files.
- **When modifying files, prefer writing complete new files (using Write) or large coherent sections over making many small incremental edits. Minimize round-trip Edit calls with narrow string matches.
- **Always use the Read tool to verify file content before using Edit. For complex multi-line changes or when indentation errors appear, prefer Write tool over Edit to avoid string-matching issues.

## Versioning
The project uses a 5-digit version format: `WW.XX.YY.ZZ`

| Position | Meaning | When to Bump |
|----------|---------|--------------|
| `WW` | Super release | Major architectural shifts, huge milestones, generational changes |
| `XX` | Major release | Epics, major subsystem launches |
| `YY` | Minor release | New functionality, new features |
| `ZZ` | Patch | Bug fixes, chores, tests, docs, improvements |

**Examples:**
- `0.6.12.1` → `0.6.12.2` — Bug fix, chore, or improvement
- `0.6.12.0` → `0.6.13.0` — New feature
- `0.6.0.0` → `0.7.0.0` — Major release (e.g., live trading, web dashboard)
- `0.9.0.0` → `1.0.0.0` — Super release (production-ready, stable API)

**Process:**
1. Update `VERSION` file with the new version number
2. Update `CHANGELOG.md` with release notes under the new version
3. Commit: `chore: bump version to WW.XX.YY.ZZ`
4. Create git tag: `git tag vWW.XX.YY.ZZ`
5. Push tag: `git push origin vWW.XX.YY.ZZ`

## Documentation
- **After adding or modifying any feature, always update the corresponding documentation file (e.g., TOOLS.md, README.md) in the same session.

## Debugging
- **When debugging, investigate root causes thoroughly before making changes. Avoid surface-level or symptom-level fixes. State your hypothesis, verify it, then act.

## Skill-Specific Rules

### /investigate (Investigation Skill)
When user invokes `/investigate`:
1. **INVESTIGATE ONLY** — Do NOT implement fixes. Do NOT write code changes.
2. **Report findings** — Root cause, evidence, and recommended fix.
3. **Create proposition** — "Recommended fix: [description]" with file:line references.
4. **WAIT for explicit approval** — "Want me to implement this fix?" before any edits.

This ensures the user controls when investigation transitions to implementation.