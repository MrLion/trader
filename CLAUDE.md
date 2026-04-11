# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Operations

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
- `data/`: Persistence for the watchlist (`watchlist.csv`), portfolio, and regime tracking.
- `scans/`: Output CSVs from various scanning scripts.
- `reports/`: Generated HTML market reports.
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
- **Fallback Data:** `yfinance` when Alpaca unavailable
- **Analysis Framework:** Based on Stage 2 (7-point system), Relative Strength (RS), and VCP patterns.
- **Watchlist Tiering:** A (Actionable), B (Developing), C (Radar).
