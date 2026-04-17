#!/usr/bin/env python3
"""CLI entry point for backtesting.

Usage:
    python3 scripts/backtest.py --start 2024-01-01 --end 2024-12-31
    python3 scripts/backtest.py --start 2024-01-01 --end 2024-12-31 --watchlist data/watchlist.csv
    python3 scripts/backtest.py --start 2024-01-01 --end 2024-12-31 --tickers AAPL MSFT
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from traderlib.backtest.data_provider import AlpacaDataProvider, DictDataProvider
from traderlib.backtest.engine import BacktestEngine, BacktestConfig, BacktestProgress
from traderlib.backtest.execution import ExecutionConfig
from traderlib.backtest.report import BacktestReporter
from traderlib.backtest.strategy import Stage2MomentumStrategy, BacktestStrategyContext
from traderlib.strategies import get_strategy, list_strategies, StrategyContext
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfigManager


def main():
    available_strategies = list_strategies()
    strategy_help = f'Strategy to use (default: stage2_momentum). Available: {", ".join(available_strategies) if available_strategies else "stage2_momentum only"}'
    parser = argparse.ArgumentParser(description='Run backtest with configurable strategy')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100_000, help='Initial capital (default: $100,000)')
    parser.add_argument('--tickers', nargs='+', help='Ticker symbols to backtest')
    parser.add_argument('--watchlist', type=Path, help='Path to watchlist CSV')
    parser.add_argument('--risk-profile', default='conservative', help='Risk profile (default: conservative)')
    parser.add_argument('--slippage', type=float, default=5.0, help='Slippage in bps (default: 5)')
    parser.add_argument('--max-positions', type=int, default=10, help='Max open positions (default: 10)')
    parser.add_argument('--csv', help='Export trades to CSV file')
    parser.add_argument('--trades', action='store_true', help='Show all trades in report')
    parser.add_argument('--dry-run', action='store_true', help='Validate config without running')
    parser.add_argument('--alpaca-mode', choices=['data-only', 'paper'], default='data-only',
                        help='Alpaca connection mode (default: data-only — data endpoint only, no trading client)')
    parser.add_argument('--strategy', default='stage2_momentum', help=strategy_help)

    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Execution config
    exec_config = ExecutionConfig(
        slippage_bps=args.slippage,
    )

    # Resolve watchlist path - look in data/ folder by default if not absolute
    watchlist_path = args.watchlist
    if watchlist_path and not watchlist_path.is_absolute():
        # First try data/ folder, then project root
        data_path = PROJECT_ROOT / 'data' / watchlist_path.name
        if data_path.exists():
            watchlist_path = data_path
        else:
            watchlist_path = PROJECT_ROOT / watchlist_path

    # Load watchlist CSV into DataFrame for date-aware filtering
    watchlist_df = None
    if watchlist_path and not args.tickers:
        try:
            watchlist_df = pd.read_csv(watchlist_path)
            ticker_col = 'Ticker' if 'Ticker' in watchlist_df.columns else 'ticker' if 'ticker' in watchlist_df.columns else None
            if ticker_col:
                args.tickers = watchlist_df[ticker_col].dropna().unique().tolist()
        except Exception:
            pass  # Engine will handle via _load_watchlist

    # Backtest config
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        tickers=args.tickers,
        watchlist_path=watchlist_path,
        risk_profile=args.risk_profile,
        execution_config=exec_config,
        max_open_positions=args.max_positions,
    )

    if args.dry_run:
        print(f"Start:          {config.start_date}")
        print(f"End:            {config.end_date}")
        print(f"Capital:        ${config.initial_capital:,.0f}")
        print(f"Risk Profile:   {config.risk_profile}")
        print(f"Slippage:       {exec_config.slippage_bps} bps")
        print(f"Max Positions:  {config.max_open_positions}")
        print(f"Strategy:       {args.strategy}")
        print("Dry run — no backtest executed.")
        return

    # Initialize components
    try:
        from traderlib.alpaca_client import AlpacaClient
        alpaca = AlpacaClient(mode=args.alpaca_mode, data_only=(args.alpaca_mode == 'data-only'))
        data_provider = AlpacaDataProvider(alpaca_client=alpaca.data_client)
    except Exception as e:
        print(f"Warning: Alpaca client unavailable ({e})")
        print("Backtest requires Alpaca data. Set ALPACA_API_KEY and ALPACA_SECRET_KEY.")
        sys.exit(1)

    risk_config = RiskConfigManager(profile=args.risk_profile).get_config()
    exit_engine = ExitEngine(risk_config=risk_config)

    # Initialize strategy - support both legacy and registered strategies
    strategy = None
    if args.strategy == 'stage2_momentum':
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=args.tickers,
            watchlist_df=watchlist_df,
            risk_config=risk_config,
            execution_config=exec_config,
        )
    else:
        # Try to load from registry
        # VCP strategies only accept risk_config and profile
        strategy_kwargs = {'risk_config': risk_config}
        if args.strategy in ['vcp_large_cap', 'vcp_high_octane']:
            strategy_kwargs['profile'] = args.strategy.split('_')[1]  # 'large' or 'high'
            if args.strategy == 'vcp_high_octane':
                strategy_kwargs['profile'] = 'high_octane'
        strategy = get_strategy(args.strategy, **strategy_kwargs)
        if strategy is None:
            available = list_strategies()
            print(f"Error: Unknown strategy '{args.strategy}'")
            print(f"Available strategies: {', '.join(available) if available else 'none registered'}")
            print("Use --strategy stage2_momentum for default behavior")
            sys.exit(1)

    print(f"Using strategy: {strategy.name}")

    engine = BacktestEngine(data_provider, strategy, config)

    print(f"Running backtest: {start_date} to {end_date}")
    print(f"Initial capital: ${args.capital:,.0f}")
    print()

    # Rich progress bar during backtest
    try:
        from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.fields[detail]}", style="dim"),
            transient=True,
        ) as progress:
            prefetch_task = progress.add_task(
                "Fetching data", total=0, detail="",
            )
            sim_task = progress.add_task(
                "Simulating", total=0, detail="",
            )

            def _on_progress(p: BacktestProgress):
                if p.phase == "prefetch":
                    progress.update(
                        prefetch_task,
                        total=p.total,
                        completed=p.current,
                        detail=p.ticker or "",
                    )
                elif p.phase == "simulation":
                    detail = (
                        f"{p.sim_date}  Pos:{p.positions}  "
                        f"${p.equity:,.0f}  Trades:{p.trades}"
                    )
                    progress.update(
                        sim_task,
                        total=p.total,
                        completed=p.current,
                        detail=detail,
                    )

            config.on_progress = _on_progress
            try:
                result = engine.run()
            except KeyboardInterrupt:
                print("\n  Interrupted during data fetch. No results to show.")
                sys.exit(1)

    except ImportError:
        # Fallback: plain-text progress
        import sys

        def _on_progress(p: BacktestProgress):
            if p.phase == "prefetch":
                msg = f"\rFetching data: {p.current}/{p.total} {p.ticker or ''}"
            elif p.phase == "simulation":
                msg = (
                    f"\rSimulating: {p.current}/{p.total} "
                    f"{p.sim_date}  Pos:{p.positions}  "
                    f"${p.equity:,.0f}  Trades:{p.trades}"
                )
            else:
                return
            sys.stdout.write(f"{msg:<80}")
            sys.stdout.flush()

        config.on_progress = _on_progress
        try:
            result = engine.run()
        except KeyboardInterrupt:
            print("\n  Interrupted during data fetch. No results to show.")
            sys.exit(1)
        print()  # newline after \r progress

    if result.partial:
        print("  Interrupted — showing partial results\n")

    # Generate and print report (Rich by default, plain fallback)
    report = BacktestReporter.generate(result)
    BacktestReporter.print_report_rich(report, show_all_trades=args.trades)

    # Export if requested
    if args.csv:
        BacktestReporter.to_csv(result, args.csv)
        print(f"Trades exported to {args.csv}")


if __name__ == '__main__':
    main()