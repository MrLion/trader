#!/usr/bin/env python3
"""Exit engine tests: trailing stops, breakeven, EMA trailing, profit targets.

Standard test position:
    entry=150, stop=140, risk/share=10, shares=100, initial_risk=1000
    target=170 (2R)

    R levels:
        +0.5R → 155.0
        +1R   → 160.0
        +1.5R → 165.0
        +2R   → 170.0  (= target)
        +3R   → 180.0
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.paper_exits import ExitEngine
from traderlib.paper_state import Position
from traderlib.risk_config import RiskConfig, ProfitTargetConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(**overrides) -> Position:
    """Create a standard test position. Keyword args override defaults."""
    defaults = dict(
        ticker='TEST',
        status='OPEN',
        entry_date='2026-01-01',
        entry_price=150.0,
        shares=100,
        stop_price=140.0,
        target_price=170.0,
        initial_risk=1000.0,   # (150-140) * 100
        sector='Technology',
        current_stop_type='HARD',
    )
    defaults.update(overrides)
    return Position(**defaults)


def make_engine(ema10=None, ema21=None, risk_config=None) -> ExitEngine:
    """Create an ExitEngine with _get_ema_values mocked."""
    engine = ExitEngine(risk_config=risk_config)
    engine._get_ema_values = Mock(return_value=(ema10, ema21))
    return engine


def create_mock_ohlcv(days=60, base_price=100.0, volatility=0.02) -> pd.DataFrame:
    """Create mock OHLCV data for testing.

    Args:
        days: Number of days of data
        base_price: Starting price
        volatility: Price volatility

    Returns:
        DataFrame with Open, High, Low, Close, Volume columns
    """
    import numpy as np
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    np.random.seed(42)
    closes = base_price + np.random.randn(days).cumsum() * volatility * base_price
    highs = closes * (1 + abs(np.random.randn(days) * 0.01))
    lows = closes * (1 - abs(np.random.randn(days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(days)
    volumes = np.random.randint(100000, 1000000, days)

    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes
    }, index=dates)


# ---------------------------------------------------------------------------
# Group 1 — _calculate_r_multiple
# ---------------------------------------------------------------------------

class TestRMultipleCalculation(unittest.TestCase):

    def setUp(self):
        self.engine = ExitEngine()

    def test_at_entry_price_is_zero(self):
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(150.0, 150.0, 140.0, 100), 0.0
        )

    def test_at_plus_one_r(self):
        # price = entry + 1 * risk/share = 160
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(160.0, 150.0, 140.0, 100), 1.0
        )

    def test_at_minus_one_r(self):
        # price = stop = 140
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(140.0, 150.0, 140.0, 100), -1.0
        )

    def test_zero_initial_risk_returns_zero(self):
        # stop == entry → no risk → guard against division by zero
        result = self.engine._calculate_r_multiple(160.0, 150.0, 150.0, 100)
        self.assertEqual(result, 0.0)


# ---------------------------------------------------------------------------
# Group 2 — Hard stop boundaries
# ---------------------------------------------------------------------------

class TestHardStop(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine()
        self.pos = make_position()

    def test_price_below_stop_triggers_exit(self):
        signal = self.engine.evaluate_exit(self.pos, 139.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, 'STOP_HIT')

    def test_price_exactly_at_stop_triggers_exit(self):
        signal = self.engine.evaluate_exit(self.pos, 140.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, 'STOP_HIT')

    def test_price_one_cent_above_stop_is_hold(self):
        signal = self.engine.evaluate_exit(self.pos, 140.01)
        self.assertFalse(signal.should_exit)


# ---------------------------------------------------------------------------
# Group 3 — Breakeven ratchet (+1R)
# ---------------------------------------------------------------------------

class TestBreakevenRatchet(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine(ema10=None, ema21=None)

    def test_at_plus_1r_stop_moves_to_entry(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 161.0)  # just above +1R
        self.assertEqual(pos.stop_price, 150.0)

    def test_at_plus_1r_stop_type_becomes_breakeven(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

    def test_below_plus_1r_stop_does_not_move(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 159.0)  # 0.9R — below threshold
        self.assertEqual(pos.stop_price, 140.0)
        self.assertEqual(pos.current_stop_type, 'HARD')

    def test_already_at_breakeven_stop_does_not_go_down(self):
        # Stop already at entry — should not be moved downward
        pos = make_position(stop_price=150.0, current_stop_type='BREAKEVEN')
        self.engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.stop_price, 150.0)


# ---------------------------------------------------------------------------
# Group 4 — EMA10 trailing (+1.5R)
# ---------------------------------------------------------------------------

class TestEMA10Trailing(unittest.TestCase):

    def test_ema10_above_stop_moves_stop(self):
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)  # +1.5R
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_ema10_below_stop_does_not_move_stop(self):
        # EMA10 below current stop — ratchet must not go down
        engine = make_engine(ema10=135.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)
        self.assertEqual(pos.stop_price, 140.0)

    def test_ema10_none_falls_back_to_breakeven(self):
        # No EMA data at +1.5R — should still apply breakeven logic
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)
        # Breakeven fires as fallback (entry_price > current_stop)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')


# ---------------------------------------------------------------------------
# Group 5 — EMA21 trailing (+3R)
# ---------------------------------------------------------------------------

class TestEMA21Trailing(unittest.TestCase):

    def test_ema21_above_stop_moves_stop(self):
        engine = make_engine(ema10=155.0, ema21=165.0)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)  # +3R
        self.assertEqual(pos.stop_price, 165.0)
        self.assertEqual(pos.current_stop_type, 'EMA21')

    def test_ema21_below_stop_does_not_move_stop(self):
        engine = make_engine(ema10=155.0, ema21=135.0)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 140.0)

    def test_ema21_none_falls_back_to_ema10(self):
        # Gap 2 decision: at +3R with ema21=None, fall back to EMA10 trailing
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_ema21_and_ema10_none_falls_back_to_breakeven(self):
        # No EMA data at +3R — breakeven is the last resort
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')


# ---------------------------------------------------------------------------
# Group 6 — Profit target exit
# ---------------------------------------------------------------------------

class TestProfitTargetExit(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine()

    def test_price_at_target_triggers_exit(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 170.0)  # exactly at 2R target
        self.assertTrue(signal.should_exit)
        self.assertIn('TARGET_HIT', signal.reason)

    def test_price_above_target_triggers_exit(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 175.0)
        self.assertTrue(signal.should_exit)
        self.assertIn('TARGET_HIT', signal.reason)

    def test_r_multiple_2_without_reaching_target_triggers_exit(self):
        # target is 175 (above 2R=170) — 2R fires first
        pos = make_position(target_price=175.0)
        signal = self.engine.evaluate_exit(pos, 170.0)  # 2R exactly
        self.assertTrue(signal.should_exit)
        self.assertIn('2.0R', signal.reason)

    def test_below_target_and_below_2r_is_hold(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 169.0)  # 1.9R, below target
        self.assertFalse(signal.should_exit)
        self.assertEqual(signal.reason, 'HOLD')


# ---------------------------------------------------------------------------
# Group 7 — Stop never goes down (ratchet invariant)
# ---------------------------------------------------------------------------

class TestStopNeverGoesDown(unittest.TestCase):

    def test_stop_does_not_retreat_when_price_falls_back(self):
        # Advance to +1.5R (EMA10 trailing), then price retreats to +1R
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()

        engine.evaluate_exit(pos, 165.0)  # stop moves to EMA10=155
        self.assertEqual(pos.stop_price, 155.0)

        engine._get_ema_values = Mock(return_value=(148.0, None))  # EMA drops
        engine.evaluate_exit(pos, 161.0)  # price retreats

        # Stop must not fall back below 155
        self.assertGreaterEqual(pos.stop_price, 155.0)

    def test_sequential_advances_only_ratchet_upward(self):
        # Three price advances — stop should only go up
        engine = make_engine(ema10=153.0, ema21=None)
        pos = make_position()
        stops = []

        for price in [161.0, 163.0, 165.0]:
            engine.evaluate_exit(pos, price)
            stops.append(pos.stop_price)

        for i in range(1, len(stops)):
            self.assertGreaterEqual(stops[i], stops[i - 1],
                msg=f"Stop went down from {stops[i-1]} to {stops[i]}")


# ---------------------------------------------------------------------------
# Group 8 — Custom risk config thresholds (Gap 3: inline RiskConfig, no YAML)
# ---------------------------------------------------------------------------

class TestCustomRiskConfigThresholds(unittest.TestCase):

    def _make_config(self, breakeven_at_r=1.0, ema10_at_r=1.5, ema21_at_r=3.0) -> RiskConfig:
        config = RiskConfig()
        config.profit_target.breakeven_at_r = breakeven_at_r
        config.profit_target.ema10_at_r = ema10_at_r
        config.profit_target.ema21_at_r = ema21_at_r
        return config

    def test_custom_breakeven_threshold_fires_early(self):
        # Configured to move to breakeven at only +0.5R
        config = self._make_config(breakeven_at_r=0.5)
        engine = make_engine(ema10=None, ema21=None, risk_config=config)
        pos = make_position()

        engine.evaluate_exit(pos, 155.0)  # exactly +0.5R
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

    def test_custom_ema10_threshold_fires_at_configured_r(self):
        # Configured EMA10 trailing at +2R instead of +1.5R
        config = self._make_config(ema10_at_r=2.0)
        engine = make_engine(ema10=155.0, ema21=None, risk_config=config)
        pos = make_position()

        # At +1.5R — should NOT trail EMA10 yet (threshold is +2R)
        engine.evaluate_exit(pos, 165.0)
        self.assertNotEqual(pos.current_stop_type, 'EMA10')

        # At +2R — should now trail EMA10
        pos2 = make_position()
        engine.evaluate_exit(pos2, 170.0)
        self.assertEqual(pos2.current_stop_type, 'EMA10')


# ---------------------------------------------------------------------------
# Gap 1 — Lifecycle: R multiples stay correct after stop ratchets
# ---------------------------------------------------------------------------

class TestLifecycle(unittest.TestCase):

    def test_r_multiple_correct_after_breakeven_ratchet(self):
        """Stop ratchet must not corrupt R multiple on subsequent calls.

        Bug: if initial_stop = position.stop_price and stop has moved to
        entry (breakeven), the next call computes risk/share = 0, returning
        r_multiple = 0.0 instead of the real value. This prevents EMA10
        trailing from ever activating after breakeven.
        """
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()

        # Call 1: price at +1R — stop ratchets to breakeven
        signal1 = engine.evaluate_exit(pos, 161.0)
        self.assertFalse(signal1.should_exit)
        self.assertEqual(pos.stop_price, 150.0, "stop should be at breakeven")

        # Call 2: price at +1.5R — EMA10 should trail (engine now has EMA data)
        engine._get_ema_values = Mock(return_value=(155.0, None))
        signal2 = engine.evaluate_exit(pos, 165.0)

        # If the bug exists, r_multiple would be 0.0 here and EMA10 wouldn't fire
        self.assertFalse(signal2.should_exit)
        self.assertEqual(pos.stop_price, 155.0,
            "EMA10 trailing should have fired — r_multiple was corrupted by stop ratchet if not")
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_full_lifecycle_initial_stop_to_target(self):
        """Full position lifecycle: HARD → BREAKEVEN → EMA10 → EMA21 → exit."""
        pos = make_position()

        # Phase 1: hold below +1R
        engine = make_engine(ema10=None, ema21=None)
        s = engine.evaluate_exit(pos, 155.0)  # +0.5R
        self.assertFalse(s.should_exit)
        self.assertEqual(pos.current_stop_type, 'HARD')

        # Phase 2: breakeven at +1R
        s = engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

        # Phase 3: EMA10 trailing at +1.5R
        engine._get_ema_values = Mock(return_value=(155.0, None))
        s = engine.evaluate_exit(pos, 165.0)
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

        # Phase 4: EMA21 trailing at +3R
        engine._get_ema_values = Mock(return_value=(162.0, 168.0))
        s = engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 168.0)
        self.assertEqual(pos.current_stop_type, 'EMA21')

        # Phase 5: target exit
        s = engine.evaluate_exit(pos, 170.0)
        self.assertTrue(s.should_exit)
        self.assertIn('TARGET_HIT', s.reason)


# ---------------------------------------------------------------------------
# Group 9 — _get_cached_data / _get_ema_values (real implementation)
# ---------------------------------------------------------------------------

class TestGetCachedData(unittest.TestCase):
    """Tests for the real _get_cached_data and _get_ema_values (no mock seam)."""

    def _make_hist(self, rows=55) -> pd.DataFrame:
        """Return a minimal DataFrame that passes the len >= 50 check."""
        closes = [100.0 + i * 0.1 for i in range(rows)]
        return pd.DataFrame({
            'Close': closes,
            'High':  [c + 1 for c in closes],
            'Low':   [c - 1 for c in closes],
            'Volume': [1_000_000] * rows,
        })

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_cache_miss_fetches_and_returns_data(self, mock_ticker_class):
        """On first call, fetches from yfinance and caches result."""
        engine = ExitEngine()
        hist = self._make_hist(55)
        mock_ticker_class.return_value.history.return_value = hist

        result = engine._get_cached_data('AAPL')

        self.assertIsNotNone(result)
        self.assertIn('EMA10', result.columns)
        self.assertIn('EMA21', result.columns)
        self.assertIn('AAPL', engine.price_cache)

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_cache_hit_does_not_refetch(self, mock_ticker_class):
        """Second call returns cached data without calling yfinance again."""
        engine = ExitEngine()
        hist = self._make_hist(55)
        mock_ticker_class.return_value.history.return_value = hist

        engine._get_cached_data('AAPL')
        engine._get_cached_data('AAPL')

        mock_ticker_class.return_value.history.assert_called_once()

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_insufficient_history_returns_none(self, mock_ticker_class):
        """Fewer than 50 rows → returns None, nothing cached."""
        engine = ExitEngine()
        mock_ticker_class.return_value.history.return_value = self._make_hist(30)

        result = engine._get_cached_data('AAPL')

        self.assertIsNone(result)
        self.assertNotIn('AAPL', engine.price_cache)

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_yfinance_exception_returns_none(self, mock_ticker_class):
        """yfinance error → returns None gracefully."""
        engine = ExitEngine()
        mock_ticker_class.return_value.history.side_effect = Exception('network error')

        result = engine._get_cached_data('AAPL')

        self.assertIsNone(result)

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_expired_cache_is_cleared_and_refetched(self, mock_ticker_class):
        """Cache older than 5 minutes is invalidated and data is refetched."""
        engine = ExitEngine()
        hist = self._make_hist(55)
        mock_ticker_class.return_value.history.return_value = hist

        # Seed cache with a stale timestamp (10 minutes ago)
        engine.price_cache['AAPL'] = hist
        engine.cache_timestamp = datetime.now() - pd.Timedelta(minutes=10)

        engine._get_cached_data('AAPL')

        # Should have refetched — called once after cache cleared
        mock_ticker_class.return_value.history.assert_called_once()

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_get_ema_values_returns_last_row(self, mock_ticker_class):
        """_get_ema_values returns the most recent EMA10 and EMA21."""
        engine = ExitEngine()
        hist = self._make_hist(55)
        hist['EMA10'] = 101.0
        hist['EMA21'] = 99.0
        engine.price_cache['AAPL'] = hist

        ema10, ema21 = engine._get_ema_values('AAPL')

        self.assertAlmostEqual(ema10, 101.0)
        self.assertAlmostEqual(ema21, 99.0)

    @patch('traderlib.paper_exits.yf.Ticker')
    def test_get_ema_values_returns_none_when_no_data(self, mock_ticker_class):
        """_get_ema_values returns (None, None) when cache returns None."""
        engine = ExitEngine()
        mock_ticker_class.return_value.history.return_value = self._make_hist(5)

        ema10, ema21 = engine._get_ema_values('AAPL')

        self.assertIsNone(ema10)
        self.assertIsNone(ema21)


# ---------------------------------------------------------------------------
# Group 10 — evaluate_exit: no initial_risk fallback + no risk_config defaults
# ---------------------------------------------------------------------------

class TestEvaluateExitEdgePaths(unittest.TestCase):

    def test_r_multiple_falls_back_when_no_initial_risk(self):
        """Position with initial_risk=0 uses _calculate_r_multiple fallback."""
        engine = make_engine(ema10=None, ema21=None)
        # Override make_position to have no initial_risk
        pos = make_position(initial_risk=0.0)
        signal = engine.evaluate_exit(pos, 161.0)  # +1R by stop math
        # Should still compute r_multiple correctly via fallback
        self.assertAlmostEqual(signal.r_multiple, 1.1, places=1)

    def test_no_risk_config_uses_default_thresholds(self):
        """Engine with risk_config=None uses hardcoded 1.0/1.5/3.0 thresholds."""
        engine = ExitEngine(risk_config=None)
        engine._get_ema_values = Mock(return_value=(None, None))
        pos = make_position()

        # At +1R (160 → actually 161 to be just over), breakeven should still fire
        engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')


# ---------------------------------------------------------------------------
# Group 11 — get_position_summary
# ---------------------------------------------------------------------------

class TestGetPositionSummary(unittest.TestCase):

    def setUp(self):
        self.engine = ExitEngine()

    def test_summary_keys_present(self):
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 160.0)
        for key in ('ticker', 'current_price', 'entry_price', 'shares',
                    'stop_price', 'stop_type', 'unrealized_pnl',
                    'unrealized_pct', 'r_multiple', 'pct_to_stop'):
            self.assertIn(key, summary, f"missing key: {key}")

    def test_summary_unrealized_pnl_at_plus_1r(self):
        # entry=150, stop=140, shares=100, price=160 → PnL = +1000
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 160.0)
        self.assertAlmostEqual(summary['unrealized_pnl'], 1000.0)

    def test_summary_unrealized_pnl_negative(self):
        # price below entry
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 145.0)
        self.assertAlmostEqual(summary['unrealized_pnl'], -500.0)

    def test_summary_r_multiple_at_plus_1r(self):
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 160.0)
        self.assertAlmostEqual(summary['r_multiple'], 1.0)

    def test_summary_pct_to_stop(self):
        # price=160, stop=140 → (160-140)/160 * 100 = 12.5%
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 160.0)
        self.assertAlmostEqual(summary['pct_to_stop'], 12.5)

    def test_summary_ticker_and_price_match(self):
        pos = make_position()
        summary = self.engine.get_position_summary(pos, 155.0)
        self.assertEqual(summary['ticker'], 'TEST')
        self.assertEqual(summary['current_price'], 155.0)
        self.assertEqual(summary['entry_price'], 150.0)
        self.assertEqual(summary['shares'], 100)


# ---------------------------------------------------------------------------
# Group 12 — calculate_initial_stop
# ---------------------------------------------------------------------------

class TestCalculateInitialStop(unittest.TestCase):

    def _make_hist(self, rows=60, base=100.0) -> pd.DataFrame:
        """Create simple historical data for testing."""
        closes = [base + i * 0.1 for i in range(rows)]
        highs  = [c + 2 for c in closes]
        lows   = [c - 2 for c in closes]
        return pd.DataFrame({'Close': closes, 'High': highs, 'Low': lows,
                             'Volume': [1_000_000] * rows})

    def _percent_config(self, pct=0.07) -> RiskConfig:
        config = RiskConfig()
        config.stop_loss.method = 'percent'
        config.stop_loss.fixed_pct = pct
        return config

    def test_historical_data_injection_works(self):
        """Pass mock DataFrame, verify ATR calculated from it (no yfinance)."""
        hist = self._make_hist(60)
        config = RiskConfig()
        config.stop_loss.method = 'atr'
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=hist)
        self.assertLess(stop, 100.0)

    def test_historical_data_column_validation(self):
        """Pass DataFrame with wrong columns, expect clear error."""
        bad_hist = pd.DataFrame({'Open': [1, 2, 3], 'Close': [4, 5, 6]})
        config = RiskConfig()
        config.stop_loss.method = 'atr'
        engine = ExitEngine(risk_config=config)
        with self.assertRaises(ValueError) as ctx:
            engine.calculate_initial_stop('FAKE', 100.0, historical_data=bad_hist)
        self.assertIn('missing required columns', str(ctx.exception).lower())

    def test_percent_method_applies_fixed_pct(self):
        config = self._percent_config(pct=0.05)
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 200.0, historical_data=self._make_hist(60))
        self.assertAlmostEqual(stop, 190.0)

    def test_insufficient_history_falls_back_to_percent(self):
        """< 14 bars → fallback to fallback_pct."""
        config = RiskConfig()
        config.stop_loss.fallback_pct = 0.07
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=self._make_hist(5))
        self.assertAlmostEqual(stop, 93.0)

    def test_atr_method_returns_stop_below_entry(self):
        """Pure ATR method: stop should be below entry price."""
        config = RiskConfig()
        config.stop_loss.method = 'atr'
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=self._make_hist(60))
        self.assertLess(stop, 100.0)

    def test_atr_or_support_returns_stop_below_entry(self):
        """atr_or_support: stop should be below entry price."""
        engine = ExitEngine()  # default method = atr_or_support
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=self._make_hist(60))
        self.assertLess(stop, 100.0)

    def test_min_stop_distance_enforced(self):
        """Stop too close to entry gets pushed down to min distance."""
        # ATR is tiny — stop would be very close to entry without enforcement
        closes = [100.0] * 60   # flat price = ATR ≈ 0
        hist = pd.DataFrame({'Close': closes, 'High': [100.01] * 60,
                             'Low': [99.99] * 60, 'Volume': [1_000_000] * 60})
        config = RiskConfig()
        config.stop_loss.method = 'atr'
        config.stop_loss.min_stop_distance_pct = 0.03
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=hist)
        # Must be at most entry * (1 - min_pct)
        self.assertLessEqual(stop, 100.0 * (1 - 0.03) + 0.01)

    def test_max_stop_distance_enforced(self):
        """Stop too far from entry gets clamped to max distance."""
        # Very wide ATR
        closes = [100.0] * 60
        hist = pd.DataFrame({'Close': closes, 'High': [120.0] * 60,
                             'Low': [80.0] * 60, 'Volume': [1_000_000] * 60})
        config = RiskConfig()
        config.stop_loss.method = 'atr'
        config.stop_loss.max_stop_distance_pct = 0.10
        engine = ExitEngine(risk_config=config)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=hist)
        self.assertGreaterEqual(stop, 100.0 * (1 - 0.10) - 0.01)

    def test_no_risk_config_applies_default_bounds(self):
        """Without risk_config, default 3-15% bounds are applied."""
        closes = [100.0] * 60
        hist = pd.DataFrame({'Close': closes, 'High': [100.01] * 60,
                             'Low': [99.99] * 60, 'Volume': [1_000_000] * 60})
        engine = ExitEngine(risk_config=None)
        stop = engine.calculate_initial_stop('FAKE', 100.0, historical_data=hist)
        # Must be within default 3-15% band
        self.assertLessEqual(stop, 97.0 + 0.01)
        self.assertGreaterEqual(stop, 85.0 - 0.01)


# ---------------------------------------------------------------------------
# Group 13 — calculate_target_price
# ---------------------------------------------------------------------------

class TestCalculateTargetPrice(unittest.TestCase):

    def setUp(self):
        self.engine = ExitEngine()

    def test_default_2r_target(self):
        # entry=150, stop=140 → risk=10 → target = 150 + 10*2 = 170
        target = self.engine.calculate_target_price(150.0, 140.0)
        self.assertAlmostEqual(target, 170.0)

    def test_explicit_r_multiple_override(self):
        # min_r=3 → 150 + 10*3 = 180
        target = self.engine.calculate_target_price(150.0, 140.0, min_r=3.0)
        self.assertAlmostEqual(target, 180.0)

    def test_zero_risk_returns_10pct_above_entry(self):
        # stop == entry → no risk → fallback to +10%
        target = self.engine.calculate_target_price(150.0, 150.0)
        self.assertAlmostEqual(target, 165.0)

    def test_inverted_stop_returns_10pct_above_entry(self):
        # stop above entry → negative risk → fallback
        target = self.engine.calculate_target_price(150.0, 160.0)
        self.assertAlmostEqual(target, 165.0)

    def test_uses_risk_config_r_multiple(self):
        config = RiskConfig()
        config.profit_target.min_r_multiple = 3.0
        engine = ExitEngine(risk_config=config)
        # entry=150, stop=140 → risk=10 → target = 150 + 10*3 = 180
        target = engine.calculate_target_price(150.0, 140.0)
        self.assertAlmostEqual(target, 180.0)


# ---------------------------------------------------------------------------
# Group 14 — calculate_position_size
# ---------------------------------------------------------------------------

class TestCalculatePositionSize(unittest.TestCase):

    def test_dual_constraint_path_with_risk_config(self):
        """With risk_config, delegates to calculate_position_size_with_constraints."""
        engine = ExitEngine()  # loads default RiskConfig via RiskConfigManager
        shares = engine.calculate_position_size(100_000, 150.0, 140.0)
        self.assertIsInstance(shares, int)
        self.assertGreater(shares, 0)

    def test_last_position_calc_stored_after_call(self):
        """Metadata from dual-constraint sizing is accessible via get_last_position_calc."""
        engine = ExitEngine()
        engine.calculate_position_size(100_000, 150.0, 140.0)
        meta = engine.get_last_position_calc()
        self.assertIsNotNone(meta)
        self.assertIsInstance(meta, dict)

    def test_get_last_position_calc_returns_none_before_any_call(self):
        """No calculation yet → get_last_position_calc returns None."""
        engine = ExitEngine()
        self.assertIsNone(engine.get_last_position_calc())

    def test_fallback_path_no_risk_config(self):
        """Without risk_config, uses 0.75% account risk fallback."""
        engine = ExitEngine.__new__(ExitEngine)
        engine.price_cache = {}
        engine.cache_timestamp = None
        engine.risk_config = None
        # equity=100k, risk=0.75% → $750 / $10 risk/share = 75 shares → round to 70
        shares = engine.calculate_position_size(100_000, 150.0, 140.0)
        self.assertEqual(shares, 70)

    def test_fallback_explicit_risk_pct_override(self):
        """account_risk_pct override is respected in fallback path."""
        engine = ExitEngine.__new__(ExitEngine)
        engine.price_cache = {}
        engine.cache_timestamp = None
        engine.risk_config = None
        # equity=100k, risk=1% → $1000 / $10 = 100 shares
        shares = engine.calculate_position_size(100_000, 150.0, 140.0,
                                                account_risk_pct=0.01)
        self.assertEqual(shares, 100)

    def test_fallback_zero_risk_returns_zero(self):
        """stop >= entry → risk/share <= 0 → returns 0."""
        engine = ExitEngine.__new__(ExitEngine)
        engine.price_cache = {}
        engine.cache_timestamp = None
        engine.risk_config = None
        shares = engine.calculate_position_size(100_000, 150.0, 150.0)
        self.assertEqual(shares, 0)


if __name__ == '__main__':
    unittest.main()
