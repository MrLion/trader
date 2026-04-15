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

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from traderlib.backtest.data_provider import AlpacaDataProvider, DictDataProvider
from traderlib.backtest.engine import BacktestEngine, BacktestConfig
from traderlib.backtest.execution import ExecutionConfig
from traderlib.backtest.report import BacktestReporter
from traderlib.backtest.strategy import Stage2MomentumStrategy
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfigManager


def main():
    parser = argparse.ArgumentParser(description='Run backtest for Stage 2 momentum strategy')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100_000, help='Initial capital (default: $100,000)')
    parser.add_argument('--tickers', nargs='+', help='Ticker symbols to backtest')
    parser.add_argument('--watchlist', type=Path, help='Path to watchlist CSV')
    parser.add_argument('--risk-profile', default='conservative', help='Risk profile (default: conservative)')
    parser.add_argument('--slippage', type=float, default=5.0, help='Slippage in bps (default: 5)')
    parser.add_argument('--commission', type=float, default=0.005, help='Commission per share (default: $0.005)')
    parser.add_argument('--max-positions', type=int, default=10, help='Max open positions (default: 10)')
    parser.add_argument('--csv', help='Export trades to CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Validate config without running')
    parser.add_argument('--alpaca-mode', choices=['data-only', 'paper'], default='data-only',
                        help='Alpaca connection mode (default: data-only — data endpoint only, no trading client)')

    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Execution config
    exec_config = ExecutionConfig(
        commission_per_share=args.commission,
        slippage_bps=args.slippage,
    )

    # Backtest config
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        tickers=args.tickers,
        watchlist_path=args.watchlist,
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
        print(f"Commission:     ${exec_config.commission_per_share}/share")
        print(f"Max Positions:  {config.max_open_positions}")
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
    strategy = Stage2MomentumStrategy(
        exit_engine=exit_engine,
        watchlist_tickers=args.tickers,
        risk_config=risk_config,
        execution_config=exec_config,
    )

    engine = BacktestEngine(data_provider, strategy, config)

    print(f"Running backtest: {start_date} to {end_date}")
    print(f"Initial capital: ${args.capital:,.0f}")
    print()

    result = engine.run()

    # Generate and print report
    report = BacktestReporter.generate(result)
    BacktestReporter.print_report(report)

    # Export if requested
    if args.csv:
        BacktestReporter.to_csv(result, args.csv)
        print(f"Trades exported to {args.csv}")

    # Gap rejections
    if result.gap_rejections:
        print(f"\nGap Rejections: {len(result.gap_rejections)} entries rejected")
        for rej in result.gap_rejections[:5]:
            print(f"  {rej['ticker']} on {rej['date']}: "
                  f"open ${rej['open_price']:.2f} below stop ${rej['stop_price']:.2f}")
        if len(result.gap_rejections) > 5:
            print(f"  ... and {len(result.gap_rejections) - 5} more")


if __name__ == '__main__':
    main()