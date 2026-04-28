#!/usr/bin/env python3
"""Tests for mcstock_scraper.py.

Covers pure logic:
- get_credentials — env, .env file, missing
- login — mocked requests session
- fetch_report — mocked requests
- extract_tickers — fake HTML
- load_scraper_config — default, file, error
- save_to_csv — temp path
- main — argparse, dry-run
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import mcstock_scraper as mcs


class TestGetCredentials:
    """Test get_credentials."""

    def test_from_env_vars(self):
        env = {'MCSTOCK_USER': 'user123', 'MCSTOCK_PASS': 'pass456'}
        with patch.dict('os.environ', env, clear=True):
            user, pwd = mcs.get_credentials()
        assert user == 'user123'
        assert pwd == 'pass456'

    def test_from_env_file(self, tmp_path):
        env_path = tmp_path / '.env'
        env_path.write_text('MCSTOCK_USER=fileuser\nMCSTOCK_PASS=filepass\n')
        with patch.dict('os.environ', {}, clear=True):
            with patch.object(mcs, 'PROJECT_ROOT', tmp_path):
                user, pwd = mcs.get_credentials()
        assert user == 'fileuser'
        assert pwd == 'filepass'

    def test_missing_raises(self, tmp_path):
        with patch.dict('os.environ', {}, clear=True):
            with patch.object(mcs, 'PROJECT_ROOT', tmp_path):
                with pytest.raises(ValueError, match='credentials not found'):
                    mcs.get_credentials()


class TestLogin:
    """Test login with mocked session."""

    def test_success(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '<html></html>'
        mock_response.url = 'https://www.mcstockcharts.com/'
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response

        result = mcs.login(mock_session, 'user', 'pass')
        assert result is True

    def test_login_error_in_response(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '<div id="login_error">Invalid</div>'
        mock_response.url = 'https://www.mcstockcharts.com/wp-login.php'
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response

        result = mcs.login(mock_session, 'user', 'pass')
        assert result is False

    def test_timeout(self):
        mock_session = MagicMock()
        import requests
        mock_session.get.side_effect = requests.exceptions.Timeout()

        result = mcs.login(mock_session, 'user', 'pass')
        assert result is False


class TestFetchReport:
    """Test fetch_report."""

    def test_success(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '<html>report</html>'
        mock_response.url = 'https://www.mcstockcharts.com/latest-report/'
        mock_session.get.return_value = mock_response

        html = mcs.fetch_report(mock_session)
        assert 'report' in html

    def test_404_raises(self):
        mock_session = MagicMock()
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_session.get.return_value = mock_response

        with pytest.raises(FileNotFoundError):
            mcs.fetch_report(mock_session, date='2026-04-01')

    def test_redirect_to_login_raises(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ''
        mock_response.url = 'https://www.mcstockcharts.com/wp-login.php'
        mock_session.get.return_value = mock_response

        with pytest.raises(PermissionError):
            mcs.fetch_report(mock_session)


class TestExtractTickers:
    """Test extract_tickers with fake HTML."""

    def test_extracts_ready_list(self):
        html = """
        <html><body>
        <p>THIS WEEKS READY LIST</p>
        <p>ACLS        $96.78</p>
        <p>AROC        $34.77</p>
        <p>WATCH LIST</p>
        </body></html>
        """
        ideas = mcs.extract_tickers(html)
        tickers = [i['Ticker'] for i in ideas]
        assert 'ACLS' in tickers
        assert 'AROC' in tickers

    def test_extracts_watch_list(self):
        html = """
        <html><body>
        <p>WATCH LIST</p>
        <p>NVDA        $420.00</p>
        <p>MORNING POST</p>
        </body></html>
        """
        ideas = mcs.extract_tickers(html)
        tickers = [i['Ticker'] for i in ideas]
        assert 'NVDA' in tickers

    def test_filters_false_positives(self):
        html = """
        <html><body>
        <p>THIS WEEKS READY LIST</p>
        <p>THE         $1.00</p>
        <p>AND         $2.00</p>
        <p>AAPL        $150.00</p>
        <p>WATCH LIST</p>
        </body></html>
        """
        ideas = mcs.extract_tickers(html)
        tickers = [i['Ticker'] for i in ideas]
        assert 'AAPL' in tickers
        assert 'THE' not in tickers
        assert 'AND' not in tickers

    def test_extra_false_positives_from_config(self):
        html = """
        <html><body>
        <p>THIS WEEKS READY LIST</p>
        <p>FOO         $1.00</p>
        <p>WATCH LIST</p>
        </body></html>
        """
        ideas = mcs.extract_tickers(html, config={'extra_false_positives': ['FOO']})
        tickers = [i['Ticker'] for i in ideas]
        assert 'FOO' not in tickers

    def test_empty_html(self):
        ideas = mcs.extract_tickers('<html></html>')
        assert ideas == []


class TestLoadScraperConfig:
    """Test load_scraper_config."""

    def test_default_when_no_file(self, tmp_path):
        with patch.object(mcs, 'PROJECT_ROOT', tmp_path):
            cfg = mcs.load_scraper_config()
        assert cfg['validation']['min_price'] == 10
        assert cfg['extra_false_positives'] == []

    def test_loads_yaml(self, tmp_path):
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        (config_dir / 'screener_config.yaml').write_text(
            'validation:\n  min_price: 20\nextra_false_positives:\n  - FOO\n'
        )
        with patch.object(mcs, 'PROJECT_ROOT', tmp_path):
            cfg = mcs.load_scraper_config()
        assert cfg['validation']['min_price'] == 20
        assert 'FOO' in cfg['extra_false_positives']

    def test_fallback_on_invalid_yaml(self, tmp_path):
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        (config_dir / 'screener_config.yaml').write_text('not: yaml: [')
        with patch.object(mcs, 'PROJECT_ROOT', tmp_path):
            cfg = mcs.load_scraper_config()
        assert cfg['validation']['min_price'] == 10


class TestSaveToCsv:
    """Test save_to_csv."""

    def test_saves_ideas(self, tmp_path):
        ideas = [{'Ticker': 'AAPL', 'Name': 'Apple'}, {'Ticker': 'MSFT', 'Name': 'Microsoft'}]
        path = mcs.save_to_csv(ideas, str(tmp_path / 'out.csv'))
        assert path.exists()
        text = path.read_text()
        assert 'Ticker' in text
        assert 'AAPL' in text
        assert 'MSFT' in text

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match='No ideas'):
            mcs.save_to_csv([])


class TestMain:
    """Test main() entry point."""

    def test_dry_run_exits_success(self):
        test_args = ['mcstock_scraper.py', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            with patch.object(mcs, 'get_credentials', return_value=('u', 'p')):
                with patch.object(mcs, 'login', return_value=True):
                    with patch.object(mcs, 'fetch_report', return_value='<html></html>'):
                        with pytest.raises(SystemExit) as exc:
                            mcs.main()
        assert exc.value.code == mcs.EXIT_SUCCESS

    def test_missing_credentials_exits_config_error(self):
        test_args = ['mcstock_scraper.py']
        with patch.object(sys, 'argv', test_args):
            with patch.object(mcs, 'get_credentials', side_effect=ValueError('missing')):
                with pytest.raises(SystemExit) as exc:
                    mcs.main()
        assert exc.value.code == mcs.EXIT_CONFIG_ERROR

    def test_login_failure_exits_auth_failed(self):
        test_args = ['mcstock_scraper.py']
        with patch.object(sys, 'argv', test_args):
            with patch.object(mcs, 'get_credentials', return_value=('u', 'p')):
                with patch.object(mcs, 'login', return_value=False):
                    with pytest.raises(SystemExit) as exc:
                        mcs.main()
        assert exc.value.code == mcs.EXIT_AUTH_FAILED


class TestGenerateTradingDates:
    """Test generate_trading_dates."""

    def test_weekdays_only(self):
        dates = mcs.generate_trading_dates('2026-04-06', '2026-04-10')
        assert len(dates) == 5
        for d in dates:
            assert d.weekday() < 5

    def test_skips_weekends(self):
        dates = mcs.generate_trading_dates('2026-04-10', '2026-04-13')
        assert len(dates) == 2
        assert dates[0].weekday() == 4
        assert dates[1].weekday() == 0


class TestBuildHistoricalUrl:
    """Test build_historical_url."""

    def test_url_format(self):
        from datetime import date as dt
        test_date = dt(2026, 4, 9)
        url = mcs.build_historical_url(test_date)
        assert 'mcstockcharts.com' in url
        assert 'pre-market-report' in url
        assert 'thursday' in url.lower()


class TestGetMondayDate:
    """Test get_monday_date."""

    def test_wednesday_returns_monday(self):
        from datetime import date as dt
        wed = dt(2026, 4, 9)
        monday = mcs.get_monday_date(wed)
        assert monday == '2026-04-06'
