#!/usr/bin/env python3
"""Trend Screener with MA Convergence Detection.

Standalone discovery tool combining MarketSurge-style trend filters
with MA convergence detection. Outputs ranked CSV for watchlist population.

Usage:
    # Discovery mode - find stocks with MA convergence
    python3 scripts/trend_screener.py --profile large-cap --rank-by convergence

    # Entry timing - rank existing watchlist by setup readiness
    python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

    # Single ticker detail with MA data
    python3 scripts/trend_screener.py --tickers AAPL --show-ma-data
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.alpaca_client import AlpacaClient
from traderlib.paper_exits import ExitEngine
from traderlib.stage2_utils import (
    calculate_stage2_score,
    get_stage2_details,
    calculate_convergence_score,
    calculate_volume_metrics,
    calculate_ma_support_stop,
)
from traderlib.vcp_utils import detect_vcp_pattern, format_vcp_summary
from traderlib.risk_config import RiskConfigManager


class TrendScreener:
    """Trend screener with MA convergence detection."""

    def __init__(self, mode: str = 'paper'):
        self.alpaca = AlpacaClient(mode=mode)
        self.exit_engine = ExitEngine()
        self.spy_cache: Dict[str, pd.DataFrame] = {}

    def _get_spy_history(self, lookback_days: int = 130) -> Optional[pd.DataFrame]:
        """Get SPY history for RS calculations."""
        cache_key = f'spy_{lookback_days}'
        if cache_key not in self.spy_cache:
            try:
                hist = self.alpaca.get_bars('SPY', limit=lookback_days)
                if hist is not None and len(hist) >= 130:
                    self.spy_cache[cache_key] = hist
                else:
                    return None
            except Exception:
                return None
        return self.spy_cache.get(cache_key)

    def _calculate_rs(self, ticker: str, hist: pd.DataFrame) -> Tuple[float, float]:
        """Calculate relative strength vs SPY.

        Returns:
            Tuple of (rs_line_pct, rs_vs_spy_pct)
        """
        if len(hist) < 130:
            return 0.0, 0.0

        spy_hist = self._get_spy_history()
        if spy_hist is None or len(spy_hist) < 130:
            return 0.0, 0.0

        # Stock 6-month return
        current = hist['Close'].iloc[-1]
        stock_6m_ago = hist['Close'].iloc[-130]
        stock_ret = ((current / stock_6m_ago) - 1) * 100

        # SPY 6-month return
        spy_current = spy_hist['Close'].iloc[-1]
        spy_6m_ago = spy_hist['Close'].iloc[-130]
        spy_ret = ((spy_current / spy_6m_ago) - 1) * 100

        # RS vs SPY
        rs_vs_spy = stock_ret - spy_ret

        # RS Line: stock performance vs SPY (normalized)
        rs_line = stock_ret  # Simple version - can be enhanced

        return rs_line, rs_vs_spy

    def _is_rs_near_high(self, ticker: str, hist: pd.DataFrame, threshold_pct: float = 5.0) -> Tuple[bool, float]:
        """Check if RS line is within threshold of 52-week high."""
        if len(hist) < 130:
            return False, 0.0

        rs_line, _ = self._calculate_rs(ticker, hist)

        # Calculate RS line history (simplified - using price as proxy)
        # In full implementation, would track RS line over time
        high_52w = hist['Close'].max()
        current = hist['Close'].iloc[-1]
        from_high_pct = ((high_52w - current) / high_52w) * 100

        is_near = from_high_pct <= threshold_pct
        return is_near, from_high_pct

    def _detect_pivot(self, hist: pd.DataFrame, lookback_days: int = 20) -> Dict:
        """Detect recent pivot high (simplified version).

        Full VCP detection will be implemented in Phase 4.
        For now, returns recent high as pivot proxy.
        """
        if len(hist) < lookback_days:
            return {'valid': False, 'pivot_high': 0, 'stop_low': 0}

        recent = hist.tail(lookback_days)
        pivot_high = recent['High'].max()
        stop_low = recent['Low'].min()

        return {
            'valid': True,
            'pivot_high': float(pivot_high),
            'stop_low': float(stop_low),
            'pivot_date': recent['High'].idxmax()
        }

    def _analyze_ticker(
        self,
        ticker: str,
        filters: Dict,
        profile: str = 'large-cap'
    ) -> Optional[Dict]:
        """Full analysis of a single ticker."""

        # Fetch historical data
        try:
            hist = self.alpaca.get_bars(ticker, limit=252)
            if hist is None or len(hist) < 200:
                return None
        except Exception:
            return None

        current = hist['Close'].iloc[-1]

        # === DISCOVERY FILTERS (MarketSurge-style) ===

        # 1. Price >= $30
        min_price = filters.get('min_price', 30)
        if current < min_price:
            return None

        # 2. Price vs 10 MA >= 6%
        ma10 = hist['Close'].rolling(10).mean().iloc[-1]
        price_vs_10ma = ((current - ma10) / ma10) * 100
        min_price_vs_10ma = filters.get('min_price_vs_10ma', 6)
        if price_vs_10ma < min_price_vs_10ma:
            return None

        # Get Stage 2 details (includes all MAs)
        s2_details = get_stage2_details(hist)
        if s2_details['score'] < filters.get('min_stage2_score', 5):
            return None

        # 3. MA Stacking: 10D > 21D > 50D (short-term)
        if filters.get('stack_short', True):
            ma21 = hist['Close'].rolling(21).mean().iloc[-1]
            ma50 = s2_details['ma50']
            if not (ma10 > ma21 > ma50):
                return None

        # 4. MA Stacking: 50D > 150D > 200D (long-term)
        if filters.get('stack_long', True):
            ma150 = s2_details.get('ma150', 0)
            ma200 = s2_details['ma200']
            if ma150 == 0 or not (ma50 > ma150 > ma200):
                return None

        # 5. RS Line within 5% of 52-week high
        rs_near_high, rs_from_high = self._is_rs_near_high(ticker, hist, filters.get('rs_near_high', 5))
        if filters.get('require_rs_near_high', True) and not rs_near_high:
            return None

        # 6. Exclude ETFs (basic check)
        if filters.get('exclude_etfs', True):
            etf_keywords = ['ETF', 'FUND', 'TRUST', 'ISHARES', 'VANGUARD', 'SPDR']
            # Note: Would need proper asset info to check this
            # For now, skip known ETFs
            if ticker in ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO']:
                return None

        # 7. Liquidity filters
        vol_metrics = calculate_volume_metrics(hist, lookback_days=50)

        # Profile-specific liquidity
        if profile == 'large-cap':
            min_dollar_vol = filters.get('min_volume_dollar', 80_000_000)
            min_share_vol = filters.get('min_volume_shares', 1_000_000)
        else:  # high-octane
            min_dollar_vol = filters.get('min_volume_dollar', 20_000_000)
            min_share_vol = filters.get('min_volume_shares', 400_000)

        if vol_metrics['avg_dollar_volume'] < min_dollar_vol:
            return None
        if vol_metrics['avg_volume'] < min_share_vol:
            return None

        # === CONVERGENCE SCORING ===

        # Calculate ATR stop for comparison
        try:
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]
            atr_stop = current - (2 * atr)
        except:
            atr_stop = current * 0.93

        conv_score = calculate_convergence_score(
            current,
            s2_details,
            atr_stop=atr_stop,
            cluster_spread_pct=filters.get('cluster_spread_pct', 0.05),
            min_cluster_size=filters.get('min_cluster_size', 2)
        )

        # Minimum convergence score
        min_conv_score = filters.get('min_convergence_score', 50)
        if conv_score['score'] < min_conv_score:
            return None

        # === ENTRY TIMING ===

        entry_mode = filters.get('entry_mode', 'any')
        entry_ready = False
        setup_type = 'none'
        proximity_pct = 100.0
        volume_ratio = vol_metrics['volume_ratio']
        vcp_data = None

        # VCP mode: Full pattern detection
        if entry_mode == 'vcp':
            vcp_pattern = detect_vcp_pattern(
                hist,
                min_contractions=filters.get('vcp_min_contractions', 2),
                reversal_threshold=filters.get('vcp_reversal_threshold', 0.05),
                require_volume_dry_up=filters.get('vcp_require_volume', True)
            )
            if vcp_pattern.valid:
                # Check proximity to pivot
                pivot_proximity = ((vcp_pattern.pivot_high - current) / vcp_pattern.pivot_high) * 100
                max_proximity = filters.get('pivot_proximity', 5.0)
                if pivot_proximity <= max_proximity and vcp_pattern.volume_declining:
                    entry_ready = True
                    setup_type = 'vcp'
                    proximity_pct = pivot_proximity
                    vcp_data = format_vcp_summary(vcp_pattern)

        # Pivot mode: Simple pivot detection
        elif entry_mode in ['pivot', 'any']:
            pivot_data_simple = self._detect_pivot(hist, lookback_days=20)
            if pivot_data_simple['valid']:
                pivot_proximity = ((pivot_data_simple['pivot_high'] - current) / pivot_data_simple['pivot_high']) * 100
                max_proximity = filters.get('pivot_proximity', 5.0)
                if pivot_proximity <= max_proximity:
                    entry_ready = True
                    setup_type = 'pivot'
                    proximity_pct = pivot_proximity

        # Volume mode: Volume spike + proximity
        if entry_mode == 'volume':
            if volume_ratio >= filters.get('min_volume_ratio', 1.5):
                pivot_data_simple = self._detect_pivot(hist, lookback_days=20)
                if pivot_data_simple['valid']:
                    pivot_proximity = ((pivot_data_simple['pivot_high'] - current) / pivot_data_simple['pivot_high']) * 100
                    if pivot_proximity <= filters.get('pivot_proximity', 5.0):
                        entry_ready = True
                        setup_type = 'volume'
                        proximity_pct = pivot_proximity

        if entry_mode == 'any' and not entry_ready:
            # Default to true if no specific filter
            entry_ready = True
            setup_type = 'convergence'
            proximity_pct = abs(price_vs_10ma)

        # === COMPILE RESULT ===

        ma_cluster = conv_score.get('cluster_data', {})

        result = {
            'ticker': ticker,
            'price': round(current, 2),
            'stage2_score': s2_details['score'],
            'convergence_score': conv_score['score'],
            'cluster_size': ma_cluster.get('cluster_size', 0),
            'cluster_spread_pct': ma_cluster.get('cluster_spread_pct', 0),
            'ma_risk_pct': conv_score.get('ma_risk_pct', 0),
            'atr_risk_pct': conv_score.get('atr_risk_pct', 0),
            'risk_improvement_pct': conv_score['components']['risk_improvement'],
            'setup_type': setup_type,
            'entry_ready': entry_ready,
            'proximity_pct': round(proximity_pct, 2),
            'volume_ratio': volume_ratio,
            'avg_dollar_volume': vol_metrics['avg_dollar_volume'],
            'rs_from_high': round(rs_from_high, 2),
            # MA values for display
            'ma10': round(s2_details['ma10'], 2),
            'ma20': round(s2_details['ma20'], 2),
            'ma50': round(s2_details['ma50'], 2),
            'ma150': round(s2_details.get('ma150', 0), 2) if 'ma150' in s2_details else None,
            'ma200': round(s2_details['ma200'], 2),
            # VCP data (if available)
            'vcp_data': vcp_data,
        }

        return result

    def scan(
        self,
        tickers: List[str],
        filters: Dict,
        profile: str = 'large-cap'
    ) -> List[Dict]:
        """Run screen on ticker list, return ranked results."""
        results = []

        print(f"Scanning {len(tickers)} tickers with {profile} profile...")
        print(f"  Filters: min_price=${filters.get('min_price', 30)}, "
              f"min_conv_score={filters.get('min_convergence_score', 50)}")

        for i, ticker in enumerate(tickers, 1):
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(tickers)}")

            result = self._analyze_ticker(ticker, filters, profile)
            if result:
                results.append(result)

        print(f"  Found {len(results)} candidates")
        return results

    def rank_results(self, results: List[Dict], rank_by: str = 'convergence') -> List[Dict]:
        """Sort results by specified criteria."""
        if not results:
            return []

        if rank_by == 'convergence':
            # Primary: convergence_score desc, Secondary: cluster_size desc
            return sorted(results, key=lambda x: (x['convergence_score'], x['cluster_size']), reverse=True)

        elif rank_by == 'setup':
            # Entry ready first, then by proximity, then convergence
            return sorted(results, key=lambda x: (
                not x['entry_ready'],  # False (ready) sorts before True
                x['proximity_pct'],     # Lower is better
                -x['convergence_score']  # Higher is better (negated for sort)
            ))

        elif rank_by == 'rs':
            # By RS from high (lower = closer to high = better)
            return sorted(results, key=lambda x: x['rs_from_high'])

        else:
            return results

    def display_results(self, results: List[Dict], show_ma_data: bool = False, top: int = 20):
        """Print formatted results table."""
        if not results:
            print("\nNo results found matching criteria.")
            return

        display = results[:top]

        print(f"\n{'=' * 120}")
        print(f"Top {len(display)} Results (sorted by convergence quality)")
        print(f"{'=' * 120}")

        # Header
        if show_ma_data:
            header = (f"{'Rank':<5} {'Ticker':<8} {'Price':>8} {'S2':>4} {'Conv':>5} {'Clust':>5} "
                     f"{'MA_Risk':>7} {'Setup':>8} {'Prox%':>6} {'Vol':>5} {'Entry':>6}")
        else:
            header = (f"{'Rank':<5} {'Ticker':<8} {'Price':>8} {'S2':>4} {'Conv':>5} {'Clust':>5} "
                     f"{'MA_Risk':>7} {'Setup':>8} {'Prox%':>6} {'Vol':>5} {'Entry':>6}")

        print(header)
        print('-' * 120)

        for i, r in enumerate(display, 1):
            entry_status = "READY" if r['entry_ready'] else "WAIT"
            setup = r['setup_type'][:8]

            row = (f"{i:<5} {r['ticker']:<8} ${r['price']:>7.2f} {r['stage2_score']:>4} "
                  f"{r['convergence_score']:>5} {r['cluster_size']:>5} "
                  f"{r['ma_risk_pct']:>6.1f}% {setup:>8} {r['proximity_pct']:>6.1f}% "
                  f"{r['volume_ratio']:>5.1f}x {entry_status:>6}")
            print(row)

            if show_ma_data:
                ma_row = (f"      MAs: 10=${r['ma10']:.2f} 20=${r['ma20']:.2f} 50=${r['ma50']:.2f} "
                         f"150=${r.get('ma150', 'N/A')} 200=${r['ma200']:.2f}")
                print(ma_row)

        print(f"{'=' * 120}")

    def export_results(
        self,
        results: List[Dict],
        format: str,
        path: Optional[str] = None
    ) -> str:
        """Export results to file."""
        if not path:
            date_str = datetime.now().strftime('%Y%m%d')
            path = f"scans/trend_screen_{date_str}.{format}"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        if format == 'csv':
            df = pd.DataFrame(results)
            df.to_csv(path, index=False)

        elif format == 'json':
            with open(path, 'w') as f:
                json.dump(results, f, indent=2, default=str)

        elif format == 'html':
            df = pd.DataFrame(results)
            html = df.to_html(index=False, classes='table table-striped')
            with open(path, 'w') as f:
                f.write(f"""
<!DOCTYPE html>
<html>
<head>
    <title>Trend Screener Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .table {{ border-collapse: collapse; width: 100%; }}
        .table th, .table td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
        .table th {{ background-color: #4CAF50; color: white; text-align: center; }}
        .table tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .high-score {{ background-color: #90EE90 !important; }}
        .ready {{ font-weight: bold; color: green; }}
    </style>
</head>
<body>
    <h1>Trend Screener Results - {datetime.now().strftime('%Y-%m-%d')}</h1>
    {html}
</body>
</html>
""")

        print(f"Exported {len(results)} results to {path}")
        return path


def load_tickers(args) -> List[str]:
    """Load tickers from various sources."""
    tickers = []

    if args.tickers:
        tickers.extend(args.tickers)

    if args.ticker_file:
        try:
            with open(args.ticker_file) as f:
                file_tickers = [line.strip() for line in f if line.strip()]
            tickers.extend(file_tickers)
        except Exception as e:
            print(f"Error loading ticker file: {e}")

    # Default: scan S&P 500 or watchlist
    if not tickers:
        # Try to load from watchlist
        watchlist_path = Path("data/watchlist.csv")
        if watchlist_path.exists():
            df = pd.read_csv(watchlist_path)
            if 'Ticker' in df.columns:
                tickers = df['Ticker'].dropna().unique().tolist()
            elif 'ticker' in df.columns:
                tickers = df['ticker'].dropna().unique().tolist()

    # Remove duplicates while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        t = t.upper().strip()
        if t and t not in seen:
            seen.add(t)
            unique_tickers.append(t)

    return unique_tickers


def main():
    parser = argparse.ArgumentParser(
        description='Trend Screener with MA Convergence Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discovery mode - find stocks with MA convergence
  python3 %(prog)s --profile large-cap --rank-by convergence --top 20

  # Rank watchlist by entry readiness
  python3 %(prog)s --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

  # Single ticker with MA details
  python3 %(prog)s --tickers AAPL MSFT --show-ma-data

  # Export results
  python3 %(prog)s --profile large-cap --export csv --export-path scans/discovery.csv
        """
    )

    # Ticker sources
    parser.add_argument('--tickers', '-t', nargs='+', help='Specific tickers to scan')
    parser.add_argument('--ticker-file', '-f', help='File with tickers (one per line)')

    # Discovery filters (MarketSurge-style)
    parser.add_argument('--min-price', type=float, default=30, help='Minimum stock price (default: 30)')
    parser.add_argument('--min-price-vs-10ma', type=float, default=6, help='Min %% above 10-day MA (default: 6)')
    parser.add_argument('--stack-short', action='store_true', default=True, help='Require 10D > 21D > 50D')
    parser.add_argument('--stack-long', action='store_true', default=True, help='Require 50D > 150D > 200D')
    parser.add_argument('--rs-near-high', type=float, default=5, help='RS line within %% of 52-week high (default: 5)')
    parser.add_argument('--exclude-etfs', action='store_true', default=True, help='Exclude ETFs')

    # Liquidity filters
    parser.add_argument('--min-volume-dollar', type=float, default=None, help='Min 50-day avg dollar volume')
    parser.add_argument('--min-volume-shares', type=float, default=None, help='Min 50-day avg share volume')

    # Profile selection
    parser.add_argument('--profile', choices=['large-cap', 'high-octane', 'custom'], default='large-cap',
                        help='VCP profile (default: large-cap)')

    # Convergence scoring
    parser.add_argument('--min-convergence-score', type=int, default=50, help='Minimum convergence score (default: 50)')
    parser.add_argument('--cluster-spread-pct', type=float, default=0.05, help='Max cluster spread %% (default: 5)')
    parser.add_argument('--min-cluster-size', type=int, default=2, help='Minimum MAs in cluster (default: 2)')

    # Entry timing
    parser.add_argument('--entry-mode', choices=['any', 'vcp', 'pivot', 'volume'], default='any',
                        help='Entry timing mode: any=vcp|pivot|volume, vcp=full VCP pattern, pivot=near pivot, volume=vol spike (default: any)')
    parser.add_argument('--pivot-proximity', type=float, default=5, help='Max %% from pivot (default: 5)')
    parser.add_argument('--min-volume-ratio', type=float, default=1.5, help='Min volume vs 50-day avg for volume mode (default: 1.5)')

    # VCP specific
    parser.add_argument('--vcp-min-contractions', type=int, default=2, help='Min contractions for VCP mode (default: 2)')
    parser.add_argument('--vcp-reversal-threshold', type=float, default=0.05, help='Min % reversal to detect swing (default: 5%%)')

    # Ranking and display
    parser.add_argument('--rank-by', choices=['convergence', 'setup', 'rs'], default='convergence',
                        help='Sort criteria (default: convergence)')
    parser.add_argument('--show-ma-data', action='store_true', help='Display MA values and cluster details')
    parser.add_argument('--top', type=int, default=20, help='Show top N results (default: 20)')

    # Export
    parser.add_argument('--export', '-e', choices=['csv', 'json', 'html', 'none'], default='none',
                        help='Export format (default: none)')
    parser.add_argument('--export-path', help='Export file path (default: scans/trend_screen_YYYYMMDD.csv)')

    args = parser.parse_args()

    # Load tickers
    tickers = load_tickers(args)
    if not tickers:
        print("Error: No tickers to scan. Provide --tickers, --ticker-file, or populate data/watchlist.csv")
        sys.exit(1)

    print(f"Loaded {len(tickers)} tickers")

    # Build filters dict
    filters = {
        'min_price': args.min_price,
        'min_price_vs_10ma': args.min_price_vs_10ma,
        'stack_short': args.stack_short,
        'stack_long': args.stack_long,
        'rs_near_high': args.rs_near_high,
        'exclude_etfs': args.exclude_etfs,
        'min_volume_dollar': args.min_volume_dollar,
        'min_volume_shares': args.min_volume_shares,
        'min_convergence_score': args.min_convergence_score,
        'cluster_spread_pct': args.cluster_spread_pct,
        'min_cluster_size': args.min_cluster_size,
        'entry_mode': args.entry_mode,
        'pivot_proximity': args.pivot_proximity,
        'min_volume_ratio': args.min_volume_ratio,
        'vcp_min_contractions': args.vcp_min_contractions,
        'vcp_reversal_threshold': args.vcp_reversal_threshold,
        'vcp_require_volume': True,
        'min_stage2_score': 5,
    }

    # Run screener
    screener = TrendScreener()
    results = screener.scan(tickers, filters, profile=args.profile)

    # Rank results
    ranked = screener.rank_results(results, rank_by=args.rank_by)

    # Display
    screener.display_results(ranked, show_ma_data=args.show_ma_data, top=args.top)

    # Export
    if args.export != 'none':
        path = screener.export_results(ranked, args.export, args.export_path)
        print(f"\nExported to: {path}")


if __name__ == '__main__':
    main()
