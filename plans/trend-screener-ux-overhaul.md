# Trend Screener HTML Report — UX & Setup/Buy Point Overhaul

**Status:** Draft — for review  
**Date:** 2026-06-19  
**Scope:** `scripts/trend_screener.py` (backend + HTML export)

---

## Problem

The current HTML report has two core issues:

1. **Setup and Buy Point are decoupled.** The Setup column shows multiple independent signals (pivot, pocket, volume, trend) while the Buy Point column always shows the 20-day range high — regardless of which setup is shown. A stock with `[pivot] [pocket]` in Setup and `$50.47` in Buy Point leaves the user guessing which price belongs to which signal.

2. **The report lacks basic interactivity.** Static summary bar, orthogonal filter tabs (20d Range / Volume / Pocket don't match the section structure), filtering destroys expanded detail rows, no URL state, no sorting, dead tabs when a category has zero results.

---

## Design Decisions

### Setup ↔ Buy Point: 1:1 pairing

Two visible setup badges. The badge determines what the Buy Point means:

| Setup badge | Buy Point = |
|---|---|
| `pp` | Pocket pivot price |
| `20d` | 20-day range high |

`pivot`, `volume`, and `trend` all use the same buy point (20-day range high), so they all render as `20d` in the HTML. The vol ratio column shows whether volume confirmed the breakout (color-coded: green ≥1.5x, white ≥0.8x, gray <0.8x). The section placement (Ready Now vs Near Pivot) communicates readiness.

`trend` is kept in the backend for section classification but never surfaced as a distinct badge. Stocks with `setup_type='trend'` display `20d` in the Setup column.

### Entry mode flags

| Flag | What it does |
|---|---|
| `--entry-mode pp` | Only pocket pivot setups. Buy Point = pocket pivot price. |
| `--entry-mode 20d` | Only 20-day range high setups (range + volume). Buy Point = 20d range high. |
| `--entry-mode any` | Pocket pivot first → 20d range → volume → trend fallback. Default mode. |

Pocket pivot is the default priority in `any` mode. When a pocket pivot exists and is within proximity, it becomes the primary setup with `setup_type='pp'` and `pivot_price` set to the pocket pivot price. If no pocket pivot, falls back to 20d range high, then volume-confirmed 20d, then trend.

---

## Changes

### A. Backend (`scripts/trend_screener.py`)

#### A1. CLI flags
- Rename `--entry-mode` choices from `any/pocket/pivot/volume` to `any/pp/20d`
- Update help text and examples

#### A2. Detection logic
- `_try_volume_pivot()`: keep the function, change `setup_type` from `'volume'` to `'20d'` — same buy point, same vol threshold check, just a unified label
- `_try_pocket_pivot_setup()`: set `pivot_price` to pocket pivot price (currently missing — causes Buy Point to show "—")
- `_try_range_pivot()`: set `setup_type` to `'20d'` instead of `'pivot'`
- `entry_mode='any'`: try pocket pivot first → 20d range → volume → trend fallback. Pocket pivot produces `setup_type='pp'`; the rest produce `setup_type='20d'` in the HTML

#### A3. Section classification
- Include `pp` in Ready Now: `setup_type in ('pp', '20d')` (currently only `pivot` and `volume`)
- Near Pivot: `entry_ready + setup_type == 'trend'`
- Extended: `not entry_ready + setup_type != 'none'`
- No Setup: `setup_type == 'none'`

### B. HTML export

#### B1. Setup badges
- Two badges only: `pp` (red) and `20d` (blue)
- Remove secondary pocket badge — no `[pocket $XX.XX]` appended
- Remove volume and trend badge styles from CSS

#### B2. Section-aligned filter tabs
- Filter buttons match the report's section structure: `All | Ready Now | Near Pivot | Extended | No Setup`
- These replace the current orthogonal setup-type tabs (`20d Range / Volume / Pocket`)
- The Setup column badges (`pp`/`20d`) already tell the user the signal type — no separate filter row needed
- Each row gets a `data-section` attribute (e.g., `data-section="ready"`) so the filter JavaScript can show/hide rows by section

#### B4. Clickable summary bar
- Each summary card (18 Ready Now, 62 Near Pivot, etc.) becomes clickable
- Clicking scrolls to that section and highlights the card

#### B5. Live-updating counts
- When a filter is active, summary bar numbers update to show visible counts
- Section headers show "(N visible)" alongside the static total

#### B6. Detail rows survive filtering
- Expanding a ▼ then applying a filter keeps the detail row open if the parent row is still visible
- Only detail rows belonging to hidden stocks are closed

#### B7. Active-filter banner
- When a filter is active, a blue banner appears: "🔍 Filtered: Ready Now (18 of 87)"
- "✕ Show all" link clears the filter

#### B8. URL hash persistence
- Filter state stored in URL hash (`#ready`, `#near`, etc.)
- Bookmark a filtered view, share it via link
- On page load, restore filter from hash

#### B9. Sortable columns
- Click any column header to sort ascending, click again for descending
- Sorted column shows a blue arrow indicator
- Numeric columns sort by value, text columns sort alphabetically

#### B10. Dynamic denominator
- "X of Y shown" reads Y from the actual DOM row count, not a hardcoded number
- Works correctly if tomorrow's report has a different total

#### B11. No Setup section always rendered
- The No Setup section exists even when count is 0
- Shows an empty state message instead of disappearing
- Keeps layout stable day to day

### C. Vol ratio column
- No changes needed. Already color-coded correctly from real data.

---

## Implementation notes

- The mockup (`scans/mockup-improved.html`) uses a hardcoded JavaScript array of 87 stocks for demonstration. The real implementation must generate all data dynamically from the screener's analysis results — no hardcoded stock data, counts, or section sizes. All JavaScript (filtering, sorting, URL hash, live counts) must work against dynamically generated rows.
- The mockup proves the design works. The implementation is a different code path: Python generates the HTML and data, JavaScript handles the interactivity client-side.

## What stays the same

- **HTML design must match the mockup at `scans/mockup-improved.html`** — the visual design, layout, colors, spacing, and all UX interactions are finalized in the mockup. Implementation must reproduce it exactly, not redesign it.
- Dark theme, table layout, row coloring (green/orange/red by section)
- Stage 2 dots, MA stack in expandable detail rows
- Dollar volume formatting, sector badges
- All discovery filters (price, MA stacking, RS, liquidity)
- CSV/JSON export paths

---

## Files affected

| File | Changes |
|---|---|
| `scripts/trend_screener.py` | Backend logic + HTML template |
| `tests/test_trend_screener.py` | Update tests for new entry modes and setup types |

## Testing

- **Backend tests:** Update existing tests that assert old `setup_type` values (`pivot`, `volume`, `trend`, `pocket`) and old `--entry-mode` flags. Add tests for `--entry-mode pp` and `--entry-mode 20d`. Add test that pocket pivot sets `pivot_price` correctly (the current bug).
- **HTML output tests:** Add tests that run the screener on mock data and verify the generated HTML:
  - Correct badges render (`pp` or `20d`, no secondary pocket badge)
  - `data-section` attributes match the section classification
  - Section classification puts `pp` stocks in Ready Now
  - No hardcoded stock data or counts in the template
  - Buy Point matches the setup type (pocket pivot price for `pp`, 20d range high for `20d`)
- This is where the design was lost last time — the HTML output wasn't tested, so visual regressions went unnoticed.

---

## Reference

- Current mockup: `scans/mockup-improved.html` (demonstrates all UX improvements with real data)
- Current report: `scripts/scans/trend_screen_20260619_151711.html` (87 stocks, 18 Ready Now, 62 Near Pivot, 7 Extended)
