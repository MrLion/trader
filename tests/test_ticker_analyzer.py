#!/usr/bin/env python3
"""Tests for TickerAnalyzer module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import pytz

from traderlib.ticker_analyzer import TickerAnalyzer, TickerAnalysis
from traderlib.pivot_detection import PivotSignal
from traderlib.risk_config import RiskConfigManager


@pytest.fixture
def mock_alpaca():
    """Fixture for mocked Alpaca client."""
    mock = Mock()
    return mock


@pytest.fixture
def risk_config():
    """Fixture for default risk config."""
    manager = RiskConfigManager()
    return manager.get_config()


@pytest.fixture
def analyzer(mock_alpaca, risk_config):
    """Fixture for TickerAnalyzer with mocked dependencies."""
    return TickerAnalyzer(mock_alpaca, risk_config, watchlist_path=None)


class TestInitialization:
    """Test TickerAnalyzer initialization."""

    def test_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert analyzer.spy_cache == {'date': None, 'return_6m': 0.0, 'price': None}


class TestGetSPYReturn:
    """Test _get_spy_return_6m method."""

    def test_spy_cache_hit(self, analyzer):
        """Test that cached value is returned on same day."""
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
        analyzer.spy_cache = {'date': today, 'return_6m': 15.5, 'price': 450.0}

        result = analyzer._get_spy_return_6m()

        assert result == 15.5

    def test_spy_cache_miss_fetches_data(self, analyzer, mock_alpaca):
        """Test that data is fetched when cache is empty."""
        hist_data = pd.DataFrame({
            'Close': [400.0] * 130 + [450.0]
        })
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = analyzer._get_spy_return_6m()

        expected_return = ((450.0 / 400.0) - 1) * 100
        assert abs(result - expected_return) < 0.01
        mock_alpaca.get_historical_bars.assert_called_once_with('SPY')
        assert analyzer.spy_cache['return_6m'] == result

    def test_spy_insufficient_data_returns_zero(self, analyzer, mock_alpaca):
        """Test that zero is returned when insufficient data."""
        hist_data = pd.DataFrame({'Close': [450.0] * 50})
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = analyzer._get_spy_return_6m()

        assert result == 0.0

    def test_spy_exception_returns_zero(self, analyzer, mock_alpaca):
        """Test that zero is returned on exception."""
        mock_alpaca.get_historical_bars.side_effect = Exception('API error')

        result = analyzer._get_spy_return_6m()

        assert result == 0.0


class TestGetCurrentPrice:
    """Test _get_current_price method."""

    def test_get_price_from_quote(self, analyzer, mock_alpaca):
        """Test price fetched from get_latest_price."""
        mock_alpaca.get_latest_price.return_value = 150.0

        result = analyzer._get_current_price('AAPL')

        assert result == 150.0

    def test_get_price_from_close(self, analyzer, mock_alpaca):
        """Test fallback to historical bars when get_latest_price returns None."""
        mock_alpaca.get_latest_price.return_value = None
        hist_data = pd.DataFrame({'Close': [145.0, 146.0, 149.5]})
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = analyzer._get_current_price('AAPL')

        assert result == 149.5

    def test_get_price_returns_none_when_all_fail(self, analyzer, mock_alpaca):
        """Test None returned when all price sources fail."""
        mock_alpaca.get_latest_price.return_value = None
        mock_alpaca.get_historical_bars.return_value = None

        result = analyzer._get_current_price('AAPL')

        assert result is None


class TestCheckMarketConditions:
    """Test check_market_conditions method."""

    def test_market_ok_when_spy_flat(self, analyzer, mock_alpaca):
        """Test market OK when SPY is flat."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [450.0, 450.0]})

        result, msg, _ = analyzer.check_market_conditions()

        assert result is True
        assert '0.00%' in msg

    def test_market_blocked_when_spy_declines(self, analyzer, mock_alpaca):
        """Test market blocked when SPY declines below threshold."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [450.0, 440.0]})

        result, msg, _ = analyzer.check_market_conditions()

        assert result is False
        assert '-2.22%' in msg

    def test_market_ok_when_no_spy_price(self, analyzer, mock_alpaca):
        """Test market OK when SPY history unavailable (fewer than 2 rows)."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': []})

        result, msg, _ = analyzer.check_market_conditions()

        assert result is True
        assert 'SPY' in msg


class TestAnalyze:
    """Test analyze method."""

    def test_analyze_insufficient_data_returns_none(self, analyzer, mock_alpaca):
        """Test None returned when insufficient historical data."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [100.0] * 10})

        result = analyzer.analyze('AAPL')

        assert result is None

    def test_analyze_no_price_returns_none(self, analyzer):
        """Test None returned when price unavailable."""
        analyzer._get_current_price = Mock(return_value=None)

        result = analyzer.analyze('AAPL')

        assert result is None

    @patch('traderlib.ticker_analyzer.calculate_ma_support_stop')
    @patch('traderlib.ticker_analyzer.get_stage2_details')
    @patch('traderlib.ticker_analyzer.get_entry_score')
    def test_analyze_valid_ticker(self, mock_get_entry_score, mock_stage2, mock_ma_stop, analyzer, mock_alpaca):
        """Test analysis of valid ticker."""
        hist_data = pd.DataFrame({
            'Close': [100.0 + i * 0.5 for i in range(130)] + [150.0],
            'High': [101.0 + i * 0.5 for i in range(130)] + [151.0],
            'Low': [99.0 + i * 0.5 for i in range(130)] + [149.0],
            'Volume': [1000000] * 131
        })
        mock_alpaca.get_historical_bars.return_value = hist_data

        mock_stage2.return_value = {'score': 8, 'criteria': {'price_above_50ma': True, 'price_above_20ma': True}}
        mock_ma_stop.return_value = None
        mock_get_entry_score.return_value = 85

        analyzer._get_current_price = Mock(return_value=150.0)
        analyzer._get_spy_return_6m = Mock(return_value=15.0)

        result = analyzer.analyze('AAPL')

        assert result is not None
        assert result.ticker == 'AAPL'
        assert result.current == 150.0
        assert result.entry_score == 85

    @patch('traderlib.ticker_analyzer.detect_pivot')
    @patch('traderlib.ticker_analyzer.calculate_ma_support_stop')
    @patch('traderlib.ticker_analyzer.get_stage2_details')
    @patch('traderlib.ticker_analyzer.get_entry_score')
    def test_analyze_technique_stop_override(self, mock_get_entry_score, mock_stage2,
                                              mock_ma_stop, mock_detect_pivot,
                                              analyzer, mock_alpaca):
        """Test that a tighter detected technique stop overrides ATR stop."""
        hist_data = pd.DataFrame({
            'Close': [100.0 + i * 0.5 for i in range(130)] + [150.0],
            'High': [101.0 + i * 0.5 for i in range(130)] + [151.0],
            'Low': [99.0 + i * 0.5 for i in range(130)] + [149.0],
            'Volume': [1000000] * 131
        })
        mock_alpaca.get_historical_bars.return_value = hist_data

        mock_stage2.return_value = {'score': 8, 'criteria': {'price_above_50ma': True, 'price_above_20ma': True}}
        mock_ma_stop.return_value = None
        mock_get_entry_score.return_value = 85

        # recent_low from synthetic data is 149.0; technique stop at 149.5 is tighter
        mock_detect_pivot.return_value = PivotSignal(
            ticker='AAPL',
            pivot_price=152.0,
            pivot_type='vcp',
            confidence=0.85,
            stop_price=149.5,
            target_price=155.0,
            entry_mode='breakout',
            context={'num_contractions': 3}
        )

        # Widen bounds so the technique stop (148.5) isn't clipped by max_stop
        analyzer.risk_config.stop_loss.max_stop_distance_pct = 0.5
        analyzer.risk_config.stop_loss.min_stop_distance_pct = 0.0

        analyzer._get_current_price = Mock(return_value=150.0)
        analyzer._get_spy_return_6m = Mock(return_value=15.0)

        result = analyzer.analyze('AAPL', technique='vcp')

        assert result is not None
        assert result.stop == 149.5
        assert result.stop_type == 'VCP'
        assert result.pivot_type == 'vcp'
        assert result.entry_mode == 'breakout'


class TestTickerAnalysis:
    """Test TickerAnalysis dataclass."""

    def test_to_dict_returns_all_fields(self):
        """Test to_dict includes all expected fields."""
        analysis = TickerAnalysis(
            ticker='AAPL',
            current=150.0,
            stage2=8,
            entry_score=85,
            tier='Tier 1',
            pivot=150.0,
            pivot_source='manual',
            dist_to_pivot=0.0,
            stop=142.5,
            target=165.0,
            sector='Tech',
            risk_pct=5.0,
        )
        d = analysis.to_dict()
        assert d['ticker'] == 'AAPL'
        assert d['current'] == 150.0
        assert d['stage2'] == 8
        assert d['entry_score'] == 85
        assert d['tier'] == 'Tier 1'
        assert d['pivot'] == 150.0
        assert d['pivot_source'] == 'manual'
