#!/usr/bin/env python3
"""Scan watchlist for entry signals — report only, no execution."""

import argparse
import json
import sys
import time
from datetime import datetime, date as _date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).parent))

from traderlib.alpaca_client import AlpacaClient
from traderlib.earnings_calendar import EarningsCalendar
from traderlib import calculate_stage2_score, get_entry_score, get_stage2_details, calculate_ma_support_stop
from traderlib.risk_config import RiskConfigManager
from traderlib.trading_exceptions import TradingExceptionHandler
from traderlib.validation import validate_ticker, validate_tickers

# Configurable paths
DATA_DIR = Path(__file__).parent.parent / 'data'
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'
SCANS_DIR = Path(__file__).parent.parent / 'scans'

# ---------------------------------------------------------------------------
# Display constants & formatting helpers
# ---------------------------------------------------------------------------

_W = 84  # terminal width target

# Pivot source badge labels — shown after distance string
_SOURCE_LABEL: dict = {
    'manual':         'm',   # set explicitly in watchlist Pivot_Price column
    'vcp_contraction': 'v',  # derived from VCP contraction pattern
    'range_20d':      'r',   # 20-day high proxy (backtest default)
}


def _thick(char: str = '━') -> str:
    return char * _W


def _sec(label: str) -> str:
    """Section divider: '── LABEL ─────────────────────────────────────────'"""
    # emoji in label throw off len(); pad conservatively
    pad = max(_W - len(label) - 4, 2)
    return f"── {label} {'─' * pad}"


def _fmt_dist(d: Optional[float], source: str = 'none') -> str:
    """'+0.4%↑[m]' / '-1.2%↓' / '—' distance string.

    Returns '—' when no pivot is set (d is None).
    Appends source badge when source is in _SOURCE_LABEL.
    """
    if d is None:
        return '—'
    arrow = '↑' if d > 0 else '↓' if d < 0 else '→'
    badge = _SOURCE_LABEL.get(source, '')
    suffix = f'[{badge}]' if badge else ''
    return f"{'+' if d > 0 else ''}{d:.1f}%{arrow}{suffix}"


def _fmt_earnings(days: Optional[int]) -> str:
    """Compact earnings-proximity badge."""
    if days is None:
        return '—'
    if days <= 0:
        return '⛔ today'
    if days == 1:
        return '🚨 1d'
    if days <= 7:
        return f'⚠️ {days}d'
    if days <= 30:
        return f'📅 {days}d'
    return '—'


# ---------------------------------------------------------------------------
# Unified table renderer (same columns for every section)
# ---------------------------------------------------------------------------

_HDR = (
    f"  {'TICKER':<8} {'SCORE':<6} {'S2':<6} {'DIST':<10} "
    f"{'RISK%':<7} {'PRICE':<10} {'PIVOT':<10} EARNINGS"
)
_DIV = (
    f"  {'─'*8} {'─'*5} {'─'*5} {'─'*9} "
    f"{'─'*6} {'─'*9} {'─'*9} {'─'*8}"
)


def _row(a: Dict) -> str:
    days = a.get('earnings_days')
    s2_str    = f"{a['stage2']}/10"
    dist_str  = _fmt_dist(a.get('dist_to_pivot'), a.get('pivot_source', 'none'))
    price_str = f"${a['current']:.2f}"
    pv        = a.get('pivot')
    pivot_str = f"${pv:.2f}" if pv is not None else '—'
    earn_str  = _fmt_earnings(days)
    return (
        f"  {a['ticker']:<8} {a['entry_score']:<6.0f} {s2_str:<6} "
        f"{dist_str:<10} {a['risk_pct']:<7.1f} {price_str:<10} {pivot_str:<10} {earn_str}"
    )


def _print_section(icon: str, title: str, subtitle: str, entries: List[Dict]) -> None:
    if not entries:
        return
    print(f"\n{_sec(icon + ' ' + title)}")
    if subtitle:
        print(f"   {subtitle}")
    print(_HDR)
    print(_DIV)
    for a in entries:
        print(_row(a))


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class EntrySignalScanner:
    """Scan watchlist for tickers meeting entry criteria."""

    def __init__(self, mode: str = 'paper', risk_profile: str = None):
        self.mode = mode
        self.risk_manager = RiskConfigManager(profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()
        self.alpaca = AlpacaClient(mode=mode)
        self.spy_cache = {'date': None, 'return_6m': 0.0, 'price': None}
        self.earnings_calendar = EarningsCalendar()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _get_spy_return_6m(self) -> float:
        """6-month SPY return, cached per day."""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.spy_cache['date'] == today:
            return self.spy_cache['return_6m']
        try:
            spy_hist = self.alpaca.get_historical_bars('SPY')
            if spy_hist is not None and len(spy_hist) >= 130:
                current = spy_hist['Close'].iloc[-1]
                past = spy_hist['Close'].iloc[-130]
                ret_6m = ((current / past) - 1) * 100
                self.spy_cache = {'date': today, 'return_6m': ret_6m, 'price': current}
                return ret_6m
        except Exception:
            pass
        return 0.0

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Latest price from Alpaca (quote → historical fallback)."""
        try:
            price = self.alpaca.get_latest_price(ticker)
            if price:
                return price
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_quote", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
        try:
            hist = self.alpaca.get_historical_bars(ticker, days=5)
            if hist is not None and len(hist) > 0:
                return hist['Close'].iloc[-1]
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_hist", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
        return None

    def _check_market_conditions(self) -> Tuple[bool, str, str]:
        """Check SPY trend and VIX level.

        Returns:
            (entries_ok, spy_str, vix_str)
            e.g. (True, 'SPY +0.42%', 'VIX 18.3')
        """
        spy_str = 'SPY —'
        vix_str = ''

        try:
            hist = self.alpaca.get_historical_bars('SPY', days=5)
            if hist is not None and len(hist) >= 2:
                chg = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-2]) - 1) * 100
                spy_str = f"SPY {chg:+.2f}%"
                if chg < self.risk_config.market.max_spy_decline_pct:
                    return False, spy_str, vix_str
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "market_conditions", e,
                severity=TradingExceptionHandler.WARNING, ticker='SPY'
            )

        max_vix = self.risk_config.market.max_vix
        if max_vix is not None:
            try:
                import yfinance as yf
                vix_hist = yf.Ticker("^VIX").history(period="2d", auto_adjust=False)
                if not vix_hist.empty:
                    vix_current = float(vix_hist['Close'].iloc[-1])
                    vix_str = f"VIX {vix_current:.1f}"
                    if vix_current > max_vix:
                        return False, spy_str, vix_str
            except Exception:
                pass  # fail open

        return True, spy_str, vix_str

    # ------------------------------------------------------------------
    # Per-ticker analysis
    # ------------------------------------------------------------------

    def _analyze_ticker(self, ticker: str) -> Optional[Dict]:
        """Full analysis for one ticker. Returns None on data failure.

        Does NOT check earnings blackout — caller handles that so skipped
        tickers are tracked for display.
        """
        try:
            hist = self.alpaca.get_historical_bars(ticker)
            if hist is None or len(hist) < 30:
                return None

            current = self._get_current_price(ticker)
            if current is None:
                return None

            # Stage 2 scoring
            s2_details = get_stage2_details(hist)
            stage2 = s2_details['score']
            below_50ma = not s2_details['criteria']['price_above_50ma']
            below_20ma = not s2_details['criteria']['price_above_20ma']

            # Pivot & sector from watchlist
            pivot: Optional[float] = None
            pivot_source: str = 'none'
            sector = 'Unknown'
            try:
                df = pd.read_csv(WATCHLIST_PATH)
                row = df[df['Ticker'] == ticker]
                if not row.empty:
                    if 'Pivot_Price' in row.columns:
                        pv = row['Pivot_Price'].values[0]
                        if not pd.isna(pv):
                            pivot = float(pv)
                            pivot_source = 'manual'
                    if 'Sector' in row.columns:
                        sv = row['Sector'].values[0]
                        if not pd.isna(sv):
                            sector = str(sv)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "sector_lookup", e,
                    severity=TradingExceptionHandler.WARNING,
                    ticker=ticker, file=str(WATCHLIST_PATH)
                )

            # Fallback: 20-day range high as pivot proxy (mirrors backtest logic).
            # Ensures every ticker has a real distance-to-pivot for scoring and
            # section categorisation. Manual pivot takes priority when set.
            if pivot is None:
                pivot = float(hist['High'].tail(20).max())
                pivot_source = 'range_20d'

            ret_6m = 0.0
            if len(hist) >= 130:
                ret_6m = ((current / hist['Close'].iloc[-130]) - 1) * 100

            # ATR
            try:
                high_low   = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close  = abs(hist['Low']  - hist['Close'].shift())
                tr  = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = tr.rolling(14).mean().iloc[-1]
            except Exception:
                atr = current * 0.02

            atr_stop     = current - (2 * atr)
            # Risk is always measured from current price to stop (not pivot)
            atr_risk_pct = abs((current - atr_stop) / current) * 100 if atr_stop < current else 999.0

            # MA Support Stop
            ma_support_stop = None
            ma_risk_pct = None
            stop_type = 'ATR'
            if self.risk_config.ma_support.enabled:
                ma_result = calculate_ma_support_stop(
                    current, s2_details,
                    buffer_pct=self.risk_config.ma_support.buffer_pct,
                    cluster_spread_pct=self.risk_config.ma_support.cluster_spread_pct,
                    min_cluster_size=self.risk_config.ma_support.min_cluster_size
                )
                if ma_result:
                    ma_support_stop = ma_result['ma_support_stop']
                    ma_risk_pct = (
                        abs((current - ma_support_stop) / current) * 100
                        if ma_support_stop < current else 999.0
                    )

            # Use tighter (higher) stop
            if ma_support_stop and ma_support_stop > atr_stop:
                stop     = ma_support_stop
                risk_pct = ma_risk_pct
                stop_type = 'MA'
            else:
                stop     = atr_stop
                risk_pct = atr_risk_pct

            risk_per_share = current - stop
            target = current + (2 * risk_per_share) if risk_per_share > 0 else current * 1.04

            # dist_to_pivot: None when no pivot set (avoids phantom +25 proximity score)
            dist_to_pivot: Optional[float] = (
                ((pivot - current) / current) * 100 if pivot is not None else None
            )
            # 999.0 sentinel: get_entry_score will award 0 proximity points
            dist_for_scoring = dist_to_pivot if dist_to_pivot is not None else 999.0

            spy_return_6m = self._get_spy_return_6m()
            rs_6m = ret_6m - spy_return_6m

            entry_score = get_entry_score(
                stage2, risk_pct, dist_for_scoring, ret_6m, rs_6m,
                below_50ma=below_50ma, below_20ma=below_20ma
            )

            tier = (
                "Tier 1" if entry_score >= 60 and stage2 >= 8 else
                "Tier 2" if entry_score >= 40 and stage2 >= 6 else
                "Tier 3"
            )

            # Earnings proximity (already prefetched by scan())
            earnings_date = self.earnings_calendar.get_next_earnings(ticker)
            earnings_days = (earnings_date - _date.today()).days if earnings_date else None

            return {
                'ticker':          ticker,
                'current':         current,
                'pivot':           pivot,           # Optional[float] — None = not set
                'pivot_source':    pivot_source,    # 'manual' | 'vcp_contraction' | 'none'
                'stop':            stop,
                'target':          target,
                'sector':          sector,
                'stage2':          stage2,
                'entry_score':     entry_score,
                'tier':            tier,
                'dist_to_pivot':   dist_to_pivot,
                'risk_pct':        risk_pct,
                'atr_stop':        atr_stop,
                'atr_risk_pct':    atr_risk_pct,
                'ma_support_stop': ma_support_stop,
                'ma_risk_pct':     ma_risk_pct,
                'stop_type':       stop_type,
                'ret_6m':          ret_6m,
                'rs_6m':           rs_6m,
                'atr':             atr,
                'earnings_date':   earnings_date,
                'earnings_days':   earnings_days,
            }

        except Exception as e:
            TradingExceptionHandler.log_exception(
                "analyze_ticker", e,
                severity=TradingExceptionHandler.WARNING, ticker=ticker
            )
            return None

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------

    def _load_watchlist(self) -> List[str]:
        try:
            df = pd.read_csv(WATCHLIST_PATH)
            if 'Ticker' in df.columns:
                return df['Ticker'].tolist()
        except Exception as e:
            print(f"⚠️  Could not load watchlist: {e}")
        return []

    # ------------------------------------------------------------------
    # Main scan + dashboard
    # ------------------------------------------------------------------

    def scan(self, tickers: Optional[List[str]] = None, min_tier: int = 1) -> List[Dict]:
        """Scan for entry signals and print the dashboard."""
        if tickers is None:
            tickers = self._load_watchlist()
        if not tickers:
            print("⚠️  No tickers to scan")
            return []

        # Brief progress line (replaced by full dashboard output)
        print(f"  ⟳  Scanning {len(tickers)} tickers...", end='\r', flush=True)
        t_start = time.monotonic()

        # Prefetch all earnings in one pass before the scan loop
        self.earnings_calendar.prefetch(tickers)

        # Market conditions
        market_ok, spy_str, vix_str = self._check_market_conditions()

        entry_threshold = self.risk_config.entry.min_entry_score
        max_dist        = self.risk_config.entry.max_dist_to_pivot_pct
        today           = _date.today()

        # ---- Scan loop ------------------------------------------------
        blackout_tickers: List[str] = []
        all_analyses:     List[Dict] = []

        for ticker in tickers:
            if self.earnings_calendar.is_earnings_blackout(ticker, today):
                blackout_tickers.append(ticker)
                continue
            analysis = self._analyze_ticker(ticker)
            if analysis:
                all_analyses.append(analysis)

        t_elapsed = time.monotonic() - t_start

        # ---- Categorise -----------------------------------------------
        ready_now:     List[Dict] = []
        close_pivot:   List[Dict] = []
        extended:      List[Dict] = []
        near_earnings: List[Dict] = []   # score ≥40, earnings in 1–7 days
        tier2_watch:   List[Dict] = []
        tier3_skip:    List[Dict] = []

        for a in all_analyses:
            tier_num = int(a['tier'][-1])
            if tier_num > min_tier:
                continue

            days         = a.get('earnings_days')
            is_near_earn = days is not None and 1 <= days <= 7
            score_ok     = a['entry_score'] >= entry_threshold
            _dist        = a['dist_to_pivot']   # Optional[float]
            dist_ok      = _dist is not None and -max_dist <= _dist <= max_dist
            dist_close   = _dist is not None and abs(_dist) <= 3.0

            # Near-earnings tickers (score ≥40) get their own section
            # regardless of distance / score tier
            if is_near_earn and a['entry_score'] >= 40:
                near_earnings.append(a)
            elif score_ok and dist_ok:
                ready_now.append(a)
            elif score_ok and dist_close:
                close_pivot.append(a)
            elif score_ok:
                extended.append(a)
            elif a['entry_score'] >= 40:
                tier2_watch.append(a)
            else:
                tier3_skip.append(a)

        for lst in [ready_now, close_pivot, extended, near_earnings, tier2_watch, tier3_skip]:
            lst.sort(key=lambda x: x['entry_score'], reverse=True)

        signals = ready_now

        # ================================================================
        # Dashboard output
        # ================================================================

        et_now = datetime.now(pytz.timezone('US/Eastern'))
        ts_str = et_now.strftime('%a %b %-d  %H:%M  ET')

        # ---- Header block ----------------------------------------------
        print()
        print(_thick('━'))

        title_left  = "  🎯  ENTRY SIGNALS"
        # right-align timestamp (account for emoji width in title)
        right_pad = _W - len(title_left) - len(ts_str) + 1
        print(f"{title_left}{ts_str:>{right_pad}}")

        # Market status line
        if market_ok:
            mkt_parts = [spy_str]
            if vix_str:
                mkt_parts.append(vix_str)
            mkt_parts += [self.mode.capitalize(), f"{len(tickers)} tickers", f"{t_elapsed:.1f}s"]
            print("  " + "  │  ".join(mkt_parts))
        else:
            paused_parts = [f"⛔ Entries paused", spy_str]
            if vix_str:
                paused_parts.append(vix_str)
            paused_parts += [self.mode.capitalize(), f"{len(tickers)} tickers"]
            print("  " + "  │  ".join(paused_parts))

        print(_thick('━'))

        # ---- Summary bar ----------------------------------------------
        summary_parts = []
        if ready_now:      summary_parts.append(f"🔥 {len(ready_now)} Ready")
        if close_pivot:    summary_parts.append(f"⏳ {len(close_pivot)} Near Pivot")
        if extended:       summary_parts.append(f"📈 {len(extended)} Extended")
        if near_earnings:  summary_parts.append(f"⚠️  {len(near_earnings)} Near Earnings")
        if tier2_watch:    summary_parts.append(f"📊 {len(tier2_watch)} Tier 2")
        if blackout_tickers: summary_parts.append(f"📅 {len(blackout_tickers)} Blackout")
        if tier3_skip:     summary_parts.append(f"○ {len(tier3_skip)} Tier 3")

        if summary_parts:
            print()
            print("  " + "  ·  ".join(summary_parts))

        # ---- Sections --------------------------------------------------
        _print_section(
            "🔥", "READY NOW",
            f"score ≥{entry_threshold}, within ±{max_dist}%",
            ready_now
        )
        _print_section(
            "⏳", "NEAR PIVOT",
            f"score ≥{entry_threshold}, 1–3% from pivot",
            close_pivot
        )
        _print_section(
            "📈", "EXTENDED",
            f"score ≥{entry_threshold}, >3% from pivot  ([r] = 20d high proxy)",
            extended
        )

        if near_earnings:
            print(f"\n{_sec('⚠️  NEAR EARNINGS  (1–7d — hold off on new entries)')}")
            print(_HDR)
            print(_DIV)
            for a in near_earnings:
                # Append forced-exit note for 1-day cases
                if self.earnings_calendar.should_force_exit(a['ticker'], today):
                    print(_row(a) + "  ← paper engine exits today")
                else:
                    print(_row(a))

        _print_section(
            "📊", "TIER 2 WATCH",
            "score 40–59, developing setups",
            tier2_watch
        )

        if tier3_skip and min_tier >= 3:
            print(f"\n{_sec('○ TIER 3')}")
            print(_HDR)
            print(_DIV)
            for a in tier3_skip[:10]:
                print(_row(a))
            if len(tier3_skip) > 10:
                print(f"  ... and {len(tier3_skip) - 10} more")

        if blackout_tickers:
            print(f"\n{_sec('📅 EARNINGS BLACKOUT  (skipped today)')}")
            # Wrap long lists at _W chars
            line = "  "
            for t in blackout_tickers:
                entry = t + "  "
                if len(line) + len(entry) > _W:
                    print(line)
                    line = "  " + entry
                else:
                    line += entry
            if line.strip():
                print(line)

        if not any([ready_now, close_pivot, extended, near_earnings, tier2_watch]):
            print("\n  No qualifying setups found")

        # ---- Footer ----------------------------------------------------
        print()
        print(_thick('═'))
        profile_str = self.risk_manager.profile or 'default'
        print(
            f"  score ≥{entry_threshold}  ·  dist ≤±{max_dist}%  ·  "
            f"{self.mode}  ·  profile: {profile_str}"
        )
        print(f"  pivot src: [m]=manual  [v]=vcp  [r]=range20d  (—=no pivot set)")
        print(_thick('═'))
        print()

        return signals

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_signals(self, signals: List[Dict], format: str = 'csv'):
        if not signals:
            print("⚠️  No signals to export")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        SCANS_DIR.mkdir(parents=True, exist_ok=True)

        if format == 'csv':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.csv'
            df = pd.DataFrame(signals)
            df.to_csv(filepath, index=False)
            print(f"💾 Exported to: {filepath}")

        elif format == 'json':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.json'
            with open(filepath, 'w') as f:
                json.dump(signals, f, indent=2, default=str)
            print(f"💾 Exported to: {filepath}")

        elif format == 'html':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.html'
            self._export_html(signals, filepath)
            print(f"💾 Exported to: {filepath}")

    def _export_html(self, signals: List[Dict], filepath: Path):
        """Generate HTML report."""
        def _earn_html(days):
            s = _fmt_earnings(days)
            if s.startswith('🚨'):
                return f'<span style="color:#f87171">{s}</span>'
            if s.startswith('⚠️'):
                return f'<span style="color:#facc15">{s}</span>'
            if s.startswith('📅'):
                return f'<span style="color:#94a3b8">{s}</span>'
            return s

        def _rows(group: List[Dict], css_class: str) -> str:
            rows = []
            for s in group:
                earn_cell = _earn_html(s.get('earnings_days'))
                rows.append(
                    f'<tr class="{css_class}">'
                    f'<td>{s["ticker"]}</td>'
                    f'<td>{s["entry_score"]:.0f}</td>'
                    f'<td>${s["current"]:.2f}</td>'
                    f'<td>{"${:.2f}".format(s["pivot"]) if s.get("pivot") is not None else "—"}</td>'
                    f'<td>{"{:+.1f}%".format(s["dist_to_pivot"]) if s.get("dist_to_pivot") is not None else "—"}</td>'
                    f'<td>{s["risk_pct"]:.1f}%</td>'
                    f'<td>{s["stage2"]}/10</td>'
                    f'<td>{s["sector"]}</td>'
                    f'<td>{earn_cell}</td>'
                    f'</tr>'
                )
            return ''.join(rows)

        th = '<th>Ticker</th><th>Score</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>Sector</th><th>Earnings</th>'

        ready  = [s for s in signals if s['entry_score'] >= 60 and abs(s['dist_to_pivot']) <= 2]
        tier2  = [s for s in signals if 40 <= s['entry_score'] < 60]

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Entry Signals — {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        :root {{ --bg: #0f172a; --bg2: #1e293b; --fg: #f8fafc;
                --green: #4ade80; --yellow: #facc15; --red: #f87171; }}
        body {{ font-family: -apple-system, sans-serif; background: var(--bg);
               color: var(--fg); padding: 20px; }}
        h1 {{ border-bottom: 1px solid #334155; padding-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: var(--bg2); font-size: 0.85em; text-transform: uppercase;
              letter-spacing: .05em; }}
        .ready {{ color: var(--green); }}
        .t2    {{ color: var(--yellow); }}
    </style>
</head>
<body>
<h1>🎯 Entry Signals — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}</h1>

<h2>🔥 Ready Now</h2>
<table><tr>{th}</tr>{_rows(ready, 'ready')}</table>

<h2>📊 Tier 2 Watch</h2>
<table><tr>{th}</tr>{_rows(tier2, 't2')}</table>
</body></html>"""

        with open(filepath, 'w') as f:
            f.write(html)

    # ------------------------------------------------------------------
    # Single-ticker deep dive
    # ------------------------------------------------------------------

    def analyze_single(self, ticker: str) -> Optional[Dict]:
        """Deep analysis of one ticker (--ticker mode)."""
        print(f"\n🔍 Analyzing {ticker.upper()}...", flush=True)

        # Prefetch so the earnings lookup is available
        self.earnings_calendar.prefetch([ticker])

        analysis = self._analyze_ticker(ticker)
        if not analysis:
            print(f"❌ Could not analyze {ticker}")
            return None

        try:
            hist = self.alpaca.get_historical_bars(ticker, days=252)
            if hasattr(hist, 'empty') and not hist.empty and len(hist) >= 150:
                current = analysis['current']

                ret_1m = (current / hist['Close'].iloc[-20]  - 1) * 100
                ret_3m = (current / hist['Close'].iloc[-65]  - 1) * 100 if len(hist) >= 65  else 0.0
                ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0.0

                ma20  = hist['Close'].rolling(20).mean().iloc[-1]
                ma50  = hist['Close'].rolling(50).mean().iloc[-1]
                ma150 = hist['Close'].rolling(150).mean().iloc[-1]
                ma200 = hist['Close'].rolling(200).mean().iloc[-1]

                high_52w = hist['Close'].max()
                from_high = ((high_52w - current) / high_52w) * 100

                chk = lambda p, ma: '✓' if p > ma else '✗'
                above = (chk(current, ma20), chk(current, ma50),
                         chk(current, ma150), chk(current, ma200))

                score = analysis['stage2']
                status = '🟢' if score >= 6 else '🟡' if score >= 4 else '🔴'

                # Earnings badge
                earn_days = analysis.get('earnings_days')
                earn_date = analysis.get('earnings_date')
                if earn_days is not None and earn_days <= 30:
                    earn_str = f"{_fmt_earnings(earn_days)} ({earn_date})"
                elif earn_date:
                    earn_str = str(earn_date)
                else:
                    earn_str = '—'

                print(f"\n{ticker.upper()} — ${current:.2f}\n")
                print("| Metric | Value |")
                print("|:-------|:------|")
                print(f"| Sector | {analysis['sector']} |")
                print(f"| 1M Return | {ret_1m:+.1f}% |")
                print(f"| 3M Return | {ret_3m:+.1f}% |")
                print(f"| 6M Return | {ret_6m:+.1f}% |")
                print(f"| Stage 2 Score | {score}/10 {status} |")
                print(f"| From 52W High | {from_high:.1f}% |")
                print(f"| Above MAs | {above[0]} {above[1]} {above[2]} {above[3]}  20/50/150/200 |")
                print(f"| Next Earnings | {earn_str} |")

                print(f"\n---\n\nENTRY SETUP\n")
                print("| Level | Price |")
                print("|:------|:------|")
                _pv = analysis.get('pivot')
                _src = analysis.get('pivot_source', 'none')
                _src_badge = f' [{_SOURCE_LABEL[_src]}]' if _src in _SOURCE_LABEL else ''
                pivot_display = f"${_pv:.2f}{_src_badge}" if _pv is not None else '— (no pivot set)'
                print(f"| Pivot | {pivot_display} |")
                print(f"| Stop | ${analysis['stop']:.2f} ({analysis['stop_type']}) |")
                print(f"| Target | ${analysis['target']:.2f} |")
                print(f"| Risk % | {analysis['risk_pct']:.1f}% |")
                print(f"| ATR Stop | ${analysis['atr_stop']:.2f} ({analysis['atr_risk_pct']:.1f}%) |")
                if analysis.get('ma_support_stop'):
                    print(f"| MA Stop | ${analysis['ma_support_stop']:.2f} ({analysis['ma_risk_pct']:.1f}%) |")

                if score >= 7 and analysis['risk_pct'] < 10:
                    verdict = "🟢 A-TIER — Strong setup. Watch for volume-confirmed breakout."
                elif score >= 6:
                    verdict = "🟡 TIER B — Developing. Promote to A on breakout."
                elif score >= 5:
                    verdict = "🔵 TIER C — On radar, monitor for improvement."
                else:
                    verdict = "⚪ PASS — Below Stage 2 criteria."

                print(f"\n**Verdict:** {verdict}")
                return analysis

        except Exception as e:
            print(f"⚠️  Error getting additional data: {e}")

        return analysis


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Scan watchlist for entry signals or analyze single ticker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 entry_signals.py                    # Scan full watchlist
  python3 entry_signals.py --ticker AAPL      # Deep dive single ticker
  python3 entry_signals.py --export-csv       # Scan and export to CSV
  python3 entry_signals.py --export-html      # Scan and export to HTML
        """
    )
    parser.add_argument('--tickers', '-t', nargs='+',
                        help='Specific tickers to scan (default: watchlist)')
    parser.add_argument('--ticker',
                        help='Analyze single ticker in detail')
    parser.add_argument('--min-tier', '-m', type=int, choices=[1, 2, 3], default=3,
                        help='Minimum tier (1=T1 only, 2=T1+T2, 3=All)')
    parser.add_argument('--export', '-e', choices=['csv', 'json', 'none'], default='none',
                        help='Export format')
    parser.add_argument('--export-csv',  action='store_true', help='Export to CSV')
    parser.add_argument('--export-html', action='store_true', help='Export to HTML')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                        help='Alpaca mode (default: paper)')
    parser.add_argument('--risk-profile', default=None,
                        help='Risk profile (conservative, aggressive, tight_stops)')

    args = parser.parse_args()

    if args.ticker:
        try:
            ticker = validate_ticker(args.ticker)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
        scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile)
        result = scanner.analyze_single(ticker)
        return 0 if result else 1

    if args.tickers:
        try:
            validated_tickers = validate_tickers(args.tickers)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
    else:
        validated_tickers = None

    scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile)
    signals = scanner.scan(tickers=validated_tickers, min_tier=args.min_tier)

    export_format = args.export
    if args.export_csv:
        export_format = 'csv'
    elif args.export_html:
        export_format = 'html'

    if export_format != 'none' and signals:
        scanner.export_signals(signals, format=export_format)

    return 0 if signals else 1


if __name__ == "__main__":
    sys.exit(main())
