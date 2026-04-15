"""Backtest reporting — statistics, benchmarks, and risk metrics.

Every report includes:
- Return metrics (total, annualized, daily volatility)
- Risk metrics (max drawdown, Sharpe, Sortino, Calmar)
- Trade metrics (win rate, profit factor, avg R-multiple)
- Buy-and-hold SPY benchmark + alpha
- Cost attribution (slippage + commissions)
- Survivorship bias disclaimer
"""

from dataclasses import dataclass
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
    total_commissions: float
    total_slippage: float
    tickers_dropped: int
    benchmark_return: float
    alpha: float
    trades: list[TradeRecord]


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
                avg_r_multiple=0, total_commissions=0, total_slippage=0,
                tickers_dropped=0, benchmark_return=0, alpha=0,
                trades=trades,
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

        # Cost attribution
        total_commissions = sum(t.commissions for t in trades)
        total_slippage = sum(
            abs(t.entry_price - t.entry_price) * t.shares  # Approximation
            for t in trades
        )
        # Better slippage calculation: entry + exit fills
        # Slippage per fill = (fill_price - reference_price) * shares for buys
        #                    = (reference_price - fill_price) * shares for sells
        # This requires FillResult data which we don't store in TradeRecord
        # Using commission as the primary cost metric for v1
        total_slippage = 0.0  # Not tracked separately in v1

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
            total_commissions=total_commissions,
            total_slippage=total_slippage,
            tickers_dropped=tickers_dropped,
            benchmark_return=benchmark_return,
            alpha=alpha,
            trades=trades,
        )

    @staticmethod
    def print_report(report: BacktestReport) -> None:
        """Print a formatted backtest report to stdout."""
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

        print(f"\n--- Costs ---")
        print(f"Total Commissions:  ${report.total_commissions:>10,.2f}")
        print(f"Total Slippage:     ${report.total_slippage:>10,.2f}")

        print(f"\n--- Benchmark ---")
        print(f"SPY Return:         {report.benchmark_return * 100:>8.2f}%")
        print(f"Alpha:              {report.alpha * 100:>8.2f}%")

        if report.tickers_dropped > 0:
            print(f"\n--- Data Quality ---")
            print(f"Tickers Dropped:    {report.tickers_dropped:>8d}")

        print(f"\n{SURVIVORSHIP_DISCLAIMER}")
        print("=" * 60 + "\n")

    @staticmethod
    def to_csv(result: BacktestResult, filepath: str) -> None:
        """Export trade records to CSV."""
        rows = []
        for t in result.trades:
            rows.append({
                'ticker': t.ticker,
                'side': t.side,
                'entry_date': t.entry_date,
                'exit_date': t.exit_date,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'shares': t.shares,
                'pnl': t.pnl,
                'exit_reason': t.exit_reason,
                'commissions': t.commissions,
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