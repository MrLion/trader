# Plan: FMP Economic Calendar Integration

**Status:** Ready for implementation  
**Date:** 2026-04-27  
**Target Version:** 0.6.14.x  
**Priority:** Medium

---

## Problem

The pre-market report (`scripts/premarket_report.py`) has an "Economic Calendar" section that is **always empty**. The current implementation attempts to scrape `forex.tradingcharts.com` which returns no usable data.

**Current behavior:**
- Empty events list
- No awareness of CPI, Fed meetings, jobs reports
- "Clear day, trade normally" message even on major event days

**Impact:** Missing high-impact economic events leads to:
- Oversized positions before volatile announcements
- No preparation for gap risk
- Missed context for market regime shifts

---

## Solution

Integrate FMP (Financial Modeling Prep) Economic Calendar API to provide comprehensive economic event data in the pre-market report.

---

## FMP API Capabilities

### Economic Calendar Endpoint
```
GET https://financialmodelingprep.com/stable/economic-calendar
```

**Parameters:**
- `from` — Start date (YYYY-MM-DD)
- `to` — End date (YYYY-MM-DD)
- `apikey` — FMP_API_KEY

**Returns:** Array of events with:
- `date` — Event date
- `time` — Release time (e.g., "08:30")
- `event` — Event name (e.g., "CPI", "Fed Interest Rate Decision")
- `impact` — Impact level (high/medium/low)
- `actual` — Released value
- `estimate` — Consensus estimate
- `previous` — Previous reading
- `unit` — Unit of measurement

### Additional FMP Economics APIs

| Endpoint | Data | Use Case |
|----------|------|----------|
| `/stable/economic-indicators?name=GDP` | GDP growth rate | Regime detection |
| `/stable/economic-indicators?name=unemployment` | Unemployment rate | Labor market health |
| `/stable/economic-indicators?name=inflation` | CPI/PPI | Inflation regime |
| `/stable/treasury-rates` | Yield curve | Recession indicator |

---

## Implementation Plan

### 1. New Module: `traderlib/economic_calendar.py`

Create a reusable module similar to `earnings_calendar.py`:

```python
class EconomicCalendar:
    """Fetches economic events from FMP API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("FMP_API_KEY")
    
    def get_events(self, start: date, end: date) -> List[EconomicEvent]:
        """Fetch economic events for date range."""
        # Cache results per session
        # Rate limit: 300 calls/min (same as earnings)
    
    def get_today_events(self, today: date) -> List[EconomicEvent]:
        """Get today's economic events."""
    
    def get_tomorrow_events(self, today: date) -> List[EconomicEvent]:
        """Get tomorrow's economic events."""
    
    def get_high_impact_events(self, today: date) -> List[EconomicEvent]:
        """Filter for high-impact events only."""
```

**Key features:**
- In-memory caching (one fetch per session)
- Rate limiting (300 req/min)
- Fail-open (empty list if FMP unavailable)
- Timezone handling (convert FMP UTC to ET)

**EconomicEvent dataclass:**
```python
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class EconomicEvent:
    date: date
    time: str  # ET time for display
    event: str
    impact: str  # 'high', 'medium', 'low'
    estimate: Optional[str] = None
    previous: Optional[str] = None
```

### 2. Update: `scripts/premarket_report.py`

Replace `fetch_economic_calendar()` function:

```python
def fetch_economic_calendar():
    """Fetch US economic events from FMP."""
    from traderlib.economic_calendar import EconomicCalendar
    
    cal = EconomicCalendar()
    today = datetime.now().date()
    
    # Get today + tomorrow events
    events = cal.get_events(today, today + timedelta(days=1))
    
    # Separate today vs tomorrow
    today_events = [e for e in events if e.date == today]
    tomorrow_events = [e for e in events if e.date == today + timedelta(days=1)]
    
    return {
        'today': today_events,
        'tomorrow': tomorrow_events,
    }
```

**Risk classification logic:**
- 🔴 **HIGH** risk: ≥1 high-impact events today (CPI, Fed, jobs)
  - Advice: "Reduce size 50% or wait for post-event clarity"
- 🟡 **MEDIUM** risk: ≥1 medium-impact events, no high
  - Advice: "Normal size, watch for volatility at event time"
- 🟢 **LOW** risk: No events or only low-impact
  - Advice: "Clear day, trade normally"

### 3. Report Output Format

**Console output:**
```
📅 Economic Calendar (via FMP)
────────────────────────────────────
🟡 Today's Events:
   08:30  🟡 Initial Jobless Claims  (est: 215k, prev: 218k)
   10:00  🟢 Wholesale Inventories    (est: +0.3%, prev: +0.2%)

   → Normal size, watch for volatility at event time

Tomorrow:
   08:30  🔴 Nonfarm Payrolls  (est: +185k, prev: +192k)

⚠️  Major event tomorrow — size accordingly today
```

**HTML output:**
- Events table with impact badges (🔴🟡🟢)
- Countdown/time indicator
- Risk level banner

### HTML Mockup

```html
<!-- Economic Calendar Section -->
<div class="section">
    <h2>📅 Economic Calendar</h2>
    
    <!-- Risk Level Banner -->
    <div class="risk-badge risk-high">
        🔴 High Impact Events Today — Reduce Size 50%
    </div>
    
    <!-- Today's Events Table -->
    <table class="events-table">
        <thead>
            <tr>
                <th>Time</th>
                <th>Impact</th>
                <th>Event</th>
                <th>Estimate</th>
                <th>Previous</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td class="time">08:30</td>
                <td class="impact impact-high">🔴 HIGH</td>
                <td class="event">Consumer Price Index (CPI)</td>
                <td class="estimate">+0.3%</td>
                <td class="previous">+0.4%</td>
            </tr>
            <tr>
                <td class="time">08:30</td>
                <td class="impact impact-high">🔴 HIGH</td>
                <td class="event">Core CPI</td>
                <td class="estimate">+0.3%</td>
                <td class="previous">+0.4%</td>
            </tr>
            <tr>
                <td class="time">10:00</td>
                <td class="impact impact-medium">🟡 MED</td>
                <td class="event">Wholesale Inventories</td>
                <td class="estimate">+0.2%</td>
                <td class="previous">+0.3%</td>
            </tr>
        </tbody>
    </table>
    
    <!-- Tomorrow Preview -->
    <div class="tomorrow-preview">
        <h3>Tomorrow</h3>
        <div class="event-item">
            <span class="time">08:30</span>
            <span class="impact impact-high">🔴</span>
            <span class="event-name">Nonfarm Payrolls</span>
            <span class="estimate">est: +185k</span>
            <span class="previous">prev: +192k</span>
        </div>
        <div class="warning">
            ⚠️ Major event tomorrow — size accordingly today
        </div>
    </div>
    
    <!-- Actionable Guidance -->
    <div class="guidance">
        <p>→ Reduce position size 50% or wait for post-event clarity</p>
    </div>
</div>

<!-- CSS (follow existing premarket_report.py patterns) -->
<style>
.risk-badge {
    padding: 12px 20px;
    border-radius: 8px;
    font-weight: bold;
    margin-bottom: 20px;
}
.risk-high { background: rgba(248, 113, 113, 0.2); color: #f87171; }
.risk-medium { background: rgba(250, 204, 21, 0.2); color: #facc15; }
.risk-low { background: rgba(74, 222, 128, 0.2); color: #4ade80; }

.events-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
}
.events-table th {
    text-align: left;
    padding: 10px;
    color: #94a3b8;
    font-weight: 500;
    border-bottom: 1px solid #475569;
}
.events-table td {
    padding: 12px 10px;
    border-bottom: 1px solid #334155;
}
.events-table .time {
    font-family: monospace;
    color: #f8fafc;
    width: 60px;
}
.events-table .impact {
    width: 80px;
    font-size: 0.85rem;
}
.impact-high { color: #f87171; }
.impact-medium { color: #facc15; }
.impact-low { color: #4ade80; }
.events-table .event {
    color: #f8fafc;
    font-weight: 500;
}
.events-table .estimate,
.events-table .previous {
    color: #94a3b8;
    font-family: monospace;
    width: 100px;
}

.tomorrow-preview {
    background: var(--bg-tertiary);
    padding: 15px;
    border-radius: 8px;
    margin: 20px 0;
}
.tomorrow-preview h3 {
    margin: 0 0 10px 0;
    color: #94a3b8;
    font-size: 0.9rem;
}
.tomorrow-preview .warning {
    margin-top: 10px;
    color: #facc15;
    font-style: italic;
}

.guidance {
    margin-top: 15px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-left: 4px solid #facc15;
    border-radius: 0 8px 8px 0;
}
.guidance p {
    margin: 0;
    color: #f8fafc;
}
</style>
```

**Visual Design Notes:**
- Follows existing dark theme from premarket report (`--bg-primary: #0f172a`, etc.)
- Risk badges use same colors as regime indicators (red/yellow/green)
- Monospace font for times and numbers (alignment)
- Zebra striping not needed — keep clean single-color rows
- Tomorrow preview visually distinct but secondary
- Guidance box draws attention with left border accent

### 4. High-Impact Event Definitions

| Event | Impact | Typical Market Effect |
|-------|--------|----------------------|
| CPI/PPI | HIGH | 2-3% SPY swing |
| Fed Rate Decision | HIGH | 2-4% SPY swing |
| Nonfarm Payrolls | HIGH | 1-2% SPY swing |
| GDP | MEDIUM | 1% SPY swing |
| Jobless Claims | MEDIUM | 0.5% SPY swing |
| Retail Sales | MEDIUM | 0.5-1% SPY swing |

**Hardcoded high-impact keywords:**
- `CPI`, `PPI`, `Fed`, `FOMC`, `Nonfarm`, `Payrolls`, `Employment`

---

## CLI Changes

No CLI changes required. The pre-market report automatically uses FMP when `FMP_API_KEY` is set.

---

## Files to Modify

| File | Change |
|------|--------|
| `traderlib/economic_calendar.py` | **New** — FMP economic calendar module |
| `scripts/premarket_report.py` | Replace tradingcharts scraper with FMP |
| `config/.env.example` | Add `FMP_API_KEY` documentation |
| `docs/TOOLS.md` | Document economic calendar feature |

---

## Empty State Handling

**No events today:**
```html
<div class="risk-badge risk-low">
    🟢 Clear Day — No Major Economic Events
</div>
<p class="no-events">No high or medium impact events scheduled for today.</p>
```

**API unavailable (fail-open):**
```html
<div class="risk-badge risk-medium">
    🟡 Economic Calendar Unavailable
</div>
<p class="no-events">Check external calendar manually before trading.</p>
```

---

## Testing Checklist

- [ ] FMP API returns events for date range
- [ ] Impact classification (high/medium/low) works
- [ ] Risk level calculation (🔴🟡🟢) accurate
- [ ] Timezone conversion (UTC → ET) correct
- [ ] Fail-open when FMP unavailable
- [ ] Console output formatted correctly
- [ ] HTML report shows events with badges
- [ ] Action items generated correctly
- [ ] Weekend handling returns empty list
- [ ] API key missing logs warning and returns empty list
- [ ] Rate limiting handles 300 req/min limit
- [ ] DST transitions handled correctly

---

## Benefits

| Benefit | How It's Achieved |
|---------|-------------------|
| Know major events before open | FMP API provides scheduled releases |
| Size positions appropriately | Risk level guidance (🔴🟡🟢) |
| Prepare for volatility | High-impact event warnings |
| No false "clear day" messages | Actual data vs broken scraper |
| Consistent with earnings gate | Same FMP API, same rate limits |

---

## User Value

- **Before:** "Clear day, trade normally" even on CPI day
- **After:** "🔴 CPI at 08:30 — reduce size 50%"

---

## Implementation Notes

1. **Reuse earnings calendar pattern** — Same caching, rate limiting, fail-open approach
2. **Date range queries** — Fetch today + tomorrow in one call
3. **Timezone handling** — FMP returns UTC, convert to ET for display
4. **Cache key** — In-memory only (same pattern as earnings calendar)

---

## Additional Implementation Details

### Weekend Handling
Economic events don't occur on weekends. The module should gracefully return empty lists:

```python
def get_events(self, start: date, end: date) -> List[EconomicEvent]:
    """Fetch economic events for date range."""
    # Skip weekends — no economic events scheduled
    if start.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return []
    # ... rest of implementation
```

### Timezone Conversion
FMP returns times in UTC. Convert to America/New_York for display:

```python
from zoneinfo import ZoneInfo  # Python 3.9+

# Parse UTC time from FMP
utc_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
utc_dt = utc_dt.replace(tzinfo=ZoneInfo("UTC"))
et_dt = utc_dt.astimezone(ZoneInfo("America/New_York"))
```

### API Key Missing
Match earnings calendar behavior exactly:

```python
def __init__(self, api_key: Optional[str] = None):
    self._api_key = api_key or os.environ.get("FMP_API_KEY")
    if not self._api_key:
        logger.warning(
            "EconomicCalendar: FMP_API_KEY not set — economic calendar disabled"
        )
```

### Rate Limiting
Use the same simple token bucket as earnings calendar:

```python
_MAX_CALLS_PER_MIN = 300

def _rate_limit(self) -> None:
    """Block until within 300 calls/min budget."""
    now = time.monotonic()
    window = 60.0
    self._call_times = [t for t in self._call_times if now - t < window]
    if len(self._call_times) >= self._MAX_CALLS_PER_MIN:
        sleep_for = window - (now - self._call_times[0]) + 0.05
        if sleep_for > 0:
            time.sleep(sleep_for)
    self._call_times.append(time.monotonic())
```

---

## Edge Cases

| Edge Case | Behavior |
|-----------|----------|
| Weekend (Sat/Sun) | Return empty list — no events scheduled |
| FMP_API_KEY missing | Log warning, return empty list (fail-open) |
| API rate limit exceeded | Sleep until window resets (same as earnings) |
| Malformed API response | Return empty list (fail-open) |
| DST transition | Handled automatically by zoneinfo |
| No events for date range | Return empty list (normal condition) |

---

## Pattern Consistency Check

| Pattern | Earnings Calendar | Economic Calendar | Match? |
|---------|-------------------|-------------------|--------|
| API key from env | `os.environ.get("FMP_API_KEY")` | Same | ✓ |
| Fail-open behavior | Returns `None` on failure | Returns `[]` | ✓ (equivalent) |
| Rate limiting | Simple internal tracker | Same 300 req/min | ✓ |
| In-memory caching | `self._cache: dict` | Same | ✓ |
| Timeout | `_REQUEST_TIMEOUT = 5` | Same | ✓ |
| Logging | `logging.getLogger(__name__)` | Same | ✓ |
| Dotenv loading | `load_dotenv()` | Same | ✓ |

---

*Next step: Implement when ready*
