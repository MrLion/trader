# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Operations

## Workflow Preferences
- ** When asked for a plan, provide ONLY a plan — do not start implementing. Wait for explicit go-ahead before making changes.

### Common Commands
- **Entry Signals (Watchlist Scan):** `python3 scripts/entry_signals.py`
- **Single Ticker Analysis:** `python3 scripts/entry_signals.py --ticker TICKER`
- **Watchlist Management:**
    - Add: `python3 scripts/watchlist_manager.py add TICKER [NOTES]`
    - List: `python3 scripts/watchlist_manager.py list`
    - Remove: `python3 scripts/watchlist_manager.py remove TICKER`
    - Populate: `python3 scripts/watchlist_manager.py populate /path/to/scan.csv`
- **Market Scans:**
    - Sector Scan: `python3 scripts/sector_scan.py`
    - Comprehensive Sector Scan: `python3 scripts/sector_scan_comprehensive.py`
    - Stage 2 RS Screen: `python3 scripts/stage2_rs_screen.py`
- **MC Stock Charts:**
    - Daily Report: `python3 scripts/mcstock_scraper.py`
    - Historical Archives: `python3 scripts/mcstock_historical_scraper.py --weeks 10`
- **Backtesting:**
    - Default: `python3 scripts/backtest.py`
    - Custom range: `python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31`
    - With risk profile: `python3 scripts/backtest.py --risk-profile conservative`
- **Reports:**
    - Pre-market: `python3 scripts/premarket_report.py` (add `--html` for HTML output)
    - Post-market: `python3 scripts/postmarket_report.py` (add `--html` for HTML output)

### External Communications
- **Telegram Posting:** Use `openclaw message send --channel telegram --account trader --target [ID] --message "[TEXT]"`
    - Sandbox: `-4872065090`
    - Channel: `-1002556195363`
    - Discussion: `-1002652699578`
- **Media Attachments:** Use `--media /path/to/file --force-document` for charts and HTML reports.

## Architecture & Structure

### Repository Layout
- `scripts/`: Python tools for market scanning, stock analysis, and report generation.
- `traderlib/`: Core library modules (alpaca_client, order_manager, paper_exits, etc.).
- `traderlib/backtest/`: Backtesting engine (data_provider, execution, state, strategy, report).
- `data/`: Persistence for the watchlist (`watchlist.csv`), portfolio, and regime tracking.
- `scans/`: Output CSVs from various scanning scripts.
- `reports/`: Generated HTML market reports.
- `config/`: YAML configuration files (risk_config.yaml, scraper_config.yaml).
- `memory/`: Daily logs (`YYYY-MM-DD.md`) and long-term curated memories (`MEMORY.md`).
- `AGENTS.MD`: Core operating rhythm, trading protocols, and sector reference.
- `TOOLS.md`: Technical documentation for `yfinance` and script usage.

### Core Logic & Workflow
The system follows a strict trading operating rhythm:
1. **Pre-Market:** Regime check $\rightarrow$ Calendar check $\rightarrow$ Gap scan $\rightarrow$ Watchlist review $\rightarrow$ Portfolio heat check.
2. **Market Hours:** Execution per entry protocol (Pivot, Volume, Market confirmation).
3. **Post-Market:** Trade logging $\rightarrow$ New scans $\rightarrow$ Breadth logging.

### Technical Dependencies
- **Primary Data:** Alpaca API (real-time WebSocket + REST)
- **Trading Data:** Alpaca API exclusively (real-time, no fallback)
- **Reports/Tools:** `yfinance` allowed for analysis (15-min delay)
- **Analysis Framework:** Based on Stage 2 (7-point system), Relative Strength (RS), and VCP patterns.
- **Watchlist Tiering:** A (Actionable), B (Developing), C (Radar).
- **Position Sizing:** Triple-constraint system (account risk 0.5%, position cap 5%, available cash). Partial positions allowed when cash-limited.
- **Scraper Config:** Validation thresholds in `config/scraper_config.yaml`. Override with `--config` flag.


## Code Style
- **Before creating any new script, utility, or module, search the entire codebase for existing implementations of the same or similar functionality. Prefer extending existing code over creating new files.
- **When modifying files, prefer writing complete new files (using Write) or large coherent sections over making many small incremental edits. Minimize round-trip Edit calls with narrow string matches.

## Versioning
- **Bug fixes** ship as patch version: `0.5.xx` (increment xx)
- **Features** ship as minor version: `0.xx.0` (increment xx, reset patch to 0)
- Always update `CHANGELOG.md` with the version bump
- Always create a git tag for the new version (e.g., `git tag v0.6.0`)

## Documentation
- **After adding or modifying any feature, always update the corresponding documentation file (e.g., TOOLS.md, README.md) in the same session.

## Debugging
- **When debugging, investigate root causes thoroughly before making changes. Avoid surface-level or symptom-level fixes. State your hypothesis, verify it, then act.