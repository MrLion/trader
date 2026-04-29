# Pre-Market Commentary Template

Standard format for daily pre-market analysis delivered to Trading Sandbox.

---

## Template

```
🌅 Pre-Market Commentary — [Month DD, YYYY]

Overnight Verdict: [BULLISH/BEARISH/NEUTRAL] FUTURES
• /ES [%] | /NQ [%] | /RTY [%] | VIX [level] ([+/-] vs prior)
• [Asia/Europe summary — what moved markets overnight]
• [Key event from overseas session]

Regime Status: [BULL/NEUTRAL/BEAR] STRUCTURE / [BULL/BEAR] OVERNIGHT BIAS
• [%] of signals positive — [specifics: 50MA alignment, breadth, etc.]
• Futures [confirming/contradicting] structural trend

Pre-Market Gaps & Movers (>|2%|):
🔴 Down: TICKER -X.XX% (context), TICKER -X.XX%, ...
🟢 Up: TICKER +X.XX% (context), TICKER +X.XX%, ...
• Expected volatility: [expanding/contracting] — [reason]

Developing Setups — Closest to Trigger:
🎯 1. TICKER — $X.XX pivot (Y% away) — [notes]
🎯 2. TICKER — $X.XX pivot (Y% away) — [notes]
🎯 3. TICKER — $X.XX pivot (Y% away) — [notes]

Economic Calendar (Today [Month DD]):
⏰ [HH:MM] — Event Name — IMPACT: [HIGH/MED/LOW] — [time until alert]
• [additional events...]

Earnings Today:
• TICKER [before/after] close — Exp move: ±X% — Guidance: [reduce/size normally]
• [additional names...]

Action Items:

1. [Specific entry trigger with price and reasoning]
2. [Risk management action with ticker and reasoning]
3. [Timing/execution guidance]
4. [Scenario to watch]

Bottom line: [One-sentence tactical stance for the session]
```

---

## Usage

**Script:** `scripts/premarket_report_comprehensive.py`  
**Delivery:** `scripts/deliver_report.py --chat-id -4872065090`

The pre-market cron job runs this template at 9:05 AM ET weekdays. Results are posted to Trading Sandbox with full commentary.

---

## Key Differences from Post-Market

| Aspect | Post-Market | Pre-Market |
|--------|-------------|------------|
| **Focus** | What happened / what failed | What's setting up / what's actionable |
| **Mover threshold** | >\|3%\| | >\|2%\| (pre-market thinner) |
| **Time orientation** | Backward | Forward |
| **Data source** | Closing prices, day's breadth | Futures, overnight news, pre-market gaps |
| **Unique sections** | Tier 1 valid/failed | Closest-to-trigger, overnight bias |
| **Action items** | Review/reassess | Execute/alert/prepare |

---

## Section Guidelines

| Section | Content | Source |
|---------|---------|--------|
| Overnight Verdict | /ES, /NQ, /RTY futures moves, VIX level | Yahoo Finance futures data |
| Regime Status | Structural regime + overnight bias confirmation | `regime_utils.py` + futures comparison |
| Pre-Market Gaps | Watchlist names >2% pre-market | `yfinance` pre-market data |
| Developing Setups | Closest to pivot triggers | `entry_signals.py` distance-to-pivot ranking |
| Economic Calendar | Today's events with impact ratings | FMP API or manual lookup |
| Earnings Today | Watchlist names reporting | FMP API earnings calendar |
| Action Items | 4 specific, actionable bullets | Derived from above |
| Bottom Line | One-sentence tactical summary | Synthesized verdict |

---

## Emoji Legend

| Emoji | Meaning |
|-------|---------|
| 🌅 | Pre-market header |
| 🔴 | Losers / Risk-off / Caution |
| 🟢 | Gainers / Risk-on / Green |
| 🟡 | Neutral / Developing / Watch |
| 🎯 | Actionable setup / trigger |
| ⏰ | Time-sensitive / Event |
| ⚠️ | Warning / Alert |
