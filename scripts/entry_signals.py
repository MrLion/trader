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

# Configurable paths
DATA_DIR = Path(__file__).parent.parent / 'data'
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'
SCANS_DIR = Path(__file__).parent.parent / 'scans'

# Entry criteria thresholds
ENTRY_THRESHOLD = 60
MAX_DIST_TO_PIVOT = 1.0
MIN_VOLUME_RATIO = 1.5
MAX_SPY_DECLINE = -0.3


class EntrySignalScanner:
    """Scan watchlist for tickers meeting entry criteria."""

    def __init__(self, mode: str = 'paper'):
        print("🔌 Initializing scanner...")
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
            quote = self.alpaca.get_latest_quote(ticker)
            if quote:
                # Use ask price for conservative entry estimate
                return quote.get('ask_price') or quote.get('close_price')
        except Exception:
            pass

        # Fallback to historical
        try:
            hist = self.alpaca.get_historical_bars(ticker, days=5)
            if hist is not None and len(hist) > 0:
                return hist['Close'].iloc[-1]
        except Exception:
            pass

        return None

    def _check_market_conditions(self) -> tuple:
        """Check SPY market conditions."""
        try:
            spy_price = self._get_current_price('SPY')
            if spy_price is None:
                return True, "SPY data unavailable"

            # Get yesterday's close
            import yfinance as yf
            spy = yf.Ticker("SPY")
            hist = spy.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                change_pct = ((spy_price / prev_close) - 1) * 100

                if change_pct < MAX_SPY_DECLINE:
                    return False, f"SPY {change_pct:+.2f}% (below {MAX_SPY_DECLINE}%)"

                return True, f"SPY {change_pct:+.2f}%"
        except Exception:
            pass

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
            except Exception:
                pass

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

        print(f"\n🔍 Scanning {len(tickers)} tickers for entry signals...")
        print(f"   Entry Criteria: Score ≥ {ENTRY_THRESHOLD}, Distance ≤ ±{MAX_DIST_TO_PIVOT}%")

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

            score_ok = a['entry_score'] >= ENTRY_THRESHOLD
            dist_ok = -MAX_DIST_TO_PIVOT <= a['dist_to_pivot'] <= MAX_DIST_TO_PIVOT
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
            print(f"\n🔥 READY NOW - Entry Signals (Score ≥{ENTRY_THRESHOLD}, Within ±{MAX_DIST_TO_PIVOT}%)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Price':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in ready_now:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if close_pivot:
            print(f"\n⏳ CLOSE TO PIVOT - Watch for Breakout (Score ≥{ENTRY_THRESHOLD}, Distance 1-3%)")
            print(f"{'Ticker':<8} {'Score':<6} {'Tier':<6} {'Stage2':<8} {'Dist':<12} {'Risk%':<8} {'Current':<10} {'→ Pivot':<10}")
            print("-" * 90)
            for a in close_pivot:
                print(f"{a['ticker']:<8} {a['entry_score']:<6} {a['tier']:<6} {a['stage2']}/7    {_format_dist(a['dist_to_pivot']):<12} {a['risk_pct']:<7.1f}  ${a['current']:<8.2f}  ${a['pivot']:<8.2f}")

        if extended:
            print(f"\n📈 EXTENDED - High Quality but >3% from Pivot (Score ≥{ENTRY_THRESHOLD})")
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


def main():
    parser = argparse.ArgumentParser(
        description='Scan watchlist for entry signals'
    )
    parser.add_argument(
        '--tickers', '-t',
        nargs='+',
        help='Specific tickers to scan (default: watchlist)'
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
        default='csv',
        help='Export format for results'
    )
    parser.add_argument(
        '--mode',
        choices=['paper', 'live'],
        default='paper',
        help='Alpaca mode (default: paper)'
    )

    args = parser.parse_args()

    # Run scan
    scanner = EntrySignalScanner(mode=args.mode)
    signals = scanner.scan(
        tickers=args.tickers,
        min_tier=args.min_tier
    )

    # Export if requested
    if args.export != 'none' and signals:
        scanner.export_signals(signals, format=args.export)

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
