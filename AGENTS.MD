# AGENTS.md - AI Assistant Instructions & Trading Reference

**Purpose:** Operational instructions for AI assistants working in this repository. Also contains the complete trading playbook (daily rhythm, entry protocol, risk rules, exit management).

**Audience:** AI assistants (primary). Human traders can reference the trading sections directly.

This folder is home. Treat it that way.

## First Run
If `BOOTSTRAP.md` exists, follow it, figure out who you are, then delete it.

## Session Startup
Before doing anything else:
1. Read `SOUL.md` — who you are
2. Read `USER.md` — who you're helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
4. **If in MAIN SESSION** (direct chat): Also read `MEMORY.md`

Don't ask permission. Just do it.

## Memory
You wake up fresh each session. Files are your continuity:
- **Daily notes:** `memory/YYYY-MM-DD.md` — raw logs of what happened
- **Long-term:** `MEMORY.md` — curated memories, only loaded in main sessions (not shared/group contexts for security)
- **No "mental notes"** — if you want to remember it, WRITE IT TO A FILE. Text > Brain.
- Periodically review daily files and distill into MEMORY.md during heartbeats.

## Red Lines
- Don't exfiltrate private data. `trash` > `rm`. When in doubt, ask.
- **Safe freely:** Read files, explore, search web, check calendars, work in workspace.
- **Ask first:** Sending emails/tweets/public posts, anything leaving the machine.

## Group Chats
You're a participant — not their voice, not their proxy. Respond when mentioned, when you add real value, or something witty fits. Stay silent (HEARTBEAT_OK) for casual banter, already-answered questions, or "yeah/nice" responses. One thoughtful response beats three fragments. React with emojis when a full reply isn't needed (one per message max).

## Tools
Check skill `SKILL.md` files when needed. Keep local notes in `TOOLS.md`.
- **Voice:** Use `sag` (ElevenLabs TTS) for stories/summaries when available.
- **Discord/WhatsApp:** No markdown tables — use bullet lists. Wrap links in `<>` to suppress embeds. WhatsApp: no headers, use **bold** or CAPS.
- **Forbidden:** peekaboo (restricted for security — stop and apologize if attempted).

## Heartbeats
Use heartbeats productively — don't just reply HEARTBEAT_OK. Default prompt: `Read HEARTBEAT.md if it exists. Follow strictly. If nothing needs attention, reply HEARTBEAT_OK.`

**Use heartbeat for:** batched checks (inbox + calendar + notifications), conversational context needed, approximate timing OK.
**Use cron for:** exact timing, isolated tasks, different model/thinking level, one-shot reminders, direct channel output.

**Rotate checks 2–4x/day:** emails, calendar (next 24–48h), mentions, weather. Track in `memory/heartbeat-state.json`. Reach out for important emails, upcoming events (<2h), interesting finds, or >8h silence. Stay quiet late night (23:00–08:00), when human is busy, or nothing new.

**Proactive work without asking:** organize memory files, check projects (git status), update docs, commit/push changes, review and update MEMORY.md.

## Make It Yours
This is a starting point. Add conventions, style, and rules as you figure out what works.

---

## Sectors & ETFs — Quick Reference

### Sector Dashboard

- **The latest sector scan is located in 'scans/YYYY-MM-DD_sector_scan.csv'

Read this file to provide the latest analytics.


### Factor & Signal ETFs
- **Momentum:** MTUM (outperforming SPY = your edge is working)
- **Low Vol:** SPLV/USMV (leading = risk-off, reduce exposure)
- **Growth vs Value:** IWF vs VLUE (growth leading = press momentum book)
- **Small Cap:** IWM/IWO (leading = broad risk appetite; lagging = narrowing leadership)
- **Credit:** HYG/JNK (declining = credit stress, leading equity weakness)
- **Bonds:** TLT (rallying = flight to safety); TIP (rising = inflation expectations)
- **International:** EFA, EEM, FXI, EWJ, INDA, EWT, KWEB
- **Commodities:** GLD, SLV, USO, UNG, DBC

### Sector Rotation Rules
1. **Daily:** Rank sector ETFs by 1w and 1m relative perf vs SPY. Concentrate watchlist in top 3.
2. **Weekly:** Compare cap-weighted vs equal-weight (XLK vs RSPT). If diverging, move is mega-cap driven, not broad.
3. **Rotation signals:** Staples/Utils/HC → Tech/Disc/Ind = risk-on. Reverse = risk-off. Energy+Materials leading = inflationary. Financials leading = steepening curve, early-cycle.

---

## Daily Operating Rhythm

### Pre-Market (6:00–9:30 ET)
1. **Regime (5 min):** Futures (/ES, /NQ, /RTY, /YM, /CL, BTC-USD, /GC), VIX, Asia/Europe. Update regime scorecard.
2. **Calendar (5 min):** FOMC/CPI/PPI/jobs/earnings. Flag held positions reporting within 5 days.
3. **Gap Scan (10 min):** Stocks gapping >3% on >2x volume. Filter: on watchlist? Stage 2? Legitimate catalyst? Max 3 day-trade candidates.
4. **Watchlist (15 min):** Walk A-tier setups. Pivot closer? Volume drying up? Top 3–5 actionable with exact trigger/stop/size. Set alerts.
5. **Portfolio (10 min):** Overnight gaps in held names. Portfolio heat check. Trailing stop pre-sets. Trim extended positions (>20% from entry).

### Market Hours (9:30–4:00 ET)
- **First 15 min:** No swing entries. Day trade opening ranges form. Watch for shakeout reversals.
- **10:00–3:00:** Execute planned entries per protocol. Monitor positions passively at 10:00, 12:00, 2:30. Evaluate day trades by 3:00.
- **Last 30 min:** Watch close quality (upper/lower 25% of range). Close all day trades. Flag weak closes for next-day review.

### Post-Market (4:00–5:00 ET)
1. **Log:** All trades taken and not taken. Closed trade P&L/R-multiple. Open trade updates.
2. **Scan:** Run screener. Check AH gaps. Move names between tiers.
3. **Breadth log:** A/D ratio, NH-NL, % above 20/50/200 SMA, up/down volume ratio.

---

## Watchlist Management

**Universe Filter:** Price ≥ $30, avg daily $ vol ≥ $150M, mkt cap ≥ $1B, NYSE/NASDAQ only.

**Stage 2:** Price > 100 SMA > 200 SMA, 200 SMA slope up ≥1 month, price ≥ 1.25× 52w low, price within 25% of 52w high.

**RS Filter:** 6-month return top 20% of universe. RS line at/near new highs.

**Volume:** ≥1 day in last 10 with vol >1.5x avg on up days. Volume contraction during base.

**Tiers:** A (5 max, actionable 1–3 days) → B (10 max, developing) → C (15 max, radar only).

**Remove if:** Breaks below 200 SMA, RS 3-month low, base fails on heavy volume, >6 weeks no development, sector turns negative.

---

## Entry Protocol

```
1. TRIGGER: Price breaks above pivot. Within 1-2% of buy point. >3% past = PASS.
2. VOLUME: Tracking ≥1.5x 50d avg. Formula: (vol / min elapsed) × 390. Below avg = PASS or half size.
3. MARKET: SPY/QQQ green or ≤0.3% down → proceed. Down >0.5% → only if RS independent. Bear regime → no longs.
4. RISK CALC:
   Risk/share = Entry - Stop
   Account risk = 0.75% equity (0.50% Neutral, 1.00% strong Bull)
   Shares = Account risk / Risk per share
   Confirm: position < 20% of equity, sector < 3 positions
5. EXECUTE: Limit buy. IMMEDIATELY place stop-market. Stop goes in before anything else.
6. LOG: Ticker, date, setup, sector, entry, stop, shares, risk$, target, R/R.
```

---

## Exit & Position Management

**Stops:** Set at entry, NEVER moved lower. Logical levels only: VCP = below last contraction low. MA pullback = below MA + 0.5% buffer. Flat base = below base midpoint. Gap-and-Go = below OR low or VWAP.

**Trailing progression:** Entry→+1R: hold initial stop. +1R: move to breakeven. +1.5–2R: trail 10 EMA daily. +3R+: widen to 21 EMA. +5R/30%+: sell 1/3, trail rest with 21 EMA or 10-week MA.

**Profit-taking:** Min 2R target. Trim into strength, not weakness. Don't sell tight consolidation above rising MAs. Sell all on climax: largest single-day gain, exhaustion gap, blow-off volume (3x+ avg, wide range, lower-half close).

**Time exits:** No progress 5–8 days → reassess. Flat within 2% and dead volume → sell. Exception: tight flag pattern → give up to 15 days.

**Pyramiding:** Only add to winners (+0.5R min), on pullbacks to support, smaller or equal size, max 2 adds. Recalculate blended entry and stop.

**De-risking triggers:** Bull→Neutral: reduce to 50%, sell weakest first. Bear: 0–20% or flat. Heat at 6%: no new positions. 3 consecutive stops: half size for next 3 trades. Weekly DD >3%: halt entries rest of week. Sector ETF breaks 50 SMA: review all sector holdings.

---

## Day Trading — Special Rules

**Activation (ALL true):** Bull or strong Neutral regime. Clear catalyst. On watchlist or high-liquidity name. Under 1% daily loss limit. Minimal swing risk to manage.

**Rules:** Max 2/day. Min 2:1 R/R. Defined trigger required. Stop immediately. Exit via target or trail (VWAP / 5m 20 EMA). Not working by 11:30 → close. All closed by 3:50 unless converting to swing. Track P&L separately.

---

## Journaling

**Per-trade:** Date, ticker, setup type (VCP/Pullback/Flat Base/PEG/Gap-and-Go), direction, regime, entry, stop, target, shares, risk$/%, R/R, trigger/volume/market confirmation Y/N, entry quality 1–5. Exit: date, price, P&L, R-multiple, holding period, exit reason, notes, lesson, chart screenshots.

**Weekly (Sunday, 30 min):** Performance (P&L, win rate, avg R, expectancy). Best/worst trades. Regime call accuracy. Sector rotation review. Watchlist quality. Upcoming catalysts.

**Monthly (1st Sunday, 60 min):** Equity curve. Setup-level stats. Sector P&L attribution. Behavioral/risk audit. Goal check.

---

## Data & Alerts

**Feeds:** Price/volume (Alpaca API for real-time + yfinance for historical), breadth (Stockbee/custom), RS rankings (custom, weekly), sector ETFs (daily), factor ETFs (daily), credit/bonds (daily), earnings cal (weekly), econ cal (daily).

**Scans:** Run via scripts — `entry_signals.py` (watchlist entry signals), `sector_scan_comprehensive.py` (131-ETF sector ranking). See TOOLS.md for details.

**Alerts:** Price at pivots (A-tier). Volume >2x pace by 10:30. Stop early-warning (0.5% above). Regime: SPY crossing 50 SMA, breadth thresholds. Sector ETF crossing 50 SMA. SPLV outperforming MTUM on 5d rolling.

---

## Communication

**Trade alert:** Ticker, sector (ETF rank), setup, entry, stop, risk/share, shares, position size, targets, R/R, regime, market context, sector exposure count.

**Daily summary:** Positions count, % invested, portfolio heat, day/week P&L. Sector exposure breakdown. Sector leadership ranks. Trades today. Open positions (R-multiple, day count, trail status). Watchlist moves. Regime + breadth + factor check. Notes.

**Templates:** Use standardized formats in `docs/templates/` for pre-market and post-market commentary.
