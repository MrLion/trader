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

    # Export to backtest
    python3 scripts/trend_screener.py --profile large-cap --export-watchlist scans/watchlist_today.csv
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
    get_stage2_details,
    calculate_volume_metrics,
)
from traderlib.vcp_utils import detect_vcp_pattern, format_vcp_summary
from traderlib.universe_builder import UniverseBuilder
from traderlib.sector_resolver import SectorResolver


class TrendScreener:
    """Trend screener with MA convergence detection."""

    def __init__(self, mode: str = 'paper'):
        self.alpaca = AlpacaClient(mode=mode)
        self.exit_engine = ExitEngine()
        self.sector_resolver = SectorResolver()
        self.spy_cache: Dict[str, pd.DataFrame] = {}
        self._filter_counts: Dict[str, int] = {}

    def _record_rejection(self, reason: str) -> None:
        self._filter_counts[reason] = self._filter_counts.get(reason, 0) + 1

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
        """Calculate relative strength vs SPY."""
        if len(hist) < 130:
            return 0.0, 0.0

        spy_hist = self._get_spy_history()
        if spy_hist is None or len(spy_hist) < 130:
            return 0.0, 0.0

        current = hist['Close'].iloc[-1]
        stock_6m_ago = hist['Close'].iloc[-130]
        stock_ret = ((current / stock_6m_ago) - 1) * 100

        spy_current = spy_hist['Close'].iloc[-1]
        spy_6m_ago = spy_hist['Close'].iloc[-130]
        spy_ret = ((spy_current / spy_6m_ago) - 1) * 100

        rs_vs_spy = stock_ret - spy_ret
        rs_line = stock_ret

        return rs_line, rs_vs_spy

    def _is_rs_near_high(self, ticker: str, hist: pd.DataFrame, threshold_pct: float = 5.0) -> Tuple[bool, float]:
        """Check if RS line is within threshold of 52-week high."""
        if len(hist) < 130:
            return False, 0.0

        rs_line, _ = self._calculate_rs(ticker, hist)

        high_52w = hist['Close'].max()
        current = hist['Close'].iloc[-1]
        from_high_pct = ((high_52w - current) / high_52w) * 100

        is_near = from_high_pct <= threshold_pct
        return is_near, from_high_pct

    def _detect_pivot(self, hist: pd.DataFrame, lookback_days: int = 20) -> Dict:
        """Detect recent pivot high."""
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

        try:
            hist = self.alpaca.get_bars(ticker, limit=252)
            if hist is None or len(hist) < 200:
                self._record_rejection('data')
                return None
        except Exception:
            self._record_rejection('data')
            return None

        current = hist['Close'].iloc[-1]

        # === DISCOVERY FILTERS (MarketSurge-style) ===

        # 1. Price floor — null/None = disabled
        min_price = filters.get('min_price')
        if min_price is not None and current < min_price:
            self._record_rejection('price')
            return None

        # 2. Price vs 10 MA — null/None = disabled
        ma10 = hist['Close'].rolling(10).mean().iloc[-1]
        price_vs_10ma = ((current - ma10) / ma10) * 100
        min_price_vs_10ma = filters.get('min_price_vs_10ma')
        if min_price_vs_10ma is not None and price_vs_10ma < min_price_vs_10ma:
            self._record_rejection('price_vs_10ma')
            return None

        # Get Stage 2 details (includes all MAs)
        s2_details = get_stage2_details(hist)
        min_stage2 = filters.get('min_stage2_score')
        if min_stage2 is not None and s2_details['score'] < min_stage2:
            self._record_rejection('stage2')
            return None

        # 3. MA Stacking: 10D > 21D > 50D (short-term)
        if filters.get('stack_short', True):
            ma21 = hist['Close'].rolling(21).mean().iloc[-1]
            ma50 = s2_details['ma50']
            if not (ma10 > ma21 > ma50):
                self._record_rejection('ma_stack_short')
                return None

        # 4. MA Stacking: 50D > 150D > 200D (long-term)
        if filters.get('stack_long', True):
            ma150 = s2_details.get('ma150', 0)
            ma200 = s2_details['ma200']
            ma50 = s2_details['ma50']
            if ma150 == 0 or not (ma50 > ma150 > ma200):
                self._record_rejection('ma_stack_long')
                return None

        # 5. RS Line within threshold of 52-week high — null/None = compute for display only
        rs_threshold = filters.get('rs_near_high')
        if rs_threshold is not None:
            rs_near_high, rs_from_high = self._is_rs_near_high(ticker, hist, rs_threshold)
            if not rs_near_high:
                self._record_rejection('rs_near_high')
                return None
        else:
            _, rs_from_high = self._is_rs_near_high(ticker, hist, 100)

        # 6. Liquidity filters — null/None = disabled individually
        vol_metrics = calculate_volume_metrics(hist, lookback_days=50)

        min_dollar_vol = filters.get('min_volume_dollar')
        min_share_vol = filters.get('min_volume_shares')

        if min_dollar_vol is not None and vol_metrics['avg_dollar_volume'] < min_dollar_vol:
            self._record_rejection('liquidity')
            return None
        if min_share_vol is not None and vol_metrics['avg_volume'] < min_share_vol:
            self._record_rejection('liquidity')
            return None

        # === ENTRY TIMING ===

        entry_mode = filters.get('entry_mode', 'any')
        entry_ready = False
        setup_type = 'none'
        proximity_pct = 100.0
        volume_ratio = vol_metrics['volume_ratio']
        vcp_data = None

        if entry_mode == 'vcp':
            vcp_pattern = detect_vcp_pattern(
                hist,
                min_contractions=filters.get('vcp_min_contractions', 2),
                reversal_threshold=filters.get('vcp_reversal_threshold', 0.05),
                require_volume_dry_up=filters.get('vcp_require_volume', True)
            )
            if vcp_pattern.valid:
                pivot_proximity = ((vcp_pattern.pivot_high - current) / vcp_pattern.pivot_high) * 100
                max_proximity = filters.get('pivot_proximity', 5.0)
                if pivot_proximity <= max_proximity and vcp_pattern.volume_declining:
                    entry_ready = True
                    setup_type = 'vcp'
                    proximity_pct = pivot_proximity
                    vcp_data = format_vcp_summary(vcp_pattern)

        elif entry_mode in ['pivot', 'any']:
            pivot_data_simple = self._detect_pivot(hist, lookback_days=20)
            if pivot_data_simple['valid']:
                pivot_proximity = ((pivot_data_simple['pivot_high'] - current) / pivot_data_simple['pivot_high']) * 100
                max_proximity = filters.get('pivot_proximity', 5.0)
                if pivot_proximity <= max_proximity:
                    entry_ready = True
                    setup_type = 'pivot'
                    proximity_pct = pivot_proximity

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
            entry_ready = True
            setup_type = 'trend'
            proximity_pct = abs(price_vs_10ma)

        # === COMPILE RESULT ===

        result = {
            'ticker': ticker,
            'price': round(current, 2),
            'stage2_score': s2_details['score'],
            'setup_type': setup_type,
            'entry_ready': entry_ready,
            'proximity_pct': round(proximity_pct, 2),
            'volume_ratio': volume_ratio,
            'avg_dollar_volume': vol_metrics['avg_dollar_volume'],
            'rs_from_high': round(rs_from_high, 2),
            'ma10': round(s2_details['ma10'], 2),
            'ma20': round(s2_details['ma20'], 2),
            'ma50': round(s2_details['ma50'], 2),
            'ma150': round(s2_details.get('ma150', 0), 2) if 'ma150' in s2_details else None,
            'ma200': round(s2_details['ma200'], 2),
            'vcp_data': vcp_data,
        }

        result['sector'] = self.sector_resolver.resolve(ticker)
        self._filter_counts['passed'] = self._filter_counts.get('passed', 0) + 1
        return result

    def scan(
        self,
        tickers: List[str],
        filters: Dict,
        profile: str = 'large-cap'
    ) -> List[Dict]:
        """Run screen on ticker list, return ranked results."""
        import time

        self._filter_counts = {}
        results = []
        total = len(tickers)

        print(f"Scanning {total} tickers with {profile} profile...")
        price_display = filters.get('min_price')
        price_label = f"${price_display}" if price_display is not None else 'disabled'
        print(f"  Filters: min_price={price_label}")

        try:
            from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn, TimeRemainingColumn

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                transient=False
            ) as progress:
                ticker_task = progress.add_task(f"Scanning {total} tickers", total=total)

                for ticker in tickers:
                    result = self._analyze_ticker(ticker, filters, profile)
                    if result:
                        results.append(result)
                    passed = self._filter_counts.get('passed', 0)
                    progress.update(ticker_task, advance=1,
                                    description=f"Scanning {ticker} — {passed} passed")

        except ImportError:
            for i, ticker in enumerate(tickers, 1):
                result = self._analyze_ticker(ticker, filters, profile)
                if result:
                    results.append(result)
                passed = self._filter_counts.get('passed', 0)
                print(f"  {ticker} ({i}/{total}) — {passed} passed")

        # Filter breakdown with active thresholds
        def _filter_label(key: str) -> str:
            if key == 'data':
                return 'no data'
            elif key == 'price':
                val = filters.get('min_price')
                return f'price floor (≥${val})' if val is not None else 'price floor'
            elif key == 'price_vs_10ma':
                val = filters.get('min_price_vs_10ma')
                return f'price vs 10MA (≥{val}%)' if val is not None else 'price vs 10MA'
            elif key == 'stage2':
                val = filters.get('min_stage2_score')
                return f'stage2 score (≥{val})' if val is not None else 'stage2 score'
            elif key == 'ma_stack_short':
                return 'MA stack (10>20>50)'
            elif key == 'ma_stack_long':
                return 'MA stack (50>150>200)'
            elif key == 'rs_near_high':
                val = filters.get('rs_near_high')
                return f'RS near high (≤{val}%)' if val is not None else 'RS near high'
            elif key == 'liquidity':
                val = filters.get('min_volume_shares')
                return f'liquidity (≥{val/1e6:.1f}M vol)' if val is not None else 'liquidity'
            elif key == 'passed':
                return 'passed'
            return key

        breakdown_order = ['data', 'price', 'price_vs_10ma', 'stage2',
                           'ma_stack_short', 'ma_stack_long', 'rs_near_high',
                           'liquidity', 'passed']
        print(f"\n  Filter breakdown:")
        for key in breakdown_order:
            count = self._filter_counts.get(key, 0)
            if count > 0:
                label = _filter_label(key)
                action = 'candidates' if key == 'passed' else 'rejected'
                print(f"    {label:<32} {count:>5} {action}")

        return results

    def rank_results(self, results: List[Dict], rank_by: str = 'setup') -> List[Dict]:
        """Sort results by specified criteria."""
        if not results:
            return []

        if rank_by == 'setup':
            return sorted(results, key=lambda x: (
                not x['entry_ready'],
                x['proximity_pct'],
            ))

        elif rank_by == 'rs':
            return sorted(results, key=lambda x: x['rs_from_high'])

        else:
            return results

    def display_results(
        self,
        results: List[Dict],
        show_ma_data: bool = False,
        top: int = 20,
        context: Optional[Dict] = None,
        entry_mode: str = 'any',
    ):
        """Print formatted results table using Rich."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.text import Text
            console = Console()
            use_rich = True
        except ImportError:
            use_rich = False

        if not results:
            print("\nNo results found matching criteria.")
            return

        # Run context header
        if context and use_rich:
            console.rule(style="dim")
            parts = []
            if context.get('profile'):
                parts.append(f"Profile: [bold]{context['profile']}[/bold]")
            if context.get('universe_size'):
                parts.append(f"Universe: [bold]{context['universe_size']:,}[/bold] tickers")
            if context.get('rank_by'):
                parts.append(f"Ranked by: [bold]{context['rank_by']}[/bold]")
            if context.get('filters_summary'):
                parts.append(f"Filters: {context['filters_summary']}")
            console.print("  " + "  |  ".join(parts))
            console.rule(style="dim")
        elif context:
            print(f"\n  Profile: {context.get('profile')}  |  "
                  f"Universe: {context.get('universe_size', '?'):,}  |  "
                  f"Ranked by: {context.get('rank_by', '?')}")

        show_entry_col = entry_mode != 'any'

        def _make_table(grade_name: str, icon: str, row_style: str) -> Table:
            table = Table(
                title=f"{icon} Top {top} {grade_name}",
                title_style=f"bold {row_style}",
                show_header=True,
                header_style="bold",
                border_style="dim",
                expand=False,
            )
            table.add_column("Ticker", style=row_style, no_wrap=True)
            table.add_column("Price", justify="right")
            table.add_column("Stage2", justify="right")
            table.add_column("To Pivot", justify="right")
            table.add_column("Vol Ratio", justify="right")
            if show_entry_col:
                table.add_column("Entry", justify="center")
            return table

        def _print_group_rich(group, grade_name, icon, row_style, table_style):
            if not group:
                return
            table = _make_table(grade_name, icon, table_style)
            display = group[:top]
            for r in display:
                row = [
                    r['ticker'],
                    f"${r['price']:.2f}",
                    str(r['stage2_score']),
                    f"{r['proximity_pct']:.1f}%",
                    f"{r['volume_ratio']:.1f}x",
                ]
                if show_entry_col:
                    row.append("READY" if r['entry_ready'] else "WAIT")
                table.add_row(*row)
                if show_ma_data:
                    ma_info = (f"MAs: 10={r['ma10']:.2f}  20={r['ma20']:.2f}  "
                               f"50={r['ma50']:.2f}  200={r['ma200']:.2f}")
                    table.add_row(f"  [dim]{ma_info}[/dim]", *[""] * (len(row) - 1))
            console.print(table)
            if len(group) > top:
                console.print(f"  [dim]... and {len(group) - top} more[/dim]")

        def _print_group_plain(group, grade_name, icon):
            if not group:
                return
            print(f"\n{icon} {grade_name} — {len(group)} candidates")
            print(f"{'=' * 80}")
            header = (f"{'Ticker':<8} {'Price':>8} {'Stage2':>6} "
                      f"{'To Pivot':>8} {'Vol Ratio':>9}")
            if show_entry_col:
                header += f" {'Entry':>6}"
            print(header)
            print('-' * 80)
            for r in group[:top]:
                row = (f"{r['ticker']:<8} ${r['price']:>7.2f} {r['stage2_score']:>6} "
                       f"{r['proximity_pct']:>7.1f}% "
                       f"{r['volume_ratio']:>8.1f}x")
                if show_entry_col:
                    row += f" {'READY' if r['entry_ready'] else 'WAIT':>6}"
                print(row)
            if len(group) > top:
                print(f"\n   ... and {len(group) - top} more")

        if use_rich:
            _print_group_rich(results, "Candidates", "📊", "white", "white")
        else:
            _print_group_plain(results, "Candidates", "📊")

        summary = f"\nTotal: {len(results)} candidates"
        if use_rich:
            console.rule(style="dim")
            console.print(summary)
        else:
            print(f"\n{'=' * 80}")
            print(summary)

    def export_results(
        self,
        results: List[Dict],
        format: str,
        path: Optional[str] = None
    ) -> str:
        """Export results to file."""
        if not path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = f"scans/trend_screen_{ts}.{format}"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        if format == 'csv':
            df = pd.DataFrame(results)
            # Capitalize Ticker column for backtest.py compatibility
            if 'ticker' in df.columns:
                df = df.rename(columns={'ticker': 'Ticker'})
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

    def export_watchlist(self, results: List[Dict], path: str) -> str:
        """Export minimal Ticker-only CSV for direct use with backtest.py --watchlist."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tickers = [r['ticker'] for r in results]
        pd.DataFrame({'Ticker': tickers}).to_csv(path, index=False)
        print(f"Watchlist exported ({len(tickers)} tickers) → {path}")
        return path


def main():
    parser = argparse.ArgumentParser(
        description='Trend Screener with MA Convergence Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discovery mode
  python3 %(prog)s --profile large-cap --rank-by setup --top 20

  # Rank watchlist by entry readiness
  python3 %(prog)s --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

  # Single ticker with MA details
  python3 %(prog)s --tickers AAPL MSFT --show-ma-data

  # Export to backtest pipeline
  python3 %(prog)s --profile large-cap --export-watchlist scans/watchlist_today.csv
        """
    )

    # Ticker sources
    parser.add_argument('--tickers', '-t', nargs='+', help='Specific tickers to scan')
    parser.add_argument('--ticker-file', '-f', help='File with tickers (one per line)')
    parser.add_argument('--refresh', action='store_true', help='Force refresh universe cache')

    # Discovery filters (MarketSurge-style)
    parser.add_argument('--min-price', type=float, default=None,
                        help='Minimum stock price (default: from profile config)')
    parser.add_argument('--min-price-vs-10ma', type=float, default=None,
                        help='Min %% above 10-day MA (default: from profile config; null in config = disabled)')
    parser.add_argument('--stack-short', action='store_true', default=True,
                        help='Require 10D > 21D > 50D')
    parser.add_argument('--stack-long', action='store_true', default=True,
                        help='Require 50D > 150D > 200D (default: on for large-cap, off for high-octane)')
    parser.add_argument('--rs-near-high', type=float, default=None,
                        help='RS line within %% of 52-week high (default: from profile config; null in config = disabled)')
    parser.add_argument('--exclude-etfs', action='store_true', default=True,
                        help='Exclude ETFs')

    # Liquidity filters
    parser.add_argument('--min-volume-dollar', type=float, default=None,
                        help='Min 50-day avg dollar volume')
    parser.add_argument('--min-volume-shares', type=float, default=None,
                        help='Min 50-day avg share volume')

    # Profile selection — any name defined in screener_config.yaml universes section
    parser.add_argument('--profile', default='large-cap',
                        help='Universe profile from config (default: large-cap). '
                             'Add custom profiles as YAML blocks in screener_config.yaml.')

    # Entry timing
    parser.add_argument('--entry-mode', choices=['any', 'vcp', 'pivot', 'volume'], default='any',
                        help='Entry timing mode (default: any)')
    parser.add_argument('--pivot-proximity', type=float, default=5,
                        help='Max %% from pivot (default: 5)')
    parser.add_argument('--min-volume-ratio', type=float, default=1.5,
                        help='Min volume vs 50-day avg for volume mode (default: 1.5)')

    # VCP specific
    parser.add_argument('--vcp-min-contractions', type=int, default=2,
                        help='Min contractions for VCP mode (default: 2)')
    parser.add_argument('--vcp-reversal-threshold', type=float, default=0.05,
                        help='Min %% reversal to detect swing (default: 5%%)')
    parser.add_argument('--detect-vcp', action='store_true',
                        help='Detect and display VCP pattern (sets --entry-mode vcp)')

    # Ranking and display
    parser.add_argument('--rank-by', choices=['setup', 'rs'], default='setup',
                        help='Sort criteria (default: setup)')
    parser.add_argument('--show-ma-data', action='store_true',
                        help='Display MA values and cluster details')
    parser.add_argument('--top', type=int, default=20,
                        help='Show top N results (default: 20)')
    # Export
    parser.add_argument('--export', '-e', choices=['csv', 'json', 'html', 'none'], default='csv',
                        help='Export full analysis (default: csv)')
    parser.add_argument('--export-path', help='Export file path')
    parser.add_argument('--export-watchlist', metavar='PATH',
                        help='Export Ticker-only CSV for backtest.py --watchlist')

    args = parser.parse_args()

    # Load profile config — this is the single source of truth for all defaults.
    # CLI flags override per-run; config defines the profile's baseline.
    _builder = UniverseBuilder()
    profile_key = args.profile.replace('-', '_')
    profile_cfg = _builder.get_profile_config(profile_key)

    if not profile_cfg:
        print(f"❌ Unknown profile '{args.profile}'. Add it to config/screener_config.yaml under 'universes:'.")
        sys.exit(1)

    # Resolve effective values: CLI flag wins if explicitly set, otherwise use config default.
    # None from config (null in YAML) means "disabled" for that filter.
    _explicit = set(sys.argv)
    effective_stack_long = args.stack_long if '--stack-long' in _explicit else profile_cfg.get('stack_long', True)
    effective_rs_near_high = args.rs_near_high if '--rs-near-high' in _explicit else profile_cfg.get('rs_near_high_pct')
    effective_min_price_vs_10ma = args.min_price_vs_10ma if '--min-price-vs-10ma' in _explicit else profile_cfg.get('min_price_vs_10ma')
    effective_min_price = args.min_price if args.min_price is not None else profile_cfg.get('min_price')
    effective_min_dollar_vol = args.min_volume_dollar if args.min_volume_dollar is not None else profile_cfg.get('min_dollar_volume')
    effective_min_share_vol = args.min_volume_shares if args.min_volume_shares is not None else profile_cfg.get('min_share_volume')
    effective_min_stage2 = profile_cfg.get('min_stage2_score')

    # Load tickers from explicit sources first
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

    universe_size = len(tickers)

    # Discovery mode: build universe from Alpaca
    if not tickers and args.profile:
        import time

        print("\n🔍 Discovery mode: building universe from Alpaca...")
        print(f"   Profile: {args.profile}")
        if args.refresh:
            print("   Force refresh: bypassing cache")

        try:
            start_build = time.time()
            builder = UniverseBuilder()

            try:
                from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn, TimeRemainingColumn

                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    MofNCompleteColumn(),
                    TextColumn("•"),
                    TimeRemainingColumn(),
                    transient=False,
                ) as progress:
                    prices_task = progress.add_task("Fetching prices...", total=1)
                    liquidity_task = progress.add_task("Computing liquidity...", total=1)
                    sectors_task = progress.add_task("Fetching sectors...", total=1)

                    def make_progress(update):
                        step = update.get("step", "")
                        current = update.get("current", 0)
                        total = update.get("total", 0)
                        if step == "prices":
                            progress.update(
                                prices_task,
                                completed=current,
                                total=total,
                                description=f"Fetching prices {current}/{total}",
                            )
                        elif step == "liquidity":
                            progress.update(
                                liquidity_task,
                                completed=current,
                                total=total,
                                description=f"Computing liquidity {current}/{total}",
                            )
                        elif step == "sectors":
                            progress.update(
                                sectors_task,
                                completed=current,
                                total=total,
                                description=f"Fetching sectors {current}/{total}",
                            )

                    result = builder.load_universe(
                        profile=args.profile.replace('-', '_'),
                        force_refresh=args.refresh,
                        progress_callback=make_progress,
                    )

            except ImportError:

                def make_progress(update):
                    print(f"    {update['message']}")

                result = builder.load_universe(
                    profile=args.profile.replace('-', '_'),
                    force_refresh=args.refresh,
                    progress_callback=make_progress,
                )

            build_time = time.time() - start_build

            print(f"\n📊 Universe Funnel:")
            print(f"   Total assets: {result.total_assets:,}")
            print(f"   After tradable filter: {result.after_tradable_filter:,}")
            print(f"   After price filter: {result.after_price_filter:,}")
            print(f"   After dollar volume filter: {result.after_dvol_filter:,}")

            if result.cache_hit:
                print(f"\n   Using cache ({result.cache_age_hours:.1f}h old)")
            else:
                print(f"\n   Built in {build_time:.1f}s")

            tickers = result.tickers
            universe_size = len(tickers)

            if not tickers:
                print("\n❌ No tickers found in universe. Try --refresh or check filters.")
                sys.exit(1)

        except Exception as e:
            print(f"\n❌ Error building universe: {e}")
            sys.exit(1)
    elif not tickers:
        watchlist_path = Path("data/watchlist.csv")
        if watchlist_path.exists():
            df = pd.read_csv(watchlist_path)
            if 'Ticker' in df.columns:
                tickers = df['Ticker'].dropna().unique().tolist()
            elif 'ticker' in df.columns:
                tickers = df['ticker'].dropna().unique().tolist()
        universe_size = len(tickers)

    if not tickers:
        print("Error: No tickers to scan. Provide --tickers, --ticker-file, or run with --profile")
        sys.exit(1)

    print(f"\nLoaded {universe_size:,} tickers")
    if universe_size > 50:
        print("   Note: structural filters (MA stacking, RS, liquidity) will further reduce this list.")

    entry_mode = 'vcp' if args.detect_vcp else args.entry_mode

    filters = {
        'min_price': effective_min_price,
        'min_price_vs_10ma': effective_min_price_vs_10ma,
        'stack_short': args.stack_short,
        'stack_long': effective_stack_long,
        'rs_near_high': effective_rs_near_high,
        'exclude_etfs': args.exclude_etfs,
        'min_volume_dollar': effective_min_dollar_vol,
        'min_volume_shares': effective_min_share_vol,
        'entry_mode': entry_mode,
        'pivot_proximity': args.pivot_proximity,
        'min_volume_ratio': args.min_volume_ratio,
        'vcp_min_contractions': args.vcp_min_contractions,
        'vcp_reversal_threshold': args.vcp_reversal_threshold,
        'vcp_require_volume': True,
        'min_stage2_score': effective_min_stage2,
    }

    # Build filters summary for context header
    active_filters = []
    if effective_min_price is not None:
        active_filters.append(f"price≥${effective_min_price}")
    if filters['stack_short']:
        active_filters.append("MA-short")
    if filters['stack_long']:
        active_filters.append("MA-long")
    if effective_rs_near_high is not None:
        active_filters.append(f"RS≤{effective_rs_near_high:.0f}%")

    context = {
        'profile': args.profile,
        'universe_size': universe_size,
        'rank_by': args.rank_by,
        'filters_summary': "  ".join(active_filters),
    }

    import time
    screener = TrendScreener()

    print(f"\n📈 Scanning for trending setups...")
    start_scan = time.time()
    results = screener.scan(tickers, filters, profile=args.profile)
    scan_time = time.time() - start_scan
    print(f"\n   Scan completed in {scan_time:.1f}s")

    ranked = screener.rank_results(results, rank_by=args.rank_by)

    screener.display_results(
        ranked,
        show_ma_data=args.show_ma_data,
        top=args.top,
        context=context,
        entry_mode=entry_mode,
    )

    export_format = args.export
    if export_format == 'none' and args.export_path:
        # Infer format from extension, default to csv
        ext = Path(args.export_path).suffix.lstrip('.').lower()
        export_format = ext if ext in ('csv', 'json', 'html') else 'csv'

    if export_format != 'none':
        screener.export_results(ranked, export_format, args.export_path)

    if args.export_watchlist:
        screener.export_watchlist(ranked, args.export_watchlist)


if __name__ == '__main__':
    main()
