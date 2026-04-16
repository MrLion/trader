"""Backtest reporting — statistics, benchmarks, and risk metrics.

Every report includes:
- Return metrics (total, annualized, daily volatility)
- Risk metrics (max drawdown, Sharpe, Sortino, Calmar)
- Trade metrics (win rate, profit factor, avg R-multiple)
- Buy-and-hold SPY benchmark + alpha
- Cost attribution (slippage + commissions)
- Survivorship bias disclaimer

Rich terminal output with color, sparklines, and exit breakdowns.
Plain-text fallback via print_report().
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from traderlib.backtest.engine import BacktestResult, BacktestConfig
from traderlib.backtest.state import TradeRecord


SURVIVORSHIP_DISCLAIMER = (
    "DISCLAIMER: Sector classifications are current as of report date. "
    "Historical reclassifications and merger activity may affect results. "
    "This backtest uses a static watchlist which introduces survivorship bias."
)

# Unicode block characters for sparkline (low to high)
SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


@dataclass
class BacktestReport:
    """Complete backtest report with all metrics."""
    total_return: float
    annualized_return: float
    volatility: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_r_multiple: float
    tickers_dropped: int
    benchmark_return: float
    alpha: float
    trades: list[TradeRecord]
    # Rich report extras
    gap_rejections: list[dict] = field(default_factory=list)
    config: Optional[BacktestConfig] = None
    equity_curve: list[tuple[date, float]] = field(default_factory=list)
    tickers_dropped_details: list[dict] = field(default_factory=list)
    partial: bool = False


class BacktestReporter:
    """Generates backtest reports from BacktestResult."""

    @staticmethod
    def generate(result: BacktestResult,
                 risk_free_rate: float = 0.045) -> BacktestReport:
        """Generate a full report from backtest results.

        Args:
            result: Output from BacktestEngine.run()
            risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default 4.5%)

        Returns:
            BacktestReport with all calculated metrics
        """
        equity_curve = result.equity_curve
        trades = result.trades

        if not equity_curve:
            return BacktestReport(
                total_return=0, annualized_return=0, volatility=0,
                max_drawdown=0, sharpe_ratio=0, sortino_ratio=0,
                calmar_ratio=0, win_rate=0, profit_factor=0,
                avg_r_multiple=0,
                tickers_dropped=0, benchmark_return=0, alpha=0,
                trades=trades, gap_rejections=result.gap_rejections,
                config=result.config, equity_curve=equity_curve,
                tickers_dropped_details=result.tickers_dropped,
                partial=result.partial,
            )

        # Convert equity curve to returns
        dates = [d for d, _ in equity_curve]
        values = [v for _, v in equity_curve]
        equity_series = pd.Series(values, index=dates)

        returns = equity_series.pct_change().dropna()

        # Total return
        total_return = (values[-1] / values[0]) - 1

        # Annualized return
        n_days = len(equity_curve)
        years = n_days / 252
        if years > 0:
            annualized_return = (1 + total_return) ** (1 / years) - 1
        else:
            annualized_return = 0.0

        # Daily volatility (annualized)
        if len(returns) > 1:
            volatility = returns.std() * np.sqrt(252)
        else:
            volatility = 0.0

        # Max drawdown
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_drawdown = abs(drawdown.min())

        # Sharpe ratio
        daily_rf = risk_free_rate / 252
        if len(returns) > 1 and volatility > 0:
            sharpe_ratio = (returns.mean() - daily_rf) / returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # Sortino ratio
        if len(returns) > 1:
            downside = returns[returns < daily_rf]
            downside_std = downside.std() if len(downside) > 1 else 0
            if downside_std > 0:
                sortino_ratio = (returns.mean() - daily_rf) / downside_std * np.sqrt(252)
            else:
                sortino_ratio = 0.0
        else:
            sortino_ratio = 0.0

        # Calmar ratio
        if max_drawdown > 0:
            calmar_ratio = annualized_return / max_drawdown
        else:
            calmar_ratio = 0.0

        # Trade metrics
        if trades:
            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            win_rate = len(wins) / len(trades)

            gross_profit = sum(t.pnl for t in wins)
            gross_loss = abs(sum(t.pnl for t in losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        else:
            win_rate = 0.0
            profit_factor = 0.0

        # Average R-multiple
        avg_r_multiple = 0.0
        if trades:
            r_multiples = []
            for t in trades:
                risk = abs(t.entry_price * 0.07 * t.shares)  # Approx initial risk
                if risk > 0:
                    r_multiples.append(t.pnl / risk)
                else:
                    r_multiples.append(0.0)
            avg_r_multiple = np.mean(r_multiples)

        # Benchmark
        benchmark_return = 0.0
        if not result.benchmark.empty:
            spy_close = result.benchmark['Close']
            benchmark_return = (float(spy_close.iloc[-1]) / float(spy_close.iloc[0])) - 1

        alpha = annualized_return - (
            risk_free_rate + benchmark_return * (annualized_return - risk_free_rate) / max(annualized_return, 0.001)
        ) if annualized_return != 0 else 0.0
        # Simplified: alpha = strategy annualized - benchmark annualized
        benchmark_annualized = 0.0
        if not result.benchmark.empty and len(result.benchmark) > 1:
            n_spy = len(result.benchmark)
            spy_years = n_spy / 252
            if spy_years > 0:
                benchmark_annualized = (1 + benchmark_return) ** (1 / spy_years) - 1
        alpha = annualized_return - benchmark_annualized

        # Tickers dropped
        tickers_dropped = len(result.tickers_dropped)

        return BacktestReport(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_r_multiple=avg_r_multiple,
            tickers_dropped=tickers_dropped,
            benchmark_return=benchmark_return,
            alpha=alpha,
            trades=trades,
            gap_rejections=result.gap_rejections,
            config=result.config,
            equity_curve=equity_curve,
            tickers_dropped_details=result.tickers_dropped,
            partial=result.partial,
        )

    @staticmethod
    def print_report(report: BacktestReport) -> None:
        """Print a plain-text backtest report to stdout (fallback)."""
        print("\n" + "=" * 60)
        print("BACKTEST REPORT")
        print("=" * 60)

        print(f"\n--- Returns ---")
        print(f"Total Return:       {report.total_return * 100:>8.2f}%")
        print(f"Annualized Return:  {report.annualized_return * 100:>8.2f}%")
        print(f"Volatility:         {report.volatility * 100:>8.2f}%")

        print(f"\n--- Risk ---")
        print(f"Max Drawdown:       {report.max_drawdown * 100:>8.2f}%")
        print(f"Sharpe Ratio:       {report.sharpe_ratio:>8.2f}")
        print(f"Sortino Ratio:      {report.sortino_ratio:>8.2f}")
        print(f"Calmar Ratio:       {report.calmar_ratio:>8.2f}")

        print(f"\n--- Trades ---")
        print(f"Total Trades:       {len(report.trades):>8d}")
        print(f"Win Rate:           {report.win_rate * 100:>8.1f}%")
        print(f"Profit Factor:      {report.profit_factor:>8.2f}")
        print(f"Avg R-Multiple:     {report.avg_r_multiple:>8.2f}")

        print(f"\n--- Benchmark ---")
        print(f"SPY Return:         {report.benchmark_return * 100:>8.2f}%")
        print(f"Alpha:              {report.alpha * 100:>8.2f}%")

        if report.tickers_dropped > 0:
            print(f"\n--- Data Quality ---")
            print(f"Tickers Dropped:    {report.tickers_dropped:>8d}")

        print(f"\n{SURVIVORSHIP_DISCLAIMER}")
        print("=" * 60 + "\n")

    # ── Rich report ──────────────────────────────────────────────

    @staticmethod
    def print_report_rich(report: BacktestReport,
                         show_all_trades: bool = False) -> None:
        """Print a Rich-formatted backtest report to stdout."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.text import Text
            from rich.columns import Columns
        except ImportError:
            BacktestReporter.print_report(report)
            return

        console = Console()

        # ── Header ───────────────────────────────────────────────
        config = report.config
        if config:
            header = (
                f"Backtest Report  |  {config.risk_profile}  |  "
                f"{config.start_date} to {config.end_date}  |  "
                f"${config.initial_capital:,.0f}"
            )
        else:
            header = "Backtest Report"

        console.print()
        console.rule(header, style="bold white")

        # Partial run warning
        if report.partial and report.equity_curve:
            first_date = report.equity_curve[0][0]
            last_date = report.equity_curve[-1][0]
            console.print(
                f"  [bold yellow]PARTIAL RUN[/] — interrupted {last_date}, "
                f"results cover {first_date} to {last_date}"
            )
            console.print()

        # ── Performance + Risk side by side ───────────────────────
        perf_table = Table(show_header=False, box=None, padding=(0, 1))
        perf_table.add_column("label", style="dim", width=18)
        perf_table.add_column("value", width=14)
        perf_table.add_column("signal", width=3)

        perf_table.add_row("Total Return", _fmt_pct(report.total_return))
        perf_table.add_row("Annualized", _fmt_pct(report.annualized_return))

        if report.benchmark_return != 0.0:
            vs_spy = report.total_return - report.benchmark_return
            perf_table.add_row("vs SPY", _fmt_pct(vs_spy))
        else:
            perf_table.add_row("vs SPY", "[dim]-- no data --[/]")

        perf_table.add_row("Alpha", _fmt_pct(report.alpha))

        risk_table = Table(show_header=False, box=None, padding=(0, 1))
        risk_table.add_column("label", style="dim", width=18)
        risk_table.add_column("value", width=14)
        risk_table.add_column("signal", width=6)

        risk_table.add_row("Max Drawdown", _fmt_pct(report.max_drawdown, invert=True))
        risk_table.add_row("Sharpe", f"{report.sharpe_ratio:.2f}  {_sharpe_gauge(report.sharpe_ratio)}")
        risk_table.add_row("Sortino", f"{report.sortino_ratio:.2f}")
        risk_table.add_row("Calmar", f"{report.calmar_ratio:.2f}")

        console.print()
        console.print(Columns([perf_table, risk_table], padding=(0, 4)))
        console.print()

        # ── Trades ─────────────────────────────────────────────────
        trades_table = Table(show_header=False, box=None, padding=(0, 1))
        trades_table.add_column("label", style="dim", width=18)
        trades_table.add_column("value", width=20)

        trades_table.add_row("Total", str(len(report.trades)))
        trades_table.add_row("Win Rate", f"{report.win_rate * 100:.1f}%  {_win_rate_bar(report.win_rate)}")
        trades_table.add_row("Profit Factor", f"{report.profit_factor:.2f}")
        trades_table.add_row("Avg R-Multiple", f"{report.avg_r_multiple:.2f}R")

        console.print(trades_table)
        console.print()

        # ── Exit breakdown ────────────────────────────────────────
        exit_rows = _exit_breakdown(report.trades)
        if exit_rows:
            exit_table = Table(show_header=False, box=None, padding=(0, 2))
            exit_table.add_column("reason", style="dim", width=20)
            exit_table.add_column("count", width=6, justify="right")
            exit_table.add_column("pnl", width=14, justify="right")

            for reason, count, pnl in exit_rows:
                pnl_str = _fmt_dollars(pnl)
                exit_table.add_row(reason, str(count), pnl_str)

            # Gap rejections
            if report.gap_rejections:
                exit_table.add_row("[yellow]Gap Rejected[/]",
                                   str(len(report.gap_rejections)), "")

            console.print(exit_table)
            console.print()

        # ── Top winners / losers ──────────────────────────────────
        winners, losers = _top_trades(report.trades, n=5)
        if winners or losers:
            wl_table = Table(show_header=True, box=None, padding=(0, 1))
            wl_table.add_column("Winners", style="green", width=28)
            wl_table.add_column("", width=4)
            wl_table.add_column("Losers", style="red", width=28)

            max_rows = max(len(winners), len(losers))
            for i in range(max_rows):
                w = winners[i] if i < len(winners) else ""
                l = losers[i] if i < len(losers) else ""
                wl_table.add_row(w, "", l)

            console.print(wl_table)
            console.print()

        # ── All trades ──────────────────────────────────────────────
        if show_all_trades and report.trades:
            # Use a wider console for the trade table to prevent column truncation
            trade_console = Console(width=140)
            trade_table = Table(
                title="All Trades",
                show_lines=False,
                padding=(0, 1),
                title_style="bold",
                expand=False,
            )
            trade_table.add_column("Ticker", no_wrap=True, width=6)
            trade_table.add_column("Entry", no_wrap=True, width=10)
            trade_table.add_column("Exit", no_wrap=True, width=10)
            trade_table.add_column("Shares", justify="right", no_wrap=True, width=6)
            trade_table.add_column("Entry $", justify="right", no_wrap=True, width=9)
            trade_table.add_column("Exit $", justify="right", no_wrap=True, width=9)
            trade_table.add_column("P&L", justify="right", no_wrap=True, width=10)
            trade_table.add_column("R", justify="right", no_wrap=True, width=6)
            trade_table.add_column("Reason", no_wrap=True, width=12)

            for t in sorted(report.trades, key=lambda x: x.entry_date):
                r_mult = t.pnl / (t.entry_price * 0.07 * t.shares) if t.shares > 0 else 0
                pnl_str = f"[green]+${t.pnl:,.0f}[/]" if t.pnl > 0 else f"[red]-${abs(t.pnl):,.0f}[/]"
                r_str = f"{r_mult:.1f}R"
                reason = t.exit_reason.replace("_", " ").title()

                trade_table.add_row(
                    t.ticker,
                    str(t.entry_date),
                    str(t.exit_date),
                    str(t.shares),
                    f"${t.entry_price:.2f}",
                    f"${t.exit_price:.2f}",
                    pnl_str,
                    r_str,
                    reason,
                )

            trade_console.print(trade_table)
            console.print()

        # ── Equity sparkline ─────────────────────────────────────
        if report.equity_curve:
            spark = _sparkline(report.equity_curve)
            peak = max(v for _, v in report.equity_curve)
            trough = min(v for _, v in report.equity_curve)
            console.print(f"  [dim]{spark}[/]  [dim]peak ${peak:,.0f}  trough ${trough:,.0f}[/]")
            console.print()

        # ── Data quality ─────────────────────────────────────────
        if report.tickers_dropped > 0:
            console.print(f"  [yellow]{report.tickers_dropped} tickers dropped[/] (insufficient data)")

        # ── Benchmark note ──────────────────────────────────────
        if report.benchmark_return == 0.0 and len(report.trades) > 0:
            console.print("  [dim]SPY benchmark: no data returned[/]")

        console.print()
        console.print(f"  [dim]{SURVIVORSHIP_DISCLAIMER}[/]")
        console.rule(style="dim")
        console.print()

    @staticmethod
    def to_csv(result: BacktestResult, filepath: str) -> None:
        """Export trade records to CSV."""
        rows = []
        for t in result.trades:
            rows.append({
                'ticker': t.ticker,
                'side': t.side,
                'entry_date': t.entry_date,
                'exit_price': t.exit_price,
                'entry_price': t.entry_price,
                'exit_date': t.exit_date,
                'shares': t.shares,
                'pnl': t.pnl,
                'exit_reason': t.exit_reason,
            })

        df = pd.DataFrame(rows)
        df.to_csv(filepath, index=False)

        # Also export equity curve
        eq_path = filepath.replace('.csv', '_equity.csv')
        eq_rows = [{'date': d, 'equity': v} for d, v in result.equity_curve]
        pd.DataFrame(eq_rows).to_csv(eq_path, index=False)

    @staticmethod
    def sensitivity_analysis(result: BacktestResult,
                             slippage_range: list[float]) -> pd.DataFrame:
        """Run backtest with varying slippage assumptions.

        This is a placeholder for v1 — full implementation requires
        re-running the engine with different ExecutionConfig values.
        The method signature is here for future use.

        Args:
            result: Original backtest result
            slippage_range: List of slippage values in bps to test

        Returns:
            DataFrame showing degradation with increased slippage
        """
        # v2: Re-run engine with different slippage values
        # v1: Report current costs as baseline
        rows = []
        for slippage_bps in slippage_range:
            # Estimate impact: each fill has slippage_bps impact
            # Approximate: total_slippage ~ n_trades * 2 * avg_price * shares * slippage_bps/10000
            rows.append({
                'slippage_bps': slippage_bps,
                'estimated_annualized_return': result.state.equity_curve[-1][1] if result.equity_curve else 0,
                'note': 'Full sensitivity analysis requires engine re-run (v2)',
            })

        return pd.DataFrame(rows)


# ── Formatting helpers ────────────────────────────────────────────


def _fmt_pct(value: float, invert: bool = False) -> str:
    """Format a percentage with green/red coloring.

    invert=True means higher values are worse (e.g., drawdown).
    """
    pct = value * 100
    if invert:
        color = "red" if pct > 0 else "green"
        arrow = "▼" if pct > 0 else "▲"
    else:
        color = "green" if pct > 0 else ("red" if pct < 0 else "white")
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else " ")
    return f"[{color}]{pct:>7.2f}% {arrow}[/{color}]"


def _fmt_dollars(value: float) -> str:
    """Format a dollar amount with green/red coloring."""
    if value > 0:
        return f"[green]+${value:,.0f}[/]"
    elif value < 0:
        return f"[red]-${abs(value):,.0f}[/]"
    return "$0"


def _sharpe_gauge(value: float) -> str:
    """Return a 5-dot gauge for Sharpe ratio (0-3 range)."""
    # Map: <0 = 0 dots, 0-0.5 = 1, 0.5-1.0 = 2, 1.0-2.0 = 3, 2.0-3.0 = 4, >3 = 5
    if value < 0:
        filled = 0
    elif value < 0.5:
        filled = 1
    elif value < 1.0:
        filled = 2
    elif value < 2.0:
        filled = 3
    elif value < 3.0:
        filled = 4
    else:
        filled = 5

    dots = "●" * filled + "○" * (5 - filled)
    # Color: red (0-1), yellow (2), green (3+)
    if filled <= 1:
        style = "red"
    elif filled == 2:
        style = "yellow"
    else:
        style = "green"
    return f"[{style}]{dots}[/{style}]"


def _win_rate_bar(rate: float) -> str:
    """Return a 10-char bar for win rate."""
    filled = int(round(rate * 10))
    filled = max(0, min(10, filled))
    bar = "▉" * filled + "░" * (10 - filled)
    if rate >= 0.6:
        style = "green"
    elif rate >= 0.4:
        style = "yellow"
    else:
        style = "red"
    return f"[{style}]{bar}[/{style}]"


def _exit_breakdown(trades: list[TradeRecord]) -> list[tuple[str, int, float]]:
    """Group trades by exit reason with count and total P&L."""
    if not trades:
        return []

    groups: dict[str, list[TradeRecord]] = {}
    for t in trades:
        # Normalize: TARGET_HIT_2.1R -> Target Hit
        reason = t.exit_reason
        if reason.startswith("TARGET_HIT"):
            label = "Target Hit"
        elif reason == "STOP_HIT":
            label = "Stop Hit"
        elif reason == "LIQUIDATION":
            label = "Liquidation"
        else:
            label = reason.replace("_", " ").title()

        groups.setdefault(label, []).append(t)

    rows = []
    for label in ["Target Hit", "Stop Hit", "Liquidation"]:
        if label in groups:
            group = groups[label]
            count = len(group)
            pnl = sum(t.pnl for t in group)
            rows.append((label, count, pnl))

    # Any remaining reasons
    for label, group in sorted(groups.items()):
        if label not in ("Target Hit", "Stop Hit", "Liquidation"):
            rows.append((label, len(group), sum(t.pnl for t in group)))

    return rows


def _top_trades(trades: list[TradeRecord], n: int = 5) -> tuple[list[str], list[str]]:
    """Return formatted top winners and losers."""
    if not trades:
        return [], []

    sorted_trades = sorted(trades, key=lambda t: t.pnl, reverse=True)

    winners = []
    for t in sorted_trades[:n]:
        if t.pnl <= 0:
            break
        r_mult = t.pnl / (t.entry_price * 0.07 * t.shares) if t.shares > 0 else 0
        winners.append(f"{t.ticker:<6} +${t.pnl:>6,.0f}  {r_mult:.1f}R")

    losers = []
    for t in sorted_trades[-n:]:
        if t.pnl >= 0:
            continue
        r_mult = t.pnl / (t.entry_price * 0.07 * t.shares) if t.shares > 0 else 0
        losers.append(f"{t.ticker:<6} -${abs(t.pnl):>6,.0f}  {r_mult:.1f}R")

    losers.reverse()  # Worst first
    return winners, losers


def _sparkline(equity_curve: list[tuple[date, float]], width: int = 60) -> str:
    """Convert equity curve to a unicode sparkline string."""
    if not equity_curve:
        return ""

    values = [v for _, v in equity_curve]

    # Downsample to ~width points
    if len(values) > width:
        step = len(values) / width
        indices = [int(i * step) for i in range(width)]
        sampled = [values[i] for i in indices]
    else:
        sampled = values

    # Map to sparkline chars
    min_val = min(sampled)
    max_val = max(sampled)
    val_range = max_val - min_val

    if val_range == 0:
        return SPARKLINE_CHARS[4] * len(sampled)  # Mid-height if flat

    chars = []
    n_levels = len(SPARKLINE_CHARS)
    for v in sampled:
        normalized = (v - min_val) / val_range
        idx = int(normalized * (n_levels - 1))
        idx = max(0, min(n_levels - 1, idx))
        chars.append(SPARKLINE_CHARS[idx])

    return "".join(chars)