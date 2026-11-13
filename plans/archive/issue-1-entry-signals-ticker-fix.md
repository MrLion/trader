---
name: Issue #1 Fix — entry_signals.py --ticker Silent Exit
description: Bug fix for single ticker analysis exiting silently without output
type: project
originSessionId: f1f3da4c-6e9e-40f3-aa9c-92e6804f0d79
---
**Issue**: `python3 scripts/entry_signals.py --ticker SCI` printed "🔍 Analyzing SCI..." then exited without showing any analysis.

**Root Cause**: Two bugs in `analyze_single()` method (`scripts/entry_signals.py:481-563`):

1. **Data threshold too high**: Historical data check required `len(hist) >= 200`, but API often returns fewer rows (e.g., 173). Condition failed silently, skipping all output.

2. **Non-existent method call**: Added `self.print_analysis(ticker, analysis)` at line 559 that never existed in the codebase, causing AttributeError when conditions were met.

**Fix Applied**:
- Lowered threshold from `>=200` to `>=150` rows
- Removed phantom `print_analysis()` call (the formatted output was already printed inline)
- Verified with test tickers SCI and AAPL - both now show full analysis

**Files Changed**:
- `scripts/entry_signals.py:495` — threshold fix
- `CHANGELOG.md` — documented the fix

**Verification**: Both `--ticker SCI` and `--ticker AAPL` now display complete analysis including metrics, entry setup, pivot/stop/target prices, and verdict.
