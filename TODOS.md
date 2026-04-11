# TODOS — Deferred from /autoplan Review

Generated: 2026-04-09
Source: /autoplan CEO, Design, Eng, DX review phases

## Critical Fixes (Do First)

### Engineering
- [x] **FINDING-002**: Split-brain vulnerability — Add `PENDING` status, track order IDs separately *(Completed 2026-04-10)*
- [x] **FINDING-004**: Order storm protection — Add submission queue with TPS limiting *(Completed 2026-04-11)*
- [x] **FINDING-008**: Partial fill handling — Track `filled_qty` separately, accumulate before position creation *(Completed 2026-04-10)*
- [ ] **FINDING-010**: Plaintext API keys — Use env vars or macOS Keychain, remove JSON credential storage
- [x] **FINDING-005**: Dangerous fallback defaults — Require explicit stops, mark `UNSYNCED` if missing *(Completed 2026-04-10)*

### DX
- [ ] **GS-001**: Python version check in `setup.sh`
- [ ] **GS-002**: `make doctor` command for config validation
- [ ] **CLI-003**: Sensible default for `midday_scan.py` (scan watchlist if exists)
- [ ] **CLI-004**: `--dry-run` flags for destructive commands
- [x] **EH-003**: Actionable API key error message *(Completed 2026-04-11)*
- [ ] **DOC-001**: Create `docs/getting-started.md`
- [ ] **NO_COLOR**: Respect `NO_COLOR` env var

### Design
- [x] **Timezone suffix**: Add "ET" to timestamp displays *(Completed 2026-04-11)*
- [x] **Portfolio overlap**: Add `[IN PORTFOLIO]` indicator to watchlist *(Completed 2026-04-11)*
- [x] **Signal age**: Add timestamp/age column to entry signals *(Completed 2026-04-11)*
- [x] **Market filter context**: Expand message with reason and reset condition *(Completed 2026-04-11)*
- [x] **Empty watchlist guidance**: Add "how to populate" help text *(Completed 2026-04-11)*

## Medium Priority (Do Soon)

### Engineering
- [ ] **FINDING-001**: Circular import risk — Refactor to proper package structure
- [ ] **FINDING-003**: WebSocket task lifecycle — Add restart limits, supervisor pattern
- [x] **FINDING-006**: Stale price cache poisoning — Track price staleness, reject old prices *(Completed 2026-04-11)*
- [ ] **FINDING-007**: Weekend/holiday market hours — Integrate `pandas_market_calendars`
- [x] **FINDING-009**: Concurrent file writes — Use atomic write pattern (temp + rename) *(Completed 2026-04-11)*
- [x] **FINDING-011**: Input validation on tickers — Add regex `^[A-Z]{1,5}$` *(Completed 2026-04-11)*
- [ ] **FINDING-012**: YAML schema validation — Add Pydantic/Cerberus validation
- [x] **FINDING-013**: R-multiple drift — Store `initial_stop_price` as immutable *(Completed 2026-04-11)*
- [x] **FINDING-014**: Async/thread safety — Use `threading.Lock()` in health monitor *(Completed 2026-04-11)*
- [ ] **FINDING-015**: Validation bypass — Add `--i-know-what-im-doing` flag

### Design
- [ ] **Progress bars**: Add to `paper_portfolio.py live` for multi-ticker fetching
- [ ] **Milestone recognition**: Celebrate first trade, first +1R, recovery from drawdown
- [ ] **`--summary` mode**: Default to summary, `--detailed` for power users
- [ ] **Terminal capability detection**: `--format=plain` for non-Unicode terminals
- [ ] **Number formatting standards**: Document prices, volume, percentage formats
- [ ] **Watchlist table formatting**: Remove index, group by tier

### DX
- [ ] **GS-003**: Add Alpaca context to `setup_alpaca.py`
- [ ] **CLI-001**: Standardize CLI naming (kebab-case)
- [ ] **CLI-002**: Standardize positional vs flags
- [ ] **CLI-005**: Accept both numeric and emoji tier inputs
- [ ] **PD-001**: `--format json|csv|table` for all listing commands
- [ ] **PD-002**: TTY detection (pretty if terminal, CSV if piped)
- [ ] **PD-003**: `--quiet` mode for scripting
- [ ] **EH-002**: Problem+cause+fix+docs pattern for all errors
- [ ] **EH-004**: Rate limit warnings with timing
- [ ] **EH-005**: Error code system (E1001, E2001, etc.)
- [ ] **ESC-001**: User config file (`~/.trader/config.yaml`)
- [ ] **ESC-002**: Override default screener criteria via config
- [ ] **DOC-002**: Link AGENTS.MD prominently from README
- [ ] **DOC-003**: API reference from docstrings
- [ ] **DOC-004**: FAQ/troubleshooting doc
- [ ] **DOC-005**: Link runbooks from error messages

## Strategic (Do Later)

### CEO Phase Recommendations
- [ ] **Strategy Health Monitor**: Track hit rate by setup type, auto-suspend underperformers
- [ ] **Trade Journal Analysis Engine**: Ingest actual trade data, identify working setups
- [ ] **Manual vs Automated comparison**: Track system-suggested vs system-executed P&L
- [ ] **Paper Performance Gate**: Require 3 months Sharpe > 1.0 before live trading work
- [ ] **Live Trading MVP**: Strip 80%, manual execution only, prove edge first

### Architecture
- [ ] WebSocket supervisor pattern with `asyncio.gather()`
- [ ] Proper package structure with `__init__.py` files
- [ ] Plugin system for custom entry/exit logic

### Documentation
- [ ] Web dashboard alternative to CLI
- [ ] Interactive setup wizard (`trader init`)
- [ ] Auto-generated API reference

## Test Coverage Gaps

- [ ] Integration test for `_sync_with_alpaca()` split-brain scenario
- [ ] Load/stress test for order storm (20+ simultaneous signals)
- [ ] Unit test for `PARTIAL_FILL` order status accumulation
- [ ] Unit test for market holiday detection
- [ ] Chaos test for WebSocket reconnect storm
- [ ] Unit test for stale price cache fallback
- [ ] Unit test for Position `UNSYNCED` status
- [ ] Unit test for credential loading (env vs file)

## Review Decisions Logged

**Taste Decisions (deferred):**
- Progress bars, milestone recognition, `--summary` mode
- Terminal capability detection, formatting standards
- Circular imports refactor, WebSocket supervisor
- CLI naming standardization, error code system

**Mechanical Fixes (approved):**
- 5 critical engineering fixes (split-brain, order storm, partial fills, API keys, defaults)
- 7 DX fixes (version check, doctor, defaults, dry-run, error messages, tutorial, NO_COLOR)
- 5 design fixes (timezone, overlap, signal age, filter context, empty guidance)

**Mode:** SELECTIVE EXPANSION — Hold infrastructure, fix critical data integrity issues, improve DX.
