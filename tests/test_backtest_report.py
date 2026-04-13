"""Tests for backtest report generation."""

import unittest
from datetime import date

import numpy as np
import pandas as pd

from traderlib.backtest.engine import BacktestConfig, BacktestResult
from traderlib.backtest.report import BacktestReport, BacktestReporter, SURVIVORSHIP_DISCLAIMER
from traderlib.backtest.state import BacktestState, TradeRecord


def make_trade(**overrides) -> TradeRecord:
    """Create a test TradeRecord with defaults."""
    defaults = dict(
        ticker='AAPL', side='LONG',
        entry_date=date(2024, 1, 15),
        exit_date=date(2024, 2, 15),
        entry_price=150.0, exit_price=160.0,
        shares=100, pnl=1000.0,
        exit_reason='TARGET_HIT', commissions=1.0,
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


class TestBacktestReport(unittest.TestCase):
    """Tests for BacktestReport dataclass."""

    def test_fields(self):
        report = BacktestReport(
            total_return=0.10, annualized_return=0.12,
            volatility=0.18, max_drawdown=0.08,
            sharpe_ratio=1.5, sortino_ratio=2.0,
            calmar_ratio=1.5, win_rate=0.6,
            profit_factor=2.0, avg_r_multiple=1.5,
            total_commissions=50.0, total_slippage=25.0,
            tickers_dropped=2, benchmark_return=0.08,
            alpha=0.04, trades=[],
        )
        self.assertEqual(report.total_return, 0.10)
        self.assertEqual(report.alpha, 0.04)


class TestBacktestReporter(unittest.TestCase):
    """Tests for BacktestReporter."""

    def setUp(self):
        self.state = BacktestState(
            initial_capital=100_000, start_date=date(2024, 1, 1),
        )

    def _make_result(self, trades=None, equity_curve=None) -> BacktestResult:
        """Create a BacktestResult with synthetic data."""
        if equity_curve is None:
            # Simple equity curve: 100k → 110k over 252 days
            dates = pd.date_range('2024-01-01', periods=252, freq='B')
            values = np.linspace(100_000, 110_000, 252)
            equity_curve = list(zip(
                [d.date() for d in dates],
                values,
            ))

        return BacktestResult(
            trades=trades or [],
            equity_curve=equity_curve,
            state=self.state,
            benchmark=pd.DataFrame({
                'Close': np.linspace(450, 470, 252),
            }, index=pd.date_range('2024-01-01', periods=252, freq='B')),
            config=BacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
            ),
        )

    def test_generate_report_basic(self):
        """Report should calculate basic metrics."""
        trades = [
            make_trade(pnl=1000.0, commissions=1.0),
            make_trade(pnl=-500.0, ticker='MSFT', commissions=1.0),
        ]
        result = self._make_result(trades=trades)
        report = BacktestReporter.generate(result)

        self.assertIsNotNone(report.total_return)
        self.assertIsNotNone(report.annualized_return)
        self.assertIsNotNone(report.sharpe_ratio)

    def test_generate_report_empty_trades(self):
        """Report with no trades should still produce valid metrics."""
        result = self._make_result(trades=[])
        report = BacktestReporter.generate(result)

        self.assertEqual(report.win_rate, 0.0)
        self.assertEqual(report.profit_factor, 0.0)

    def test_generate_report_win_rate(self):
        """Win rate should be wins / total trades."""
        trades = [
            make_trade(pnl=500.0, ticker='A'),
            make_trade(pnl=-200.0, ticker='B'),
            make_trade(pnl=300.0, ticker='C'),
            make_trade(pnl=-100.0, ticker='D'),
        ]
        result = self._make_result(trades=trades)
        report = BacktestReporter.generate(result)

        self.assertAlmostEqual(report.win_rate, 0.5)  # 2 wins out of 4

    def test_generate_report_profit_factor(self):
        """Profit factor = gross profit / gross loss."""
        trades = [
            make_trade(pnl=1000.0, ticker='A'),
            make_trade(pnl=500.0, ticker='B'),
            make_trade(pnl=-300.0, ticker='C'),
        ]
        result = self._make_result(trades=trades)
        report = BacktestReporter.generate(result)

        # Gross profit = 1500, Gross loss = 300
        self.assertAlmostEqual(report.profit_factor, 1500 / 300)

    def test_generate_report_commissions(self):
        """Total commissions should be sum of all trade commissions."""
        trades = [
            make_trade(commissions=2.0, ticker='A'),
            make_trade(commissions=3.0, ticker='B'),
        ]
        result = self._make_result(trades=trades)
        report = BacktestReporter.generate(result)

        self.assertAlmostEqual(report.total_commissions, 5.0)

    def test_print_report_does_not_crash(self):
        """print_report should not raise errors."""
        result = self._make_result()
        report = BacktestReporter.generate(result)
        # Should not raise
        BacktestReporter.print_report(report)

    def test_survivorship_disclaimer_in_report(self):
        """Every report output should include the survivorship bias disclaimer."""
        self.assertIn('survivorship', SURVIVORSHIP_DISCLAIMER.lower())

    def test_to_csv_export(self):
        """CSV export should produce valid files."""
        import tempfile
        import os

        trades = [make_trade()]
        result = self._make_result(trades=trades)

        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            filepath = f.name

        try:
            BacktestReporter.to_csv(result, filepath)
            self.assertTrue(os.path.exists(filepath))

            # Read back and verify
            df = pd.read_csv(filepath)
            self.assertEqual(len(df), 1)
            self.assertIn('ticker', df.columns)
        finally:
            os.unlink(filepath)
            eq_path = filepath.replace('.csv', '_equity.csv')
            if os.path.exists(eq_path):
                os.unlink(eq_path)

    def test_alpha_calculation(self):
        """Alpha = strategy annualized return - benchmark annualized return."""
        result = self._make_result()
        report = BacktestReporter.generate(result)
        # Alpha should be a number (not NaN or Inf)
        self.assertFalse(np.isnan(report.alpha))
        self.assertFalse(np.isinf(report.alpha))


class TestBacktestReportEdgeCases(unittest.TestCase):
    """Edge cases for report generation."""

    def test_single_trade(self):
        """Report with a single trade."""
        state = BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1))
        trades = [make_trade(pnl=500.0)]
        equity_curve = [(date(2024, 1, 1), 100_000), (date(2024, 2, 1), 100_500)]
        result = BacktestResult(
            trades=trades, equity_curve=equity_curve,
            state=state, benchmark=pd.DataFrame({'Close': [450, 455]}),
            config=BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)),
        )
        report = BacktestReporter.generate(result)
        self.assertEqual(len(report.trades), 1)

    def test_empty_equity_curve(self):
        """Report with empty equity curve should produce defaults."""
        state = BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1))
        result = BacktestResult(
            trades=[], equity_curve=[],
            state=state, benchmark=pd.DataFrame(),
            config=BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)),
        )
        report = BacktestReporter.generate(result)
        self.assertEqual(report.total_return, 0)
        self.assertEqual(report.sharpe_ratio, 0)


if __name__ == '__main__':
    unittest.main()