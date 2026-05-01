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

sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.alpaca_client import AlpacaClient
from traderlib.earnings_calendar import EarningsCalendar
from traderlib.risk_config import RiskConfigManager
from traderlib.ticker_analyzer import TickerAnalyzer, TickerAnalysis
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
    'manual':          'm',   # set explicitly in watchlist Pivot_Price column
    'vcp':             'v',   # volatility contraction pattern
    'range_20d':       'r',   # 20-day high proxy (backtest default)
    'pocket_pivot':    'p',   # pocket pivot volume spike
    'vcp_fallback':    'v',   # vcp requested but not found, using fallback
    'pocket_pivot_fallback': 'p',  # pocket pivot requested but not found
    'range_20d_fallback': 'r',  # range_20d requested but not found (edge case)
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

def _fmt_entry_stop(a: Dict) -> str:
    """Format ENTRY → STOP (TYPE) cluster."""
    price = a['current']
    stop = a.get('stop')
    stop_type = a.get('stop_type', '—')
    if stop is not None:
        return f"${price:.2f} → ${stop:.2f} {stop_type}"
    return f"${price:.2f} → —"


_HDR = (
    f"  {'TICKER':<8} {'SCORE':<6} {'S2':<6} {'DIST':<10} "
    f"{'ENTRY → STOP':<28} {'RISK':<6} EARNINGS"
)
_DIV = (
    f"  {'─'*8} {'─'*5} {'─'*5} {'─'*9} "
    f"{'─'*28} {'─'*6} {'─'*8}"
)


def _row(a: Dict) -> str:
    days = a.get('earnings_days')
    s2_str    = f"{a['stage2']}/10"
    dist_str  = _fmt_dist(a.get('dist_to_pivot'), a.get('pivot_type', 'none'))
    entry_stop_str = _fmt_entry_stop(a)
    earn_str  = _fmt_earnings(days)
    risk_str  = f"{a['risk_pct']:.1f}%"
    return (
        f"  {a['ticker']:<8} {a['entry_score']:<6.0f} {s2_str:<6} "
        f"{dist_str:<10} {entry_stop_str:<28} {risk_str:<6} {earn_str}"
    )


def _print_section(icon: str, title: str, criteria: str, entries: List[Dict]) -> None:
    if not entries:
        return
    # Inline count with criteria: "🔥 READY NOW  (2)  score≥60 · within ±3%"
    count_str = f"({len(entries)})" if len(entries) > 0 else ""
    header = f"{icon} {title}"
    if count_str:
        header = f"{header}  {count_str}"
    if criteria:
        header = f"{header}    {criteria}"
    print(f"\n{_sec(header)}")
    print(_HDR)
    print(_DIV)
    for a in entries:
        print(_row(a))


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class EntrySignalScanner:
    """Scan watchlist for tickers meeting entry criteria."""

    def __init__(self, mode: str = 'paper', risk_profile: str = None,
                 pivot_mode: str = 'auto'):
        self.mode = mode
        self.risk_manager = RiskConfigManager(profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()
        self.alpaca = AlpacaClient(mode=mode)
        self.analyzer = TickerAnalyzer(self.alpaca, self.risk_config, WATCHLIST_PATH)
        self.earnings_calendar = EarningsCalendar()
        self.pivot_mode = pivot_mode

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------

    def _load_tickers_from_source(self, source: Optional[str] = None) -> List[str]:
        """Load tickers from a file path, universe profile, or fallback to default watchlist."""
        if source is None:
            source = str(WATCHLIST_PATH)

        path = Path(source)

        # Case 1: Explicit file path
        if path.suffix in ('.csv', '.txt'):
            if not path.exists():
                print(f"❌ Watchlist file not found: {source}")
                return []
            try:
                if path.suffix == '.csv':
                    df = pd.read_csv(path)
                    if 'Ticker' in df.columns:
                        return df['Ticker'].dropna().astype(str).str.upper().tolist()
                    print(f"⚠️  No 'Ticker' column in {source}")
                    return []
                else:
                    # Plain text: one ticker per line
                    return [line.strip().upper() for line in path.read_text().splitlines() if line.strip()]
            except Exception as e:
                print(f"⚠️  Could not load {source}: {e}")
                return []

        # Case 2: Universe profile shorthand (e.g., "large_cap", "high_octane")
        universe_dir = DATA_DIR / 'universes'
        if not path.exists() and source.replace('-', '_') not in ('.', '/'):
            profile = source.replace('-', '_')
            pattern = f"{profile}_*.csv"
            matches = sorted(universe_dir.glob(pattern))
            if matches:
                latest = matches[-1]  # Glob is sorted lexicographically; YYYY-MM-DD works
                print(f"  📁 Using universe: {latest.name}")
                df = pd.read_csv(latest)
                if 'Ticker' in df.columns:
                    return df['Ticker'].dropna().astype(str).str.upper().tolist()
                # Fallback: first column if no 'Ticker' header
                return df.iloc[:, 0].dropna().astype(str).str.upper().tolist()

        # Case 3: Fallback to default watchlist
        try:
            df = pd.read_csv(WATCHLIST_PATH)
            if 'Ticker' in df.columns:
                return df['Ticker'].dropna().astype(str).str.upper().tolist()
        except Exception as e:
            print(f"⚠️  Could not load default watchlist: {e}")
        return []

    def _load_watchlist(self) -> List[str]:
        """Legacy method — delegates to _load_tickers_from_source."""
        return self._load_tickers_from_source()

    # ------------------------------------------------------------------
    # Main scan + dashboard
    # ------------------------------------------------------------------

    def scan(self, tickers: Optional[List[str]] = None, min_tier: int = 1,
             source: Optional[str] = None,
             pivot_mode: Optional[str] = None) -> List[Dict]:
        """Scan for entry signals and print the dashboard."""
        if tickers is None:
            tickers = self._load_tickers_from_source(source)
        if not tickers:
            print("⚠️  No tickers to scan")
            return []

        # Brief progress line (replaced by full dashboard output)
        print(f"  ⟳  Scanning {len(tickers)} tickers...", end='\r', flush=True)
        t_start = time.monotonic()

        # Prefetch all earnings in one pass before the scan loop
        self.earnings_calendar.prefetch(tickers)

        # Market conditions
        market_ok, spy_str, vix_str = self.analyzer.check_market_conditions()

        entry_threshold = self.risk_config.entry.min_entry_score
        max_dist        = self.risk_config.entry.max_dist_to_pivot_pct
        today           = _date.today()

        # ---- Scan loop ------------------------------------------------
        blackout_tickers: List[str] = []
        all_analyses:     List[Dict] = []

        technique = pivot_mode or self.pivot_mode
        for ticker in tickers:
            if self.earnings_calendar.is_earnings_blackout(ticker, today):
                blackout_tickers.append(ticker)
                continue
            result = self.analyzer.analyze(ticker, technique=technique)
            if result:
                analysis = result.to_dict()
                earnings_date = self.earnings_calendar.get_next_earnings(ticker)
                earnings_days = (earnings_date - _date.today()).days if earnings_date else None
                analysis['earnings_date'] = earnings_date
                analysis['earnings_days'] = earnings_days
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

        # ---- Section counts inline (shown in section headers) -----------

        # ---- Sections --------------------------------------------------
        _print_section(
            "🔥", "READY NOW",
            f"score≥{entry_threshold} · dist≤±{max_dist}%",
            ready_now
        )
        _print_section(
            "⏳", "NEAR PIVOT",
            f"score≥{entry_threshold} · dist 3–5%",
            close_pivot
        )
        _print_section(
            "📈", "EXTENDED",
            f"score≥{entry_threshold} · dist>5%",
            extended
        )

        if near_earnings:
            count_str = f"({len(near_earnings)})"
            print(f"\n{_sec(f'⚠️  NEAR EARNINGS  {count_str}  1–7d · hold off on new entries')}")
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
            "score 40–59 · developing setups",
            tier2_watch
        )

        if tier3_skip and min_tier >= 3:
            count_str = f"({len(tier3_skip)})"
            print(f"\n{_sec(f'○ TIER 3  {count_str}  score<40 · early stage')}")
            print(_HDR)
            print(_DIV)
            for a in tier3_skip[:10]:
                print(_row(a))
            if len(tier3_skip) > 10:
                print(f"  ... and {len(tier3_skip) - 10} more")

        if blackout_tickers:
            count_str = f"({len(blackout_tickers)})"
            print(f"\n{_sec(f'📅 EARNINGS BLACKOUT  {count_str}  skipped today')}")
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
        # Two-line footer: legend on left, mode/profile on right
        print(f"  [m]=manual  [v]=vcp  [r]=range20d  [p]=pocket_pivot")
        print(f"  score≥{entry_threshold} · dist≤±{max_dist}% · {self.mode} · profile: {profile_str}")
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

    def analyze_single(self, ticker: str, pivot_mode: Optional[str] = None) -> Optional[Dict]:
        """Deep analysis of one ticker (--ticker mode)."""
        print(f"\n🔍 Analyzing {ticker.upper()}...", flush=True)

        # Prefetch so the earnings lookup is available
        self.earnings_calendar.prefetch([ticker])

        technique = pivot_mode or self.pivot_mode
        result = self.analyzer.analyze(ticker, technique=technique)
        if not result:
            print(f"❌ Could not analyze {ticker}")
            return None

        analysis = result.to_dict()
        earnings_date = self.earnings_calendar.get_next_earnings(ticker)
        earnings_days = (earnings_date - _date.today()).days if earnings_date else None
        analysis['earnings_date'] = earnings_date
        analysis['earnings_days'] = earnings_days

        try:
            hist = self.alpaca.get_historical_bars(ticker)
            if hasattr(hist, 'empty') and not hist.empty and len(hist) >= 200:
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
                _src = analysis.get('pivot_type', 'none')
                _src_badge = f' [{_SOURCE_LABEL[_src]}]' if _src in _SOURCE_LABEL else ''
                pivot_display = f"${_pv:.2f}{_src_badge}" if _pv is not None else '— (no pivot set)'
                print(f"| Pivot | {pivot_display} |")

                # Entry Stop: the actual stop you enter with, annotated with type
                _stop = analysis['stop']
                _stop_type = analysis['stop_type']
                _pivot = analysis.get('pivot')
                if _pivot and _pivot > 0 and _stop < _pivot:
                    _pivot_rel = abs((_pivot - _stop) / _pivot) * 100
                    _stop_anno = f"{_stop_type}, {_pivot_rel:.1f}% below pivot"
                else:
                    _stop_anno = _stop_type
                print(f"| Entry Stop | ${_stop:.2f} ({_stop_anno}) |")

                print(f"| Target | ${analysis['target']:.2f} |")
                print(f"| Risk from Current | {analysis['risk_pct']:.1f}% |")

                # Raw ATR: pre-override intermediate value, not the final stop
                _atr_risk = analysis.get('atr_risk_pct')
                atr_risk_str = f"{_atr_risk:.1f}% below current" if _atr_risk is not None else "N/A"
                print(f"| Raw ATR | ${analysis['atr_stop']:.2f} ({atr_risk_str}) |")

                if analysis.get('ma_support_stop'):
                    _ma_risk = analysis.get('ma_risk_pct')
                    ma_risk_str = f"{_ma_risk:.1f}% below current" if _ma_risk is not None else "N/A"
                    print(f"| Raw MA | ${analysis['ma_support_stop']:.2f} ({ma_risk_str}) |")

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
  python3 entry_signals.py                    # Scan default watchlist
  python3 entry_signals.py --tickers AAPL     # Deep dive single ticker
  python3 entry_signals.py --tickers AAPL TSLA NVDA
  python3 entry_signals.py --watchlist scans/custom.csv
  python3 entry_signals.py --universe high_octane --export-csv
  python3 entry_signals.py --use-universe --min-tier 1
  python3 entry_signals.py --export-html      # Scan and export to HTML
        """
    )
    parser.add_argument('--tickers', '-t', nargs='+',
                        help='Specific tickers to scan (default: watchlist)')
    parser.add_argument('--watchlist', '-w', type=str,
                        help='Path to custom watchlist CSV or TXT file')
    parser.add_argument('--universe', '-u', type=str,
                        help='Universe profile name (e.g., large_cap, high_octane). '
                             'Auto-resolves to latest file in data/universes/')
    parser.add_argument('--use-universe', action='store_true',
                        help='Use the latest large_cap universe (shorthand for --universe large_cap)')
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
    parser.add_argument('--pivot-mode', choices=['auto', 'range_20d', 'vcp', 'pocket_pivot'],
                        default='auto',
                        help='Pivot detection technique (default: auto)')

    args = parser.parse_args()

    if args.tickers:
        try:
            validated_tickers = validate_tickers(args.tickers)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
        if len(validated_tickers) == 1:
            scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile,
                                         pivot_mode=args.pivot_mode)
            result = scanner.analyze_single(validated_tickers[0])
            return 0 if result else 1
    else:
        validated_tickers = None

    # Resolve ticker source: --watchlist > --universe > --use-universe > default
    source = None
    if args.watchlist:
        source = args.watchlist
    elif args.universe:
        source = args.universe
    elif args.use_universe:
        source = 'large_cap'

    scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile,
                                 pivot_mode=args.pivot_mode)
    signals = scanner.scan(tickers=validated_tickers, min_tier=args.min_tier, source=source)

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
