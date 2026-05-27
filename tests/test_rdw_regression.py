#!/usr/bin/env python3
"""Regression tests for RDW stop investigation fixes.

Covers bugs identified in docs/2026-05-26-rdw-stop-investigation.md:
1. VCP strategy R-calculation uses current stop instead of initial stop
2. Dashboard shows stale data when market is closed
3. Strategy plugins override legacy ExitEngine for all positions
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import numpy as np
import pandas as pd

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.paper_state import Position
from traderlib.strategies import StrategyContext, ExitAction, ExitActionType
from traderlib.strategies.vcp_breakout import VCPBreakoutLargeCap
from traderlib.risk_config import RiskConfig, RiskConfigManager


class MockDataProvider:
    """Mock data provider for testing."""

    def __init__(self, data: dict):
        self.data = data

    def get_bars(self, ticker: str, as_of: date, min_rows: int = 30):
        return self.data.get(ticker)

    def get_current_price(self, ticker: str, as_of: date):
        df = self.data.get(ticker)
        if df is not None and len(df) > 0:
            return float(df['Close'].iloc[-1])
        return None


def make_uptrend_df(n_days: int = 60, price: float = 150.0) -> pd.DataFrame:
    """Generate simple uptrend data."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')
    prices = np.linspace(price * 0.8, price, n_days) + np.random.randn(n_days) * 0.5
    highs = prices * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = prices * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1000000, 5000000, n_days)
    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': prices,
        'Volume': volumes,
    }, index=dates)


class TestVCPRCalculationBug(unittest.TestCase):
    """Test for VCP strategy R-calculation bug (FINDING-013).

    When a position's stop ratchets to breakeven, the VCP strategy
    must still calculate R-multiples using the ORIGINAL stop price,
    not the current (ratcheted) stop price.
    """

    def setUp(self):
        self.risk_config = RiskConfig()
        self.strategy = VCPBreakoutLargeCap(risk_config=self.risk_config)
        self.df = make_uptrend_df(60, price=150.0)
        self.data_provider = MockDataProvider({'AAPL': self.df})

    def make_position(self, entry_price: float = 150.0,
                      stop_price: float = 150.0,  # breakeven
                      initial_stop_price: float = 140.0) -> Position:
        """Create a breakeven position for testing.

        stop_price == entry_price (breakeven, ratcheted up)
        initial_stop_price = original stop at entry
        """
        return Position(
            ticker='AAPL',
            status='OPEN',
            entry_date='2024-01-15',
            entry_price=entry_price,
            shares=100,
            stop_price=stop_price,
            target_price=entry_price * 1.10,
            initial_risk=(entry_price - initial_stop_price) * 100,
            sector='Technology',
            current_stop_type='BREAKEVEN',
            initial_stop_price=initial_stop_price,
        )

    def test_r_multiple_uses_initial_stop_not_current_stop(self):
        """BUG: VCP strategy used stop_price instead of initial_stop_price.

        With entry=100, initial_stop=90, current_stop=100 (breakeven),
        and current price at ~150 (from mock data):
        - Correct R = (150 - 100) / (100 - 90) = 50 / 10 = 5.0R
        - Buggy R = (150 - 100) / (100 - 100) = division by zero -> 0R

        With the fix, r_multiple should be ~5.0R, not 0R.
        """
        position = self.make_position(
            entry_price=100.0,
            stop_price=100.0,  # breakeven
            initial_stop_price=90.0,
        )

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 3, 1),
            positions={'AAPL': position},
            cash=50000,
            equity=100000,
        )

        actions = self.strategy.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        # At 5.0R the position should be in Phase 2 (trailing), not Phase 1
        self.assertNotEqual(
            aapl_action.reason, 'PHASE1_WAITING',
            msg=(
                "VCP strategy returned PHASE1_WAITING with R=0 "
                "— this indicates the bug where initial_stop_price "
                "was not used for R-calculation. "
                "Expected: r_multiple ~5.0R using initial_stop_price."
            )
        )

    def test_r_multiple_with_high_r_breakeven_position(self):
        """High R position at breakeven should enter Phase 2 trailing.

        Entry=100, initial_stop=90, current_stop=100 (breakeven).
        Current price=130 (from mock data ~130 range).
        Correct R = (130 - 100) / (100 - 90) = 30 / 10 = 3.0R.

        At 3.0R, the position should trigger Phase 2 trailing (EMA20).
        """
        # Create data with price around 130
        df = make_uptrend_df(60, price=130.0)
        data_provider = MockDataProvider({'AAPL': df})

        position = self.make_position(
            entry_price=100.0,
            stop_price=100.0,  # breakeven
            initial_stop_price=90.0,
        )

        context = StrategyContext(
            data_provider=data_provider,
            sim_date=date(2024, 3, 1),
            positions={'AAPL': position},
            cash=50000,
            equity=100000,
        )

        actions = self.strategy.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        # At 3.0R we should be in Phase 2 (trailing), not Phase 1
        self.assertNotEqual(
            aapl_action.reason, 'PHASE1_WAITING',
            msg=(
                "Position at 3.0R with breakeven stop was stuck in Phase 1. "
                "The R-calculation bug prevents Phase 2 trailing from ever "
                "triggering for breakeven positions."
            )
        )


class TestStrategyConfigToggle(unittest.TestCase):
    """Test for strategy.manage_exits config toggle.

    When strategy.manage_exits is false, the legacy ExitEngine
    should handle all positions regardless of loaded strategy.
    """

    def test_strategy_config_parses_manage_exits(self):
        """RiskConfig should parse strategy.manage_exits from YAML."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'risk_config.yaml'
            config_path.write_text("""
account:
  risk_per_trade_pct: 0.005
strategy:
  manage_exits: false
""")
            manager = RiskConfigManager(config_path=config_path, quiet=True)
            config = manager.get_config()

            self.assertFalse(
                config.strategy.manage_exits,
                msg="strategy.manage_exits should be False when set in YAML"
            )

    def test_strategy_config_defaults_to_true(self):
        """RiskConfig should default strategy.manage_exits to True."""
        config = RiskConfig()
        self.assertTrue(
            config.strategy.manage_exits,
            msg="strategy.manage_exits should default to True"
        )


class TestDashboardFrozenIndicator(unittest.TestCase):
    """Test for dashboard stale data indicator.

    When market is closed, the dashboard should show
    'Data frozen since HH:MM:SS' in the header.
    """

    def test_header_shows_frozen_when_market_closed(self):
        """Dashboard header should indicate frozen data when market != OPEN."""
        try:
            from traderlib.dashboard import Dashboard
        except ImportError:
            self.skipTest("rich not installed")

        with patch('traderlib.dashboard.Live'):
            d = Dashboard(enabled=True)
            d._last_update_time = pd.Timestamp('2024-01-15 16:00:00')

            state = {
                'market_status': 'CLOSED',
                'mode': 'PAPER',
                'regime': 'NEUTRAL',
                'vix': 16.4,
                'ws_connected': True,
                'api_requests': 12,
                'api_max': 500,
            }

            header = d._header(state)
            header_text = str(header)

            self.assertIn(
                'Data frozen since',
                header_text,
                msg="Dashboard should show 'Data frozen since' when market is CLOSED"
            )
            self.assertIn(
                '16:00:00',
                header_text,
                msg="Dashboard should show the frozen timestamp"
            )
            d.stop()

    def test_header_no_frozen_when_market_open(self):
        """Dashboard header should NOT show frozen indicator when market is OPEN."""
        try:
            from traderlib.dashboard import Dashboard
        except ImportError:
            self.skipTest("rich not installed")

        with patch('traderlib.dashboard.Live'):
            d = Dashboard(enabled=True)
            d._last_update_time = pd.Timestamp('2024-01-15 10:30:00')

            state = {
                'market_status': 'OPEN',
                'mode': 'PAPER',
                'regime': 'NEUTRAL',
                'vix': 16.4,
                'ws_connected': True,
                'api_requests': 12,
                'api_max': 500,
            }

            header = d._header(state)
            header_text = str(header)

            self.assertNotIn(
                'Data frozen since',
                header_text,
                msg="Dashboard should NOT show frozen indicator when market is OPEN"
            )
            d.stop()


if __name__ == '__main__':
    unittest.main()
