# Post-Market Commentary Template

Standard format for daily post-market analysis delivered to Trading Sandbox.

---

## Template

```
📊 Post-Market Commentary — [Month DD, YYYY]

Market Close Verdict: [BEAR/BULL/NEUTRAL] CLOSE / [BEAR/BULL/NEUTRAL] REGIME
• SPY [+%] | QQQ [+%] | IWM [+%]
• [Regime assessment — how many signals positive/negative, key context]
• [Technical/breadth interpretation]

Notable Watchlist Movers (>|3%|):
🔴 Losers: [TICKER] [-X.XX%] ([context]), [TICKER] [-X.XX%], ...
🟢 Gainers: [TICKER] [+X.XX%] ([context]), [TICKER] [+X.XX%], ...

Tier 1 Setups Still Valid: [TICKER, TICKER, TICKER] ([observation])
Failed/Extended: [TICKER, TICKER, TICKER] — [reason]

Economic Calendar (Tomorrow [Month DD]):
• [HH:MM] — [Event Name] ([key detail])
• [HH:MM] — [Event Name] ([key detail])

Watchlist Earnings This Week:
• [TICKER] reports [Month DD] ([day]) [before/after] close — [importance/context]
• [Additional names...]

Action Items:

1. [Specific tactical action with ticker and reasoning]
2. [Specific tactical action with ticker and reasoning]
3. [Specific tactical action with ticker and reasoning]
4. [Risk management / broader market consideration]

Bottom line: [One-sentence summary of tactical stance]
```

---

## Usage

**Script:** `scripts/postmarket_report.py`  
**Delivery:** `scripts/deliver_report.py --chat-id -4872065090`

The post-market cron job runs this template at 4:10 PM ET daily. Results are posted to Trading Sandbox with full commentary.

---

## Section Guidelines

| Section | Content | Source |
|---------|---------|--------|
| Market Close Verdict | SPY/QQQ/IWM % moves + regime assessment | `yfinance` index data, regime scoring from `regime_utils.py` |
| Notable Movers | Watchlist names >3% daily move | `watchlist_manager.py` + `yfinance` daily data |
| Tier 1 Valid/Failed | Entry signal scan results | `entry_signals.py` output |
| Economic Calendar | Next 24-48h events | FMP API or manual lookup |
| Earnings This Week | Watchlist names reporting | FMP API earnings calendar |
| Action Items | 3-4 specific, actionable bullets | Derived from above |
| Bottom Line | One-sentence tactical summary | Synthesized verdict |

---

## Emoji Legend

| Emoji | Meaning |
|-------|---------|
| 🔴 | Losers / Risk-off / Caution |
| 🟢 | Gainers / Risk-on / Green |
| 🟡 | Neutral / Developing / Watch |
| 📊 | Report header |
| ⚠️ | Warning / Alert |
| 🎯 | Actionable setup |

---

## Example Output

See `reports/example_postmarket_commentary.txt` for filled example.
