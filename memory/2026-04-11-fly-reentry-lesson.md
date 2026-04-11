# Trading Lesson: Re-entering Losing Position (FLY Case Study)

**Date:** 2026-04-09 to 2026-04-10  
**Ticker:** FLY  
**Lesson:** Re-entering a losing position immediately after closing

---

## What Happened

FLY was traded twice in quick succession, both resulting in losses:

### Trade #1
- **Entry:** Apr 9, 11:00 @ $41.03 (120 shares)
- **Exit:** Apr 9, 13:15 @ $38.00
- **P&L:** -$363.60
- **Exit Reason:** EXTERNAL_CLOSE (manual/Alpaca initiated)

### Trade #2 (Re-entry)
- **Entry:** Apr 9, 13:17 @ $40.58 (120 shares) - **Only 2 minutes after close!**
- **Exit:** Apr 10, 15:28 @ $37.46
- **P&L:** -$405.60
- **Exit Reason:** STOP_HIT

**Total Loss:** -$769.20

---

## The Problem

The system re-entered FLY almost immediately (2 minutes) after the first position was closed at a loss. This is a common trading mistake:

1. **No cooling-off period** - Should wait before re-entering same ticker
2. **No reassessment** - Conditions hadn't changed, same setup failed twice
3. **Double loss** - Instead of one small loss, became two larger losses

---

## Recommendation for Future

Add safeguards to prevent immediate re-entry:

1. **Cooldown period** - Block re-entry of same ticker for X minutes after exit
2. **Daily signal limit** - Only one entry signal per ticker per day (already partially implemented)
3. **Loss review** - Require manual confirmation after losing trade on same ticker

---

## Related Implementation

- `paper_engine_alpaca.py` has `signaled_tickers` set that resets daily
- Consider extending to prevent re-entry within same session after loss
- Could add to risk configuration: `min_time_between_entries` or `block_after_loss`

---

**Status:** Documented for future risk rule enhancement
