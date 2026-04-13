"""Tests for backtest execution model."""

import unittest

from traderlib.backtest.execution import ExecutionConfig, ExecutionModel, FillResult


class TestExecutionConfig(unittest.TestCase):
    """Tests for ExecutionConfig defaults."""

    def test_defaults(self):
        config = ExecutionConfig()
        self.assertEqual(config.commission_per_share, 0.005)
        self.assertEqual(config.commission_min, 1.0)
        self.assertEqual(config.slippage_bps, 5.0)

    def test_custom_config(self):
        config = ExecutionConfig(
            commission_per_share=0.01,
            commission_min=2.0,
            slippage_bps=10.0,
        )
        self.assertEqual(config.commission_per_share, 0.01)
        self.assertEqual(config.commission_min, 2.0)
        self.assertEqual(config.slippage_bps, 10.0)


class TestFillResult(unittest.TestCase):
    """Tests for FillResult dataclass."""

    def test_fill_result_fields(self):
        fill = FillResult(
            ticker='AAPL',
            side='BUY',
            shares=100,
            intended_price=150.0,
            fill_price=150.075,
            commission=0.5,
            total_cost=15007.5,
        )
        self.assertEqual(fill.ticker, 'AAPL')
        self.assertEqual(fill.side, 'BUY')
        self.assertEqual(fill.shares, 100)


class TestExecutionModel(unittest.TestCase):
    """Tests for deterministic, conservative fill simulation."""

    def setUp(self):
        self.config = ExecutionConfig(
            commission_per_share=0.005,
            commission_min=1.0,
            slippage_bps=5.0,
        )
        self.model = ExecutionModel(self.config)

    def test_buy_fill_adds_slippage(self):
        """BUY fills at reference * (1 + slippage) — you pay more."""
        fill = self.model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        expected_fill = 150.0 * (1 + 5 / 10000)  # 150.075
        self.assertAlmostEqual(fill.fill_price, expected_fill, places=4)
        self.assertEqual(fill.side, 'BUY')

    def test_sell_fill_subtracts_slippage(self):
        """SELL fills at reference * (1 - slippage) — you receive less."""
        fill = self.model.simulate_fill('AAPL', 'SELL', 100, 150.0)
        expected_fill = 150.0 * (1 - 5 / 10000)  # 149.925
        self.assertAlmostEqual(fill.fill_price, expected_fill, places=4)

    def test_commission_per_share(self):
        """Commission = max(min, per_share * shares)."""
        fill = self.model.simulate_fill('AAPL', 'BUY', 1000, 100.0)
        # 0.005 * 1000 = $5, which is > $1 min
        self.assertEqual(fill.commission, 5.0)

    def test_commission_minimum(self):
        """Minimum commission of $1 for small orders."""
        fill = self.model.simulate_fill('AAPL', 'BUY', 10, 100.0)
        # 0.005 * 10 = $0.05, but min is $1.0
        self.assertEqual(fill.commission, 1.0)

    def test_total_cost_buy_includes_commission(self):
        """BUY total_cost = fill_price * shares + commission."""
        fill = self.model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        expected_total = fill.fill_price * 100 + fill.commission
        self.assertAlmostEqual(fill.total_cost, expected_total, places=2)

    def test_total_cost_sell_subtracts_commission(self):
        """SELL total_cost = fill_price * shares - commission."""
        fill = self.model.simulate_fill('AAPL', 'SELL', 100, 150.0)
        expected_total = fill.fill_price * 100 - fill.commission
        self.assertAlmostEqual(fill.total_cost, expected_total, places=2)

    def test_deterministic(self):
        """Same inputs always produce same outputs."""
        fill1 = self.model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        fill2 = self.model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        self.assertEqual(fill1.fill_price, fill2.fill_price)
        self.assertEqual(fill1.commission, fill2.commission)

    def test_zero_slippage(self):
        """With zero slippage, fill price equals reference price."""
        config = ExecutionConfig(slippage_bps=0.0)
        model = ExecutionModel(config)
        fill = model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        self.assertAlmostEqual(fill.fill_price, 150.0, places=4)

    def test_high_slippage(self):
        """With 20bps slippage, costs are significant."""
        config = ExecutionConfig(slippage_bps=20.0)
        model = ExecutionModel(config)
        fill = model.simulate_fill('AAPL', 'BUY', 100, 150.0)
        expected = 150.0 * (1 + 20 / 10000)  # 150.30
        self.assertAlmostEqual(fill.fill_price, expected, places=4)

    def test_boundary_commission(self):
        """At 200 shares, per-share commission equals minimum."""
        # 200 * $0.005 = $1.00, which equals $1.00 minimum
        fill = self.model.simulate_fill('AAPL', 'BUY', 200, 100.0)
        self.assertEqual(fill.commission, 1.0)

    def test_small_order_uses_minimum(self):
        """Orders under 200 shares use minimum commission."""
        fill = self.model.simulate_fill('AAPL', 'BUY', 50, 100.0)
        # 50 * $0.005 = $0.25 < $1.00 minimum
        self.assertEqual(fill.commission, 1.0)


if __name__ == '__main__':
    unittest.main()