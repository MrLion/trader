#!/usr/bin/env python3
"""Scan watchlist for entry signals - report only, no execution."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytz

# Add scripts directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from alpaca_client import AlpacaClient
from traderlib import calculate_stage2_score, get_entry_score
from traderlib.risk_config import RiskConfigManager
from traderlib.trading_exceptions import TradingExceptionHandler

# Configurable paths
DATA_DIR = Path(__file__).parent.parent / 'data'
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'
SCANS_DIR = Path(__file__).parent.parent / 'scans'


class EntrySignalScanner:
    """Scan watchlist for tickers meeting entry criteria."""

    def __init__(self, mode: str = 'paper', risk_profile: str = None):
        print("🔌 Initializing scanner...")
        self.risk_manager = RiskConfigManager(profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()
        self.alpaca = AlpacaClient(mode=mode)
        self.spy_cache = {'date': None, 'return_6m': 0.0, 'price': None}
        print("✅ Scanner ready")

    def _get_spy_return_6m(self) -> float:
        """Get SPY 6-month return (cached per day)."""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.spy_cache['date'] == today:
            return self.spy_cache['return_6m']

        try:
            spy_hist = self.alpaca.get_historical_bars('SPY')
            if spy_hist is not None and len(spy_hist) >= 130:
                current = spy_hist['Close'].iloc[-1]
                past = spy_hist['Close'].iloc[-130]
                ret_6m = ((current / past) - 1) * 100
                self.spy_cache = {
                    'date': today,
                    'return_6m': ret_6m,
                    'price': current
                }
                return ret_6m
        except Exception as e:
            print(f"   ⚠️  Could not fetch SPY data: {e}")

        return 0.0

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price from Alpaca."""
        try:
            price = self.alpaca.get_latest_price(ticker)
            if price:
                return price
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_quote", e,
                severity=TradingExceptionHandler.WARNING,
                ticker=ticker
            )

        # Fallback to historical
        try:
            hist = self.alpaca.get_historical_bars(ticker, days=5)
            if hist is not None and len(hist) > 0:
                return hist['Close'].iloc[-1]
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "get_current_price_hist", e,
                severity=TradingExceptionHandler.WARNING,
                ticker=ticker
            )

        return None

    def _check_market_conditions(self) -> tuple:
        """Check SPY market conditions."""
        try:
            import yfinance as yf
            hist = yf.Ticker("SPY").history(period="2d")
            if len(hist) >= 2:
                change_pct = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-2]) - 1) * 100

                if change_pct < self.risk_config.market.max_spy_decline_pct:
                    return False, f"SPY {change_pct:+.2f}% (below {self.risk_config.market.max_spy_decline_pct}%)"

                return True, f"SPY {change_pct:+.2f}%"
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "market_conditions", e,
                severity=TradingExceptionHandler.WARNING,
                ticker="SPY"
            )

        return True, "SPY OK"

    def _analyze_ticker(self, ticker: str) -> Optional[Dict]:
        """Analyze ticker for entry signal."""
        try:
            # Get historical data
            hist = self.alpaca.get_historical_bars(ticker)
            if hist is None or len(hist) < 30:
                return None

            current = self._get_current_price(ticker)
            if current is None:
                return None

            # Calculate Stage 2 score
            stage2 = calculate_stage2_score(hist)

            # Get pivot and sector from watchlist
            pivot = current
            sector = 'Unknown'
            try:
                df = pd.read_csv(WATCHLIST_PATH)
                row = df[df['Ticker'] == ticker]
                if not row.empty:
                    if 'Pivot_Price' in row.columns:
                        pivot_val = row['Pivot_Price'].values[0]
                        if not pd.isna(pivot_val):
                            pivot = float(pivot_val)
                    if 'Sector' in row.columns:
                        sector_val = row['Sector'].values[0]
                        if not pd.isna(sector_val):
                            sector = str(sector_val)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "sector_lookup", e,
                    severity=TradingExceptionHandler.WARNING,
                    ticker=ticker,
                    file=str(WATCHLIST_PATH)
                )

            # Calculate metrics
            ret_6m = 0
            if len(hist) >= 130:
                ret_6m = ((current / hist['Close'].iloc[-130]) - 1) * 100

            # ATR calculation
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                ranges = pd.concat([high_low, high_close, low_close], axis=1)
                true_range = ranges.max(axis=1)
                atr = true_range.rolling(14).mean().iloc[-1]
            except Exception:
                atr = current * 0.02  # Default 2% ATR

            # Calculate stop and target
            stop = current - (2 * atr)
            risk_per_share = current - stop
            target = current + (2 * risk_per_share) if risk_per_share > 0 else current * 1.04

            dist_to_pivot = ((pivot - current) / current) * 100
            risk_pct = abs((stop - pivot) / pivot) * 100 if pivot > stop else 999

            # Relative strength
            spy_return_6m = self._get_spy_return_6m()
            rs_6m = ret_6m - spy_return_6m

            # Calculate entry score
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)

            # Determine tier
            if entry_score >= 60 and stage2 >= 6:
                tier = "Tier 1"
            elif entry_score >= 40 and stage2 >= 4:
                tier = "Tier 2"
            else:
                tier = "Tier 3"

            return {
                'ticker': ticker,
                'current': current,
                'pivot': pivot,
                'stop': stop,
                'target': target,
                'sector': sector,
                'stage2': stage2,
                'entry_score': entry_score,
                'tier': tier,
                'dist_to_pivot': dist_to_pivot,
                'risk_pct': risk_pct,
                'ret_6m': ret_6m,
                'rs_6m': rs_6m,
                'atr': atr
            }

        except Exception as e:
            return None

    def _load_watchlist(self) -> List[str]:
        """Load tickers from watchlist."""
        try:
            df = pd.read_csv(WATCHLIST_PATH)
            if 'Ticker' in df.columns:
                return df['Ticker'].tolist()
        except Exception as e:
            print(f"⚠️  Could not load watchlist: {e}")

        return []

    def scan(self, tickers: Optional[List[str]] = None, min_tier: int = 1) -> List[Dict]:
        """
        Scan for entry signals.

        Args:
            tickers: List of tickers to scan (default: watchlist)
            min_tier: Minimum tier to include (1=Tier1 only, 2=Tier1+2, 3=All)

        Returns:
            List of tickers meeting entry criteria
        """
        if tickers is None:
            tickers = self._load_watchlist()

        if not tickers:
            print("⚠️  No tickers to scan")
            return []

        # Check market conditions
        market_ok, market_msg = self._check_market_conditions()
        print(f"\n📊 Market Condition: {market_msg}")
        if not market_ok:
            print(f"⚠️  Market filter blocking entries")

        entry_threshold = self.risk_config.entry.min_entry_score
        max_dist = self.risk_config.entry.max_dist_to_pivot_pct

        print(f"\n🔍 Scanning {len(tickers)} tickers for entry signals...")
        print(f"   Entry Criteria: Score ≥ {entry_threshold}, Distance ≤ ±{max_dist}%")

        # Collect all analyses
        all_analyses = []
        for ticker in tickers:
            analysis = self._analyze_ticker(ticker)
            if analysis:
                all_analyses.append(analysis)

        # Categorize results
        ready_now = []      # Score ≥60, within ±1%
        close_pivot = []    # Score ≥60, distance 1-3%
        extended = []       # Score ≥60, but distance >3% (extended from pivot)
        tier2_watch = []    # Score 40-59
        tier3_skip = []     # Score <40

        for a in all_analyses:
            # Skip if below minimum tier
            tier_num = int(a['tier'][-1])
            if tier_num > min_tier:
                continue

            score_ok = a['entry_score'] >= entry_threshold
            dist_ok = -max_dist <= a['dist_to_pivot'] <= max_dist
            dist_close = abs(a['dist_to_pivot']) <= 3.0  # Within 3%

            if score_ok and dist_ok:
                ready_now.append(a)
            elif score_ok and dist_close:
                close_pivot.append(a)  # Score ≥60, distance 1-3%
            elif score_ok:
                extended.append(a)  # Score ≥60, but distance >3%
            elif a['entry_score'] >= 40:
                tier2_watch.append(a)  # Score 40-59
            else:
                tier3_skip.append(a)  # Score <40

        # Sort by entry score (descending)
        ready_now.sort(key=lambda x: x['entry_score'], reverse=True)
        close_pivot.sort(key=lambda x: x['entry_score'], reverse=True)
        extended.sort(key=lambda x: x['entry_score'], reverse=True)
        tier2_watch.sort(key=lambda x: x['entry_score'], reverse=True)
        tier3_skip.sort(key=lambda x: x['entry_score'], reverse=True)

        signals = ready_now  # Return signals that meet entry criteria

        # Display results by category
        print("=" * 90)

        def _format_dist(d):
            """Format distance with sign and icon."""
            sign = "+" if d > 0 else "-" if d < 0 else ""
            icon = "📈" if d > 0 else "📉" if d < 0 else "➡️"
            return f"{sign}{abs(d):.1f}% {icon}"

        if ready_now:
            print(f"\n🔥 READY NOW - Entry Signals (Score ≥{entry_threshold}, Within ±{max_dist}%)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Price':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in ready_now:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if close_pivot:
            print(f"\n⏳ CLOSE TO PIVOT - Watch for Breakout (Score ≥{entry_threshold}, Distance 1-3%)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Current':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in close_pivot:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if extended:
            print(f"\n📈 EXTENDED - High Quality but >3% from Pivot (Score ≥{entry_threshold})")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Current':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in extended:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if tier2_watch:
            print(f"\n📊 TIER 2 WATCH - Developing Setups (Score 40-59)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Current':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in tier2_watch:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if tier3_skip and min_tier >= 3:
            print(f"\n⏸️  TIER 3 / BELOW THRESHOLD - Not Ready (Score <40)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Current':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in tier3_skip[:10]:  # Show first 10
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")
            if len(tier3_skip) > 10:
                print(f"   ... and {len(tier3_skip) - 10} more")

        if not any([ready_now, close_pivot, extended, tier2_watch]):
            print("\n⏸️  No qualifying setups found in Tier 1 or Tier 2")

        print("=" * 90)
        print(f"\n📊 Scan Complete: {len(ready_now)} Entry Signals | {len(close_pivot)} Close to Pivot | {len(extended)} Extended | {len(tier2_watch)} Tier 2 | {len(tier3_skip)} Tier 3")

        return signals

    def export_signals(self, signals: List[Dict], format: str = 'csv'):
        """Export signals to file."""
        if not signals:
            print("⚠️  No signals to export")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        SCANS_DIR.mkdir(parents=True, exist_ok=True)

        if format == 'csv':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.csv'
            df = pd.DataFrame(signals)
            df.to_csv(filepath, index=False)
            print(f"\n💾 Exported to: {filepath}")

        elif format == 'json':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.json'
            with open(filepath, 'w') as f:
                json.dump(signals, f, indent=2, default=str)
            print(f"\n💾 Exported to: {filepath}")

        elif format == 'html':
            filepath = SCANS_DIR / f'entry_signals_{timestamp}.html'
            self._export_html(signals, filepath)
            print(f"\n💾 Exported to: {filepath}")

    def _export_html(self, signals: List[Dict], filepath: Path):
        """Generate HTML report."""
        tier1 = [s for s in signals if s['entry_score'] >= 60]
        tier2 = [s for s in signals if 40 <= s['entry_score'] < 60]
        tier3 = [s for s in signals if s['entry_score'] < 40]

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Entry Signals — {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        :root {{ --bg-primary: #0f172a; --bg-secondary: #1e293b; --text-primary: #f8fafc;
                --accent-green: #4ade80; --accent-yellow: #facc15; --accent-red: #f87171; }}
        body {{ font-family: -apple-system, sans-serif; background: var(--bg-primary);
               color: var(--text-primary); padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: var(--bg-secondary); }}
        .tier1 {{ color: var(--accent-green); }}
        .tier2 {{ color: var(--accent-yellow); }}
        .tier3 {{ color: var(--accent-red); }}
    </style>
</head>
<body>
    <h1>🎯 Entry Signals — {datetime.now().strftime('%Y-%m-%d')}</h1>

    <h2 class="tier1">🟢 Ready Now (Score ≥60)</h2>
    <table>
        <tr><th>Ticker</th><th>Score</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>Sector</th></tr>
        {''.join(f'<tr class="tier1"><td>{s["ticker"]}</td><td>{s["entry_score"]}</td><td>${s["current"]:.2f}</td><td>${s["pivot"]:.2f}</td><td>{s["dist_to_pivot"]:.1f}%</td><td>{s["risk_pct"]:.1f}%</td><td>{s["stage2"]}/7</td><td>{s["sector"]}</td></tr>' for s in tier1)}
    </table>

    <h2 class="tier2">🟡 Tier 2 (Score 40-59)</h2>
    <table>
        <tr><th>Ticker</th><th>Score</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>Sector</th></tr>
        {''.join(f'<tr class="tier2"><td>{s["ticker"]}</td><td>{s["entry_score"]}</td><td>${s["current"]:.2f}</td><td>${s["pivot"]:.2f}</td><td>{s["dist_to_pivot"]:.1f}%</td><td>{s["risk_pct"]:.1f}%</td><td>{s["stage2"]}/7</td><td>{s["sector"]}</td></tr>' for s in tier2)}
    </table>
</body>
</html>"""

        with open(filepath, 'w') as f:
            f.write(html_content)

    def analyze_single(self, ticker: str) -> Optional[Dict]:
        """Deep analysis of single ticker (like old analyze_ticker.py)."""
        print(f"\n🔍 Analyzing {ticker.upper()}...")

        analysis = self._analyze_ticker(ticker)
        if not analysis:
            print(f"❌ Could not analyze {ticker}")
            return None

        # Get additional data for deep dive
        try:
            hist = self.alpaca.get_historical_bars(ticker, days=252)  # 1 year
            if hist is not None and len(hist) >= 200:
                current = analysis['current']

                # Returns
                ret_1m = (current / hist['Close'].iloc[-20] - 1) * 100
                ret_3m = (current / hist['Close'].iloc[-65] - 1) * 100 if len(hist) >= 65 else 0
                ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0

                # Moving averages
                ma20 = hist['Close'].rolling(20).mean().iloc[-1]
                ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                ma150 = hist['Close'].rolling(150).mean().iloc[-1]
                ma200 = hist['Close'].rolling(200).mean().iloc[-1]

                # 52-week high
                high_52w = hist['Close'].max()
                from_high = ((high_52w - current) / high_52w) * 100

                # Above MAs check
                above_20 = '✓' if current > ma20 else '✗'
                above_50 = '✓' if current > ma50 else '✗'
                above_150 = '✓' if current > ma150 else '✗'
                above_200 = '✓' if current > ma200 else '✗'

                # Stage 2 status
                score = analysis['stage2']
                status = '🟢' if score >= 5 else '🟡' if score >= 3 else '🔴'

                print(f"\n{ticker.upper()} — ${current:.2f}\n")
                print("| Metric | Value |")
                print("|:-------|:------|")
                print(f"| Sector | {analysis['sector']} |")
                print(f"| 1M Return | {ret_1m:+.1f}% |")
                print(f"| 3M Return | {ret_3m:+.1f}% |")
                print(f"| 6M Return | {ret_6m:+.1f}% |")
                print(f"| Stage 2 Score | {score}/7 {status} |")
                print(f"| From 52W High | {from_high:.1f}% |")
                print(f"| Above All MAs | {above_20} {above_50} {above_150} {above_200} 20/50/150/200 |")

                print(f"\n---\n\nENTRY SETUP\n")
                print("| Level | Price |")
                print("|:------|:------|")
                print(f"| Pivot | ${analysis['pivot']:.2f} |")
                print(f"| Stop | ${analysis['stop']:.2f} |")
                print(f"| Target | ${analysis['target']:.2f} |")
                print(f"| Risk % | {analysis['risk_pct']:.1f}% |")

                # Verdict
                if score >= 6 and analysis['risk_pct'] < 10:
                    verdict = "🟢 A-TIER — Strong setup. Watch for volume-confirmed breakout."
                elif score >= 5:
                    verdict = "🟡 TIER B — Developing Stage 2 setup. Promote to A on breakout."
                elif score >= 4:
                    verdict = "🔵 TIER C — On radar, monitor for improvement."
                else:
                    verdict = "⚪ PASS — Below Stage 2 criteria."

                print(f"\n**Verdict:** {verdict}")

                return analysis
        except Exception as e:
            print(f"⚠️ Error getting additional data: {e}")

        return analysis


def main():
    parser = argparse.ArgumentParser(
        description='Scan watchlist for entry signals or analyze single ticker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 entry_signals.py                    # Scan full watchlist
  python3 entry_signals.py --ticker AAPL      # Deep dive single ticker
  python3 entry_signals.py --export-csv         # Scan and export to CSV
  python3 entry_signals.py --export-html        # Scan and export to HTML
        """
    )
    parser.add_argument(
        '--tickers', '-t',
        nargs='+',
        help='Specific tickers to scan (default: watchlist)'
    )
    parser.add_argument(
        '--ticker',
        help='Analyze single ticker in detail (replaces analyze_ticker.py)'
    )
    parser.add_argument(
        '--min-tier', '-m',
        type=int,
        choices=[1, 2, 3],
        default=3,
        help='Minimum tier to include (1=Tier1 only, 2=Tier1+2, 3=All)'
    )
    parser.add_argument(
        '--export', '-e',
        choices=['csv', 'json', 'none'],
        default='none',
        help='Export format for results'
    )
    parser.add_argument(
        '--export-csv',
        action='store_true',
        help='Export results to CSV (replaces analyze_watchlist.py --csv)'
    )
    parser.add_argument(
        '--export-html',
        action='store_true',
        help='Export results to HTML (replaces analyze_watchlist.py --html)'
    )
    parser.add_argument(
        '--mode',
        choices=['paper', 'live'],
        default='paper',
        help='Alpaca mode (default: paper)'
    )
    parser.add_argument(
        '--risk-profile',
        default=None,
        help='Risk profile to use (conservative, aggressive, tight_stops)'
    )

    args = parser.parse_args()

    # Single ticker analysis mode
    if args.ticker:
        scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile)
        result = scanner.analyze_single(args.ticker.upper())
        return 0 if result else 1

    # Run scan
    scanner = EntrySignalScanner(mode=args.mode, risk_profile=args.risk_profile)
    signals = scanner.scan(
        tickers=args.tickers,
        min_tier=args.min_tier
    )

    # Determine export format
    export_format = args.export
    if args.export_csv:
        export_format = 'csv'
    elif args.export_html:
        export_format = 'html'

    # Export if requested
    if export_format != 'none' and signals:
        scanner.export_signals(signals, format=export_format)

    # Summary
    if signals:
        print(f"\n✅ Found {len(signals)} entry signal(s):")
        for s in signals:
            print(f"   {s['ticker']}: Score {s['entry_score']:.0f} ({s['tier']}) - ${s['current']:.2f}")
    else:
        print("\n⏸️  No entry signals found")

    return 0 if signals else 1


if __name__ == "__main__":
    sys.exit(main())
