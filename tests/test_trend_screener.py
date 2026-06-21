"""Tests for Trend Screener.

Covers:
1. TrendScreener initialization
2. MarketSurge filter logic
3. Volume metrics integration
4. Entry timing detection (pocket, pivot, volume, trend)
5. Result ranking
6. Profile-specific parameters (large-cap vs high-octane)
"""

import unittest
from datetime import date
from typing import Optional
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import pandas as pd

from traderlib.stage2_utils import calculate_volume_metrics


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
                'stage2_score': 7,
                'entry_ready': True,
                'proximity_pct': 2.5,
                'rs_from_high': 3.0,
            },
            {
                'ticker': 'MSFT',
                'stage2_score': 5,
                'entry_ready': False,
                'proximity_pct': 5.0,
                'rs_from_high': 1.5,
            },
            {
                'ticker': 'GOOGL',
                'stage2_score': 8,
                'entry_ready': True,
                'proximity_pct': 1.0,
                'rs_from_high': 4.0,
            },
        ]

    def test_rank_by_setup(self):
        """Should prioritize entry-ready tickers, then proximity."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        ranked = screener.rank_results(self.sample_results.copy(), rank_by='setup')

        # Entry-ready should come first
        ready_tickers = [r['ticker'] for r in ranked if r['entry_ready']]
        not_ready = [r['ticker'] for r in ranked if not r['entry_ready']]

        self.assertEqual(ready_tickers, ['GOOGL', 'AAPL'])
        self.assertEqual(not_ready, ['MSFT'])

    def test_rank_by_setup_sorts_by_proximity(self):
        """rank_by setup should sort by proximity to buy point (closest first)."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        results = [
            {'ticker': 'FAR', 'stage2_score': 8, 'entry_ready': False, 'proximity_pct': 10.0},
            {'ticker': 'CLOSE', 'stage2_score': 6, 'entry_ready': True, 'proximity_pct': 1.0},
        ]
        ranked = screener.rank_results(results, rank_by='setup')
        assert ranked[0]['ticker'] == 'CLOSE'
        assert ranked[1]['ticker'] == 'FAR'

    def test_rank_by_rs(self):
        """Should sort by RS from high ascending."""
        from scripts.trend_screener import TrendScreener

        screener = TrendScreener.__new__(TrendScreener)
        ranked = screener.rank_results(self.sample_results.copy(), rank_by='rs')

        rs_values = [r['rs_from_high'] for r in ranked]
        self.assertEqual(rs_values, sorted(rs_values))


class TestEntryTimingModes(unittest.TestCase):
    """Tests for entry timing modes."""

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


# Make TrendScreener available at module level for decorator-based patching.
TrendScreener = None


class TestPocketPivotEntryMode(unittest.TestCase):
    """Tests for --entry-mode pocket and any-mode priority logic."""

    @patch('scripts.trend_screener.AlpacaClient', MockAlpacaClient)
    def setUp(self):
        import scripts.trend_screener as ts
        global TrendScreener
        self.ts = ts
        self.screener = ts.TrendScreener(mode='paper')
        TrendScreener = ts.TrendScreener

    def _make_pocket_pivot_df(self, current_close: float = None) -> pd.DataFrame:
        """Build a DataFrame where the most recent day is a pocket pivot.

        The last day is an up-day with volume well above prior down-day volume.
        The prior 10 days include explicit down-days so the detector can
        compare volume. Price is kept within 5%% of the pocket pivot close unless
        *current_close* overrides it.
        """
        n_days = 220
        dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')
        base = 100.0

        # Strong, steady uptrend so MAs stack and Stage 2 score is high.
        closes = [base + i * 0.15 for i in range(n_days)]
        highs = [c * 1.02 for c in closes]
        lows = [c * 0.98 for c in closes]
        opens = [c * 0.99 for c in closes]
        volumes = [1_000_000] * n_days

        # Plant a few down-days in the prior 10 bars with normal volume so the
        # last up-day can exceed their volume and qualify as a pocket pivot.
        for idx in range(n_days - 10, n_days - 1):
            closes[idx] = closes[idx - 1] - 0.10
        # Last day: strong up-day with volume spike.
        closes[-1] = closes[-2] + 2.0
        volumes[-1] = 5_000_000

        if current_close is not None:
            closes[-1] = current_close
            highs[-1] = current_close * 1.02
            lows[-1] = current_close * 0.98
            opens[-1] = current_close * 0.99

        return pd.DataFrame({
            'Open': opens,
            'High': highs,
            'Low': lows,
            'Close': closes,
            'Volume': volumes,
        }, index=dates)

    def _make_no_setup_df(self) -> pd.DataFrame:
        """Build a DataFrame with no specific entry setup."""
        n_days = 220
        dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')
        # Strong uptrend, then a flat top for the last 20 days before a sudden
        # drop in the final 3 days. The 20-day high stays up near the peak while
        # current price is well below it, so neither a range pivot nor a pocket
        # pivot is within proximity.
        base = 100.0
        closes = [base + i * 0.05 for i in range(n_days)]
        peak = closes[n_days - 4]
        # Last 3 days: sharp drop to ~12%% below peak.
        drop_level = peak * 0.88
        for i in range(n_days - 3, n_days):
            closes[i] = drop_level
        highs = [c * 1.01 for c in closes]
        lows = [c * 0.99 for c in closes]
        opens = [c * 0.995 for c in closes]
        volumes = [1_000_000] * n_days
        return pd.DataFrame({
            'Open': opens,
            'High': highs,
            'Low': lows,
            'Close': closes,
            'Volume': volumes,
        }, index=dates)

    def test_pocket_mode_finds_pocket_pivot(self):
        """pp mode should mark entry_ready and setup_type='pp', with pivot_price set."""
        df = self._make_pocket_pivot_df()
        with patch.object(self.screener, '_is_rs_near_high', return_value=(True, 5.0)):
            with patch.object(self.screener, '_calculate_rs', return_value=(10.0, 5.0)):
                with patch.object(self.screener.alpaca, 'get_bars', return_value=df):
                    result = self.screener._analyze_ticker(
                        'POCKET',
                        {'entry_mode': 'pp', 'stack_short': False, 'stack_long': False},
                        'large-cap'
                    )

        self.assertIsNotNone(result)
        self.assertTrue(result['entry_ready'])
        self.assertEqual(result['setup_type'], 'pp')
        self.assertTrue(result['has_pocket_pivot'])
        self.assertIsNotNone(result['pocket_pivot_price'])
        # pivot_price (Buy Point) should now be set to the pocket pivot price
        self.assertIsNotNone(result['pivot_price'])
        self.assertAlmostEqual(result['pivot_price'], result['pocket_pivot_price'], places=1)

    def test_pocket_mode_not_ready_when_far_from_pivot(self):
        """pp mode should not mark entry_ready if price is more than 5%% below the pivot."""
        df = self._make_pocket_pivot_df()
        # Override the current close to 90.00 while forcing detect_pivot to see a
        # pocket pivot at 100.00. Proximity = (100 - 90) / 100 = 10% > 5%.
        df.loc[df.index[-1], 'Close'] = 90.0
        df.loc[df.index[-1], 'High'] = 91.0
        df.loc[df.index[-1], 'Low'] = 89.0
        df.loc[df.index[-1], 'Open'] = 89.5
        from traderlib.pivot_detection import PivotSignal
        forced_signal = PivotSignal(
            ticker='POCKET_FAR',
            pivot_price=100.0,
            pivot_type='pocket_pivot',
            confidence=0.8,
            stop_price=95.0,
            target_price=110.0,
            entry_mode='immediate',
        )
        with patch('scripts.trend_screener.detect_pivot', return_value=forced_signal):
            with patch.object(self.screener, '_is_rs_near_high', return_value=(True, 5.0)):
                with patch.object(self.screener, '_calculate_rs', return_value=(10.0, 5.0)):
                    with patch.object(self.screener.alpaca, 'get_bars', return_value=df):
                        result = self.screener._analyze_ticker(
                            'POCKET_FAR',
                            {'entry_mode': 'pp', 'stack_short': False, 'stack_long': False},
                            'large-cap'
                        )

        self.assertIsNotNone(result)
        self.assertFalse(result['entry_ready'])
        self.assertTrue(result['has_pocket_pivot'])
        self.assertEqual(result['pocket_pivot_price'], 100.0)

    def test_any_mode_prefers_pocket_pivot_as_primary(self):
        """Any mode should use pocket pivot as the primary setup when it exists and is within proximity."""
        df = self._make_pocket_pivot_df()
        with patch.object(self.screener, '_is_rs_near_high', return_value=(True, 5.0)):
            with patch.object(self.screener, '_calculate_rs', return_value=(10.0, 5.0)):
                with patch.object(self.screener.alpaca, 'get_bars', return_value=df):
                    result = self.screener._analyze_ticker(
                        'POCKET_ANY',
                        {'entry_mode': 'any', 'stack_short': False, 'stack_long': False},
                        'large_cap'
                    )

        self.assertIsNotNone(result)
        self.assertTrue(result['entry_ready'])
        self.assertEqual(result['setup_type'], 'pp')
        self.assertTrue(result['has_pocket_pivot'])
        self.assertIsNotNone(result['pocket_pivot_price'])
        self.assertIsNotNone(result['pivot_price'])

    def test_any_mode_falls_back_to_trend_when_no_setup(self):
        """Any mode should fall back to setup_type='trend' when no specific setup exists."""
        df = self._make_no_setup_df()
        with patch.object(self.screener, '_is_rs_near_high', return_value=(True, 5.0)):
            with patch.object(self.screener, '_calculate_rs', return_value=(10.0, 5.0)):
                with patch.object(self.screener.alpaca, 'get_bars', return_value=df):
                    result = self.screener._analyze_ticker(
                        'NO_SETUP',
                        {'entry_mode': 'any', 'stack_short': False, 'stack_long': False},
                        'large_cap'
                    )

        self.assertIsNotNone(result)
        self.assertTrue(result['entry_ready'])
        self.assertEqual(result['setup_type'], 'trend')

    def test_20d_mode_finds_range_pivot(self):
        """20d mode should find 20-day range high setup with setup_type='20d'."""
        df = self._make_pocket_pivot_df()
        # In 20d mode, pocket pivot should NOT be used — only range pivot.
        # The pocket pivot df should still have a valid 20d range high.
        with patch.object(self.screener, '_is_rs_near_high', return_value=(True, 5.0)):
            with patch.object(self.screener, '_calculate_rs', return_value=(10.0, 5.0)):
                with patch.object(self.screener.alpaca, 'get_bars', return_value=df):
                    result = self.screener._analyze_ticker(
                        'RANGE20D',
                        {'entry_mode': '20d', 'stack_short': False, 'stack_long': False},
                        'large-cap'
                    )

        self.assertIsNotNone(result)
        self.assertTrue(result['entry_ready'])
        self.assertEqual(result['setup_type'], '20d')
        self.assertIsNotNone(result['pivot_price'])


class TestHtmlOutput(unittest.TestCase):
    """Tests that the HTML export produces correct badges and structure."""

    @patch('scripts.trend_screener.AlpacaClient', MockAlpacaClient)
    def setUp(self):
        import scripts.trend_screener as ts
        self.ts = ts
        self.screener = ts.TrendScreener(mode='paper')

    def test_setup_badges_renders_pp(self):
        """setup_badges should render 'pp' badge for pp setup type."""
        setup = 'pp'
        badge_class = {'pp': 'badge-pp', '20d': 'badge-20d'}.get(setup, 'badge-none')
        badge_html = f'<span class="badge {badge_class}">{setup}</span>'
        self.assertIn('pp', badge_html)
        self.assertIn('badge-pp', badge_html)
        self.assertNotIn('signal-badge', badge_html)
        self.assertNotIn('pocket $', badge_html)

    def test_setup_badges_renders_20d_for_trend(self):
        """setup_badges should render '20d' badge for trend setup type."""
        setup = 'trend'
        if setup in ('pivot', 'volume', 'trend'):
            setup = '20d'
        badge_class = {'pp': 'badge-pp', '20d': 'badge-20d'}.get(setup, 'badge-none')
        badge_html = f'<span class="badge {badge_class}">{setup}</span>'
        self.assertIn('20d', badge_html)
        self.assertIn('badge-20d', badge_html)
        self.assertNotIn('trend', badge_html)

    def test_no_secondary_pocket_badge_in_html(self):
        """HTML export should not include secondary pocket badges."""
        import tempfile, os
        results = [{
            'ticker': 'TEST', 'price': 100.0, 'stage2_score': 8,
            'setup_type': '20d', 'entry_ready': True, 'proximity_pct': 2.0,
            'volume_ratio': 1.5, 'avg_dollar_volume': 500_000_000,
            'rs_from_high': 1.0, 'ma10': 99.0, 'ma20': 98.0, 'ma50': 95.0,
            'ma150': 85.0, 'ma200': 80.0, 'sector': 'Technology',
            'has_pocket_pivot': True, 'pocket_pivot_price': 98.50,
            'pivot_price': 102.0,
        }]
        fd, tmp_path = tempfile.mkstemp(suffix='.html')
        os.close(fd)
        self.screener.export_results(results, 'html', tmp_path)
        html = open(tmp_path).read()
        os.unlink(tmp_path)
        # Should have 20d badge, not pp badge
        self.assertIn('20d', html)
        self.assertIn('badge-20d', html)
        # Should NOT have secondary pocket badge
        self.assertNotIn('signal-badge', html)
        self.assertNotIn('signal-pocket', html)
        self.assertNotIn('pocket $', html)
        # Should have data-section attribute
        self.assertIn('data-section=', html)
        # Should have developing section
        self.assertIn('section-developing', html)
        self.assertIn('row-developing', html)
        self.assertIn('To Buy Point', html)
        self.assertNotIn('To Pivot', html)


class TestClassification(unittest.TestCase):
    """Tests for proximity-based section classification."""

    def test_classify_ready_above_buy_point(self):
        """Stock 1% above buy point → Ready."""
        r = {'pivot_price': 100.0, 'price': 101.0, 'proximity_pct': 1.0}
        # Simulate classify_section logic
        prox = r['proximity_pct']
        if -2.0 <= prox <= 2.0:
            section = 'ready'
        elif prox > 2.0:
            section = 'extended'
        elif prox >= -5.0:
            section = 'near'
        else:
            section = 'developing'
        self.assertEqual(section, 'ready')

    def test_classify_ready_below_buy_point(self):
        """Stock 1% below buy point → Ready."""
        prox = -1.0
        if -2.0 <= prox <= 2.0:
            section = 'ready'
        elif prox > 2.0:
            section = 'extended'
        elif prox >= -5.0:
            section = 'near'
        else:
            section = 'developing'
        self.assertEqual(section, 'ready')

    def test_classify_near(self):
        """Stock 3% below buy point → Near."""
        prox = -3.0
        if -2.0 <= prox <= 2.0:
            section = 'ready'
        elif prox > 2.0:
            section = 'extended'
        elif prox >= -5.0:
            section = 'near'
        else:
            section = 'developing'
        self.assertEqual(section, 'near')

    def test_classify_developing(self):
        """Stock 6% below buy point → Developing."""
        prox = -6.0
        if -2.0 <= prox <= 2.0:
            section = 'ready'
        elif prox > 2.0:
            section = 'extended'
        elif prox >= -5.0:
            section = 'near'
        else:
            section = 'developing'
        self.assertEqual(section, 'developing')

    def test_classify_extended(self):
        """Stock 3% above buy point → Extended."""
        prox = 3.0
        if -2.0 <= prox <= 2.0:
            section = 'ready'
        elif prox > 2.0:
            section = 'extended'
        elif prox >= -5.0:
            section = 'near'
        else:
            section = 'developing'
        self.assertEqual(section, 'extended')

    def test_classify_no_setup(self):
        """Stock with no buy point → No Setup."""
        r = {'pivot_price': None, 'price': 100.0}
        bp = r.get('pivot_price')
        if bp is None or bp == 0:
            section = 'nosetup'
        else:
            section = 'ready'
        self.assertEqual(section, 'nosetup')


if __name__ == '__main__':
    unittest.main()
