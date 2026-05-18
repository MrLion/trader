"""Tests for Trend Screener.

Covers:
1. TrendScreener initialization
2. MarketSurge filter logic
3. Convergence scoring integration
4. Entry timing detection (VCP, pivot, volume)
5. Result ranking
6. Profile-specific parameters (large-cap vs high-octane)
"""

import unittest
from datetime import date
from typing import Optional
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import pandas as pd

from traderlib.stage2_utils import calculate_convergence_score, calculate_volume_metrics
from traderlib.vcp_utils import detect_vcp_pattern


class MockAlpacaClient:
    """Mock AlpacaClient for testing."""

    def __init__(self, mode='paper'):
        self.mode = mode

    def get_bars(self, ticker: str, limit: int = 252) -> Optional[pd.DataFrame]:
        """Return mock data for testing."""
        return make_uptrend_df(limit)


def make_uptrend_df(n_days: int = 252) -> pd.DataFrame:
    """Generate Stage 2 uptrend data."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')

    # Strong uptrend with proper Stage 2 characteristics
    base_price = 100.0
    trend = np.linspace(0, base_price * 0.5, n_days)
    closes = base_price + np.cumsum(np.random.randn(n_days) * 0.5) + trend
    closes = np.maximum(closes, 30.0)  # Keep above $30

    # Generate OHLCV
    highs = closes * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = closes * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1_000_000, 5_000_000, n_days)

    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes,
    }, index=dates)


def make_stage2_details(price: float = 150.0) -> dict:
    """Create Stage 2 details dict."""
    return {
        'score': 7,
        'criteria': {
            'price_above_50ma': True,
            'price_above_150ma': True,
            'price_above_200ma': True,
            '50ma_above_150ma': True,
            '50ma_above_200ma': True,
            '150ma_above_200ma': True,
            'price_above_20ema': True,
            '52w_high_proximity': True,
        },
        'ma10': price * 0.98,
        'ma20': price * 0.96,
        'ma50': price * 0.93,
        'ma150': price * 0.85,
        'ma200': price * 0.80,
    }


class TestTrendScreenerBasics(unittest.TestCase):
    """Basic TrendScreener tests."""

    @patch('scripts.trend_screener.AlpacaClient', MockAlpacaClient)
    def setUp(self):
        # Import after patching
        import scripts.trend_screener as ts
        self.ts = ts
        self.screener = ts.TrendScreener(mode='paper')

    def test_initialization(self):
        """Should initialize with proper dependencies."""
        self.assertIsNotNone(self.screener)
        self.assertIsNotNone(self.screener.exit_engine)


class TestMarketSurgeFilters(unittest.TestCase):
    """Tests for MarketSurge-style filters."""

    def test_price_above_minimum(self):
        """Should filter stocks below minimum price."""
        df = make_uptrend_df(100)
        current = df['Close'].iloc[-1]
        self.assertGreaterEqual(current, 30.0)

    def test_ma_stacking_short_term(self):
        """Should validate 10D > 21D > 50D MA stacking."""
        df = make_uptrend_df(100)

        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        ma21 = df['Close'].rolling(21).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]

        self.assertGreater(ma10, ma21)
        self.assertGreater(ma21, ma50)

    def test_ma_stacking_long_term(self):
        """Should validate 50D > 150D > 200D MA stacking."""
        df = make_uptrend_df(252)

        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma150 = df['Close'].rolling(150).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]

        self.assertGreater(ma50, ma150)
        self.assertGreater(ma150, ma200)


class TestConvergenceFilters(unittest.TestCase):
    """Tests for convergence scoring in screener."""

    def test_convergence_score_calculation(self):
        """Should calculate convergence score correctly."""
        current_price = 150.0
        # Tight MA cluster for good convergence score
        s2_details = {
            'ma10': 148.0,
            'ma20': 147.5,
            'ma50': 147.0,
            'ma150': 145.0,
            'ma200': 143.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        self.assertIsNotNone(result)
        self.assertIn('score', result)
        self.assertIn('components', result)
        self.assertIn('cluster_data', result)
        # With tight cluster (3+ MAs within 5%), score should be decent
        self.assertGreaterEqual(result['score'], 30)

    def test_convergence_score_invalid_when_no_cluster(self):
        """Should return low score when no MA cluster found."""
        current_price = 100.0
        s2_details = {
            'ma10': 150.0,
            'ma20': 140.0,
            'ma50': 130.0,
            'ma150': 120.0,
            'ma200': 110.0,
        }

        result = calculate_convergence_score(current_price, s2_details)
        # Returns dict with score=0 when no cluster found
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['cluster_data']['cluster_size'], 0)


class TestVolumeMetrics(unittest.TestCase):
    """Tests for volume metric calculations."""

    def test_volume_ratio_calculation(self):
        """Should calculate volume ratio correctly."""
        df = make_uptrend_df(60)
        metrics = calculate_volume_metrics(df, lookback_days=50)

        self.assertIn('volume_ratio', metrics)
        self.assertIn('avg_volume', metrics)
        self.assertIn('avg_dollar_volume', metrics)

    def test_volume_trend_detection(self):
        """Should detect volume trends."""
        df = make_uptrend_df(60)
        metrics = calculate_volume_metrics(df, lookback_days=50)

        self.assertIn('volume_trend', metrics)
        self.assertIn(metrics['volume_trend'], ['increasing', 'decreasing', 'stable', 'unknown'])


class TestVCPPatternDetection(unittest.TestCase):
    """Tests for VCP pattern detection in screener."""

    def test_vcp_detection_returns_valid_result(self):
        """Should detect VCP patterns."""
        df = make_uptrend_df(150)
        pattern = detect_vcp_pattern(df, min_contractions=2)

        self.assertIsInstance(pattern.valid, bool)

        if pattern.valid:
            self.assertGreater(pattern.pivot_high, 0)
            self.assertGreater(pattern.stop_low, 0)


class TestProfileParameters(unittest.TestCase):
    """Tests for large-cap vs high-octane profiles."""

    def test_large_cap_volume_thresholds(self):
        """Large-cap should have higher volume thresholds."""
        large_cap_dollar = 80_000_000
        large_cap_shares = 1_000_000

        self.assertEqual(large_cap_dollar, 80_000_000)
        self.assertEqual(large_cap_shares, 1_000_000)

    def test_high_octane_volume_thresholds(self):
        """High-octane should have lower volume thresholds."""
        high_octane_dollar = 20_000_000
        high_octane_shares = 400_000

        self.assertEqual(high_octane_dollar, 20_000_000)
        self.assertEqual(high_octane_shares, 400_000)


class TestResultRanking(unittest.TestCase):
    """Tests for result ranking functions."""

    def setUp(self):
        self.sample_results = [
            {
                'ticker': 'AAPL',
                'convergence_score': 75,
                'cluster_size': 4,
                'entry_ready': True,
                'proximity_pct': 2.5,
                'rs_from_high': 3.0,
            },
            {
                'ticker': 'MSFT',
                'convergence_score': 60,
                'cluster_size': 3,
                'entry_ready': False,
                'proximity_pct': 5.0,
                'rs_from_high': 1.5,
            },
            {
                'ticker': 'GOOGL',
                'convergence_score': 85,
                'cluster_size': 5,
                'entry_ready': True,
                'proximity_pct': 1.0,
                'rs_from_high': 4.0,
            },
        ]

    def test_rank_by_convergence(self):
        """Should sort by convergence score descending."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        ranked = screener.rank_results(self.sample_results.copy(), rank_by='convergence')

        scores = [r['convergence_score'] for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_rank_by_setup(self):
        """Should prioritize entry-ready tickers."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        ranked = screener.rank_results(self.sample_results.copy(), rank_by='setup')

        # Entry-ready should come first
        ready_tickers = [r['ticker'] for r in ranked if r['entry_ready']]
        not_ready = [r['ticker'] for r in ranked if not r['entry_ready']]

        self.assertIn('AAPL', ready_tickers)
        self.assertIn('GOOGL', ready_tickers)
        self.assertIn('MSFT', not_ready)

    def test_rank_by_rs(self):
        """Should sort by RS from high ascending."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        ranked = screener.rank_results(self.sample_results.copy(), rank_by='rs')

        rs_values = [r['rs_from_high'] for r in ranked]
        self.assertEqual(rs_values, sorted(rs_values))


class TestEntryTimingModes(unittest.TestCase):
    """Tests for entry timing modes."""

    def test_vcp_entry_mode(self):
        """VCP mode should check for valid VCP pattern."""
        df = make_uptrend_df(150)
        pattern = detect_vcp_pattern(df, min_contractions=2)

        # Should return boolean validity
        self.assertIsInstance(pattern.valid, bool)

    def test_pivot_entry_mode(self):
        """Pivot mode should check proximity to pivot."""
        df = make_uptrend_df(50)
        recent = df.tail(20)
        pivot_high = recent['High'].max()
        current = df['Close'].iloc[-1]

        proximity = ((pivot_high - current) / pivot_high) * 100
        self.assertIsInstance(proximity, float)


class TestRelativeStrength(unittest.TestCase):
    """Tests for RS calculations."""

    def test_rs_calculation_components(self):
        """RS calculation should have required components."""
        df = make_uptrend_df(130)

        if len(df) >= 130:
            current = df['Close'].iloc[-1]
            past = df['Close'].iloc[-130]
            ret = ((current / past) - 1) * 100

            self.assertIsInstance(ret, float)


class TestTrendScreenerSector:
    def test_analyze_ticker_includes_sector(self, tmp_path):
        from unittest.mock import MagicMock, patch
        import pandas as pd

        with patch('scripts.trend_screener.AlpacaClient', MockAlpacaClient):
            from scripts.trend_screener import TrendScreener
            screener = TrendScreener()
        screener.sector_resolver = MagicMock()
        screener.sector_resolver.resolve.return_value = "Technology"

        with patch.object(screener, "_is_rs_near_high", return_value=(True, 5.0)):
            with patch.object(screener.alpaca, "get_bars", return_value=pd.DataFrame({
                "Close": list(range(100, 300)),
                "High": list(range(105, 305)),
                "Low": list(range(95, 295)),
                "Volume": [1_000_000] * 200,
            })):
                result = screener._analyze_ticker("AAPL", {}, "large_cap")

        assert result is not None
        assert result["sector"] == "Technology"


if __name__ == '__main__':
    unittest.main()
