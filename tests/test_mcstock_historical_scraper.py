#!/usr/bin/env python3
"""Tests for mcstock_historical_scraper.py.

Covers pure logic:
- generate_trading_dates — date range, weekends skipped
- build_report_url — URL format
- get_monday_date — Monday calculation
- extract_tickers_from_report — fake HTML
- save_to_csv — sample data
- get_credentials / login — same patterns as mcstock_scraper
- main — argparse paths
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import mcstock_historical_scraper as mch


class TestGenerateTradingDates:
    """Test generate_trading_dates."""

    def test_generates_mon_fri(self):
        dates = mch.generate_trading_dates('2026-04-06', '2026-04-10')
        assert len(dates) == 5
        assert dates[0] == date(2026, 4, 6)
        assert dates[-1] == date(2026, 4, 10)

    def test_skips_weekends(self):
        dates = mch.generate_trading_dates('2026-04-04', '2026-04-12')
        weekdays = [d for d in dates if d.weekday() < 5]
        assert len(weekdays) == 5  # Mon-Fri of that week
        assert date(2026, 4, 11) not in dates  # Saturday
        assert date(2026, 4, 12) not in dates  # Sunday

    def test_defaults_when_none(self):
        dates = mch.generate_trading_dates(None, None)
        assert len(dates) > 0
        assert all(d.weekday() < 5 for d in dates)


class TestBuildReportUrl:
    """Test build_report_url."""

    def test_url_format(self):
        d = date(2026, 4, 21)
        url = mch.build_report_url(d)
        assert url == 'https://www.mcstockcharts.com/members/pre-market-report-tuesday-april-21-2026-900a-m-est/'


class TestGetMondayDate:
    """Test get_monday_date."""

    def test_monday_returns_same(self):
        d = date(2026, 4, 6)  # Monday
        assert mch.get_monday_date(d) == '2026-04-06'

    def test_friday_returns_monday(self):
        d = date(2026, 4, 10)  # Friday
        assert mch.get_monday_date(d) == '2026-04-06'

    def test_sunday_returns_monday(self):
        d = date(2026, 4, 12)  # Sunday
        assert mch.get_monday_date(d) == '2026-04-06'


class TestExtractTickersFromReport:
    """Test extract_tickers_from_report with fake HTML."""

    def test_extracts_ready_and_watch(self):
        html = """
        <html><body>
        <p>THIS WEEKS READY LIST</p>
        <p>ACLS        $96.78</p>
        <p>WATCH LIST</p>
        <p>NVDA        $420.00</p>
        <p>MORNING POST</p>
        </body></html>
        """
        tickers = mch.extract_tickers_from_report(html)
        assert ('ACLS', 'ready') in tickers
        assert ('NVDA', 'watch') in tickers

    def test_filters_false_positives(self):
        html = """
        <html><body>
        <p>THIS WEEKS READY LIST</p>
        <p>THE         $1.00</p>
        <p>AAPL        $150.00</p>
        <p>WATCH LIST</p>
        </body></html>
        """
        tickers = mch.extract_tickers_from_report(html)
        symbols = [t for t, _ in tickers]
        assert 'AAPL' in symbols
        assert 'THE' not in symbols

    def test_empty_html(self):
        tickers = mch.extract_tickers_from_report('<html></html>')
        assert tickers == []


class TestSaveToCsv:
    """Test save_to_csv."""

    def test_saves_weekly_data(self, tmp_path):
        data = {
            '2026-04-06': {
                'AAPL': ('ready', '2026-04-06'),
                'MSFT': ('watch', '2026-04-07'),
            }
        }
        path = mch.save_to_csv(data, str(tmp_path / 'out.csv'), '2026-04-21')
        assert path.exists()
        text = path.read_text()
        assert 'AAPL' in text
        assert 'MSFT' in text
        assert 'ready' in text
        assert 'watch' in text


class TestGetCredentials:
    """Test get_credentials (duplicated from mcstock_scraper)."""

    def test_from_env(self):
        env = {'MCSTOCK_USER': 'u', 'MCSTOCK_PASS': 'p'}
        with patch.dict('os.environ', env, clear=True):
            user, pwd = mch.get_credentials()
        assert user == 'u'

    def test_missing_raises(self, tmp_path):
        with patch.dict('os.environ', {}, clear=True):
            with patch.object(mch, 'PROJECT_ROOT', tmp_path):
                with pytest.raises(ValueError):
                    mch.get_credentials()


class TestLogin:
    """Test login."""

    def test_success(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '<html></html>'
        mock_response.url = 'https://www.mcstockcharts.com/'
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response
        assert mch.login(mock_session, 'u', 'p') is True

    def test_failure(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = 'login_error'
        mock_response.url = 'https://www.mcstockcharts.com/wp-login.php'
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response
        assert mch.login(mock_session, 'u', 'p') is False


class TestMain:
    """Test main entry point."""

    def test_missing_credentials_exits_config_error(self):
        test_args = ['mcstock_historical_scraper.py']
        with patch.object(sys, 'argv', test_args):
            with patch.object(mch, 'get_credentials', side_effect=ValueError('missing')):
                with pytest.raises(SystemExit) as exc:
                    mch.main()
        assert exc.value.code == mch.EXIT_CONFIG_ERROR

    def test_login_failure_exits_auth_failed(self):
        test_args = ['mcstock_historical_scraper.py']
        with patch.object(sys, 'argv', test_args):
            with patch.object(mch, 'get_credentials', return_value=('u', 'p')):
                with patch.object(mch, 'login', return_value=False):
                    with pytest.raises(SystemExit) as exc:
                        mch.main()
        assert exc.value.code == mch.EXIT_AUTH_FAILED
