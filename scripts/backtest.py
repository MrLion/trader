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
import yaml

# Add project root to path
from traderlib.paths import data_dir, project_root
PROJECT_ROOT = project_root()
sys.path.insert(0, str(PROJECT_ROOT))

from traderlib.backtest.data_provider import AlpacaDataProvider, DictDataProvider
from traderlib.backtest.engine import BacktestEngine, BacktestConfig, BacktestProgress
from traderlib.backtest.execution import ExecutionConfig
from traderlib.backtest.report import BacktestReporter
from traderlib.backtest.strategy import Stage2MomentumStrategy, BacktestStrategyContext
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfigManager


def _get_backtest_save_path(
    risk_profile: str,
    profit_mode: str,
    strategy: str,
    backtests_dir: Path,
) -> Path:
    """Generate timestamped folder path for backtest results.

    Format: YYYY-MM-DD_HHMMSS_MMM_risk_profile_profit_mode_strategy/
    """
    from datetime import datetime

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    milliseconds = f"{now.microsecond // 1000:03d}"

    # Sanitize strategy name (remove underscores for cleaner folder names)
    strategy_clean = strategy.replace("_", "")

    folder_name = f"{timestamp}_{milliseconds}_{risk_profile}_{profit_mode}_{strategy_clean}"
    return backtests_dir / folder_name


def _save_backtest_results(
    result,
    report,
    risk_profile: str,
    profit_mode: str,
    strategy: str,
    version: str,
    backtests_dir: Path = None,
) -> Path:
    """Save backtest results to timestamped folder.

    Creates:
    - trades.csv: Clean trade data
    - equity.csv: Daily equity curve
    - config.txt: Human-readable configuration + results

    Returns the path to the created folder.
    """
    if backtests_dir is None:
        backtests_dir = data_dir() / 'backtests'

    # Ensure directory exists
    backtests_dir.mkdir(parents=True, exist_ok=True)

    # Generate folder path
    folder_path = _get_backtest_save_path(risk_profile, profit_mode, strategy, backtests_dir)
    folder_path.mkdir(parents=True, exist_ok=True)

    # Generate timestamp prefix for files (matching folder)
    timestamp_prefix = folder_path.name.rsplit('_', 3)[0]  # Keep timestamp + milliseconds

    # Write trades.csv
    trades_path = folder_path / f"{timestamp_prefix}_trades.csv"
    _write_trades_csv(result, trades_path)

    # Write equity.csv
    equity_path = folder_path / f"{timestamp_prefix}_equity.csv"
    _write_equity_csv(result, equity_path)

    # Write config.txt
    config_path = folder_path / f"{timestamp_prefix}_config.txt"
    _write_config_txt(result, report, risk_profile, profit_mode, strategy, version, config_path)

    return folder_path


def _write_equity_csv(result, filepath: Path) -> None:
    """Write equity curve to CSV."""
    import csv

    fieldnames = ['date', 'equity']

    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for d, v in result.equity_curve:
            writer.writerow({
                'date': str(d),
                'equity': v,
            })


def _write_trades_csv(result, filepath: Path) -> None:
    """Write clean trade data to CSV."""
    import csv

    fieldnames = [
        'ticker', 'entry_date', 'exit_date', 'entry_price', 'exit_price',
        'shares', 'pnl', 'r_multiple', 'exit_reason', 'pivot_price'
    ]

    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for t in result.trades:
            # Calculate R-multiple
            risk = _trade_initial_risk(t)
            r_multiple = t.pnl / risk if risk > 0 else 0.0

            # Get pivot price if available
            pivot_price = getattr(t, 'pivot_price', None)

            writer.writerow({
                'ticker': t.ticker,
                'entry_date': str(t.entry_date),
                'exit_date': str(t.exit_date) if t.exit_date else '',
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'shares': t.shares,
                'pnl': t.pnl,
                'r_multiple': round(r_multiple, 2),
                'exit_reason': t.exit_reason,
                'pivot_price': pivot_price if pivot_price else '',
            })


def _trade_initial_risk(t) -> float:
    """Return the dollar initial risk for a trade."""
    # Phase 4: pivot-aware risk calculation for breakout entries
    if getattr(t, 'pivot_price', None) and t.pivot_price > 0:
        if getattr(t, 'initial_stop_price', 0.0) and t.initial_stop_price < t.pivot_price:
            return abs(t.pivot_price - t.initial_stop_price) * t.shares

    # Legacy: entry_price -> stop
    if getattr(t, 'initial_stop_price', 0.0) and t.initial_stop_price < t.entry_price and t.shares > 0:
        return abs(t.entry_price - t.initial_stop_price) * t.shares

    # Ultra-legacy: approximate 7% stop distance
    return abs(t.entry_price * 0.07 * t.shares) if t.shares > 0 else 1.0


def _write_config_txt(
    result,
    report,
    risk_profile: str,
    profit_mode: str,
    strategy: str,
    version: str,
    filepath: Path,
) -> None:
    """Write human-readable configuration and results summary."""
    from datetime import datetime

    config = result.config
    risk_config = getattr(result, '_risk_config', None)

    # Get current timestamp
    now = datetime.now()
    run_timestamp = now.strftime("%Y-%m-%d at %H:%M:%S")

    # Load full risk config for detailed settings
    risk_details = {}
    try:
        manager = RiskConfigManager(profile=risk_profile, quiet=True)
        full_config = manager.get_config()
        if full_config:
            risk_details = {
                'risk_per_trade_pct': getattr(full_config.account, 'risk_per_trade_pct', 0.005),
                'daily_loss_limit_pct': getattr(full_config.account, 'daily_loss_limit_pct', 0.02),
                'max_position_pct': getattr(full_config.position, 'max_position_pct', 0.10),
                'min_position_pct': getattr(full_config.position, 'min_position_pct', 0.05),
                'stop_method': getattr(full_config.stop_loss, 'method', 'atr_or_support'),
                'atr_multiplier': getattr(full_config.stop_loss, 'atr_multiplier', 2.0),
            }
    except Exception:
        # Use defaults if config loading fails
        risk_details = {
            'risk_per_trade_pct': 0.005,
            'daily_loss_limit_pct': 0.02,
            'max_position_pct': 0.10,
            'min_position_pct': 0.05,
            'stop_method': 'atr_or_support',
            'atr_multiplier': 2.0,
        }

    # Get profit target details based on mode
    profit_details = _get_profit_target_details(profit_mode, risk_details)

    # Format slippage
    slippage_bps = getattr(config, 'execution_config', None)
    slippage_bps = getattr(slippage_bps, 'slippage_bps', 5.0) if slippage_bps else 5.0

    lines = [
        f"Backtest Run: {run_timestamp}",
        f"Version: {version}",
        "",
        f"Risk Profile: {risk_profile}",
        f"  Risk per trade: {risk_details.get('risk_per_trade_pct', 0.005) * 100:.1f}%",
        f"  Max position: {risk_details.get('max_position_pct', 0.10) * 100:.0f}%",
        f"  Daily loss limit: {risk_details.get('daily_loss_limit_pct', 0.02) * 100:.0f}%",
        "",
        f"Strategy: {strategy}",
        f"Profit Target: {profit_mode}",
    ]

    # Add profit target details
    lines.extend(profit_details)
    lines.append("")

    # Stop loss details
    lines.extend([
        f"Stop Loss: {risk_details.get('stop_method', 'atr_or_support')}",
        f"  ATR multiplier: {risk_details.get('atr_multiplier', 2.0):.0f}x",
        "",
        "Execution:",
        f"  Slippage: {slippage_bps:.0f} bps",
        f"  Earnings filter: {'enabled' if getattr(config, 'enable_earnings_filter', False) else 'disabled'}",
        "",
        "Backtest:",
        f"  Date range: {config.start_date} to {config.end_date}",
        f"  Initial capital: ${config.initial_capital:,.0f}",
        f"  Max positions: {config.max_open_positions}",
        "",
        "Results:",
        f"  Total Return: {report.total_return * 100:.1f}%",
        f"  Win Rate: {report.win_rate * 100:.1f}%",
        f"  Avg R-Multiple: {report.avg_r_multiple:.2f}",
        f"  Sharpe: {report.sharpe_ratio:.2f}",
        f"  Trades: {len(report.trades)}",
    ])

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))


def _get_profit_target_details(profit_mode: str, risk_details: dict) -> list:
    """Get human-readable profit target configuration lines."""
    lines = []

    if profit_mode == 'target':
        lines.append("  Sell at 2R: 100%")
    elif profit_mode == 'trailing':
        lines.append("  Breakeven at 2R: protect capital")
        lines.append("  Trail 10 EMA at 3R: tight stop")
        lines.append("  Trail 21 EMA at 5R: room for trend")
    elif profit_mode == 'hybrid':
        lines.append("  Scale out at 3R: 33%")
        lines.append("  Scale out at 4R: 50% of remaining")
        lines.append("  Trail remainder until EMA stop")
    else:
        lines.append("  (custom configuration)")

    return lines


parser = argparse.ArgumentParser(description='Run backtest with configurable strategy')
parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
parser.add_argument('--capital', type=float, default=100_000, help='Initial capital (default: $100,000)')
parser.add_argument('--tickers', nargs='+', help='Ticker symbols to backtest')
parser.add_argument('--watchlist', type=Path, help='Path to watchlist CSV')
parser.add_argument('--risk-profile', default='conservative', help='Risk profile (default: conservative)')
parser.add_argument('--slippage', type=float, default=5.0, help='Slippage in bps (default: 5)')
parser.add_argument('--max-positions', type=int, default=10, help='Max open positions (default: 10)')
parser.add_argument('--csv', help='Export trades to CSV file (deprecated: auto-save is now default)')
parser.add_argument('--trades', action='store_true', help='Show all trades in report')
parser.add_argument('--dry-run', action='store_true', help='Validate config without running')
parser.add_argument('--no-save', action='store_true', help='Skip saving backtest results to disk (for quick testing)')
parser.add_argument('--alpaca-mode', choices=['data-only', 'paper'], default='data-only',
                    help='Alpaca connection mode (default: data-only — data endpoint only, no trading client)')
parser.add_argument('--strategy', default='stage2_momentum', help='Deprecated. Only stage2_momentum is supported.')


def main():
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Load backtest config YAML for earnings filter setting
    backtest_config_path = PROJECT_ROOT / 'config' / 'backtest_config.yaml'
    enable_earnings_filter = False
    try:
        if backtest_config_path.exists():
            with open(backtest_config_path) as f:
                bt_config = yaml.safe_load(f)
                if bt_config and 'earnings' in bt_config:
                    enable_earnings_filter = bt_config['earnings'].get('enable_filter', False)
    except Exception:
        pass  # Fail open - continue without earnings filter

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
            # Parse week_start as datetime so timestamp comparisons work
            if 'week_start' in watchlist_df.columns:
                watchlist_df['week_start'] = pd.to_datetime(watchlist_df['week_start'])
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
        enable_earnings_filter=enable_earnings_filter,
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
        # Use the same rate limit as AlpacaClient (respects paid tier config)
        alpaca_rate_limit = alpaca.rate_limiter.max_requests
        data_provider = AlpacaDataProvider(
            alpaca_client=alpaca.data_client,
            max_requests_per_min=alpaca_rate_limit,
        )
    except Exception as e:
        print(f"Warning: Alpaca client unavailable ({e})")
        print("Backtest requires Alpaca data. Set ALPACA_API_KEY and ALPACA_SECRET_KEY.")
        sys.exit(1)

    risk_config = RiskConfigManager(profile=args.risk_profile).get_config()
    exit_engine = ExitEngine(risk_config=risk_config)

    # Initialize strategy
    if args.strategy != 'stage2_momentum':
        print(f"⚠️  --strategy is deprecated; only stage2_momentum is supported")
    strategy = Stage2MomentumStrategy(
        exit_engine=exit_engine,
        watchlist_tickers=args.tickers,
        watchlist_df=watchlist_df,
        risk_config=risk_config,
        execution_config=exec_config,
    )

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

    # Print entry filter breakdown for strategies that support it
    if hasattr(strategy, 'get_rejection_summary') and strategy.rejection_counts['scanned'] > 0:
        if strategy.rejection_counts['signals'] == 0 or args.trades:
            print(strategy.get_rejection_summary())

    # Generate and print report (Rich by default, plain fallback)
    report = BacktestReporter.generate(result)
    BacktestReporter.print_report_rich(report, show_all_trades=args.trades)

    # Auto-save backtest results (unless --no-save is specified)
    if not args.no_save:
        # Load version
        version = "0.6.12.1"  # Default fallback
        try:
            version_path = PROJECT_ROOT / 'VERSION'
            if version_path.exists():
                version = version_path.read_text().strip()
        except Exception:
            pass

        # Get profit mode from risk config
        profit_mode = 'target'  # Default
        try:
            risk_config_manager = RiskConfigManager(profile=args.risk_profile, quiet=True)
            risk_config = risk_config_manager.get_config()
            if risk_config and hasattr(risk_config, 'profit_target') and risk_config.profit_target:
                profit_mode = getattr(risk_config.profit_target, 'mode', 'target')
        except Exception:
            pass  # Keep default

        # Save results
        save_path = _save_backtest_results(
            result=result,
            report=report,
            risk_profile=args.risk_profile,
            profit_mode=profit_mode,
            strategy=strategy.name,
            version=version,
        )
        print(f"Backtest results saved to: {save_path}")
    else:
        print("Backtest results not saved (--no-save specified)")

    # Export if requested (legacy CSV support - deprecated)
    if args.csv:
        BacktestReporter.to_csv(result, args.csv)
        print(f"Trades exported to {args.csv}")


if __name__ == '__main__':
    main()