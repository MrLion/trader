#!/usr/bin/env python3
"""Tests for report scripts.

Covers unit-testable functions in:
- scripts/deliver_report.py
- scripts/premarket_report.py
- scripts/postmarket_report.py
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pytest

# scripts/ is on sys.path via conftest.py
import deliver_report
import postmarket_report
import premarket_report


# =============================================================================
# deliver_report.py
# =============================================================================

class TestRetryDecorator:
    """Test retry exponential backoff decorator."""

    def test_succeeds_first_attempt(self):
        call_count = 0

        @deliver_report.retry(max_attempts=3, backoff=2)
        def flaky():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert flaky() == "ok"
        assert call_count == 1

    def test_retries_then_raises(self):
        call_count = 0

        @deliver_report.retry(max_attempts=3, backoff=2)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise deliver_report.Timeout("timeout")

        with pytest.raises(deliver_report.Timeout):
            always_fails()
        assert call_count == 3

    def test_does_not_retry_on_non_retryable_exception(self):
        call_count = 0

        @deliver_report.retry(max_attempts=3, backoff=2)
        def fails_valueerror():
            nonlocal call_count
            call_count += 1
            raise ValueError("nope")

        with pytest.raises(ValueError):
            fails_valueerror()
        assert call_count == 1


class TestTelegramReporter:
    """Test TelegramReporter."""

    def test_init_creates_base_url(self):
        r = deliver_report.TelegramReporter("token123", "-123")
        assert r.base_url == "https://api.telegram.org/bottoken123"
        assert r.chat_id == "-123"

    def test_init_raises_on_empty_token(self):
        with pytest.raises(ValueError, match="Bot token"):
            deliver_report.TelegramReporter("", "-123")

    def test_init_raises_on_empty_chat_id(self):
        with pytest.raises(ValueError, match="Chat ID"):
            deliver_report.TelegramReporter("token123", "")

    def test_send_document_dry_run(self, tmp_path):
        r = deliver_report.TelegramReporter("token", "-123")
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        result = r.send_document(f, caption="Test", dry_run=True)
        assert result["ok"] is True
        assert result["result"]["dry_run"] is True

    def test_send_document_success(self, tmp_path):
        r = deliver_report.TelegramReporter("token", "-123")
        f = tmp_path / "report.html"
        f.write_text("<html></html>")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

        with patch("deliver_report.requests.post", return_value=mock_response) as mock_post:
            result = r.send_document(f, caption="Test", dry_run=False)

        assert result["ok"] is True
        mock_post.assert_called_once()

    def test_send_document_file_not_found(self):
        r = deliver_report.TelegramReporter("token", "-123")
        with pytest.raises(FileNotFoundError):
            r.send_document(Path("/nonexistent/file.html"))

    def test_send_document_http_error_401(self, tmp_path):
        r = deliver_report.TelegramReporter("token", "-123")
        f = tmp_path / "report.html"
        f.write_text("<html></html>")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        error = deliver_report.HTTPError("401", response=mock_response)
        mock_response.raise_for_status.side_effect = error

        with patch("deliver_report.requests.post", return_value=mock_response):
            with pytest.raises(deliver_report.HTTPError):
                r.send_document(f, dry_run=False)


class TestValidateFile:
    """Test validate_file."""

    def test_valid_html_file(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        path = deliver_report.validate_file(str(f))
        assert path == f

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            deliver_report.validate_file(str(tmp_path / "missing.html"))

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Not a file"):
            deliver_report.validate_file(str(tmp_path))

    def test_non_html_warns(self, tmp_path):
        f = tmp_path / "report.txt"
        f.write_text("txt")
        with patch("deliver_report.logging.warning") as mock_warn:
            deliver_report.validate_file(str(f))
        mock_warn.assert_called_once()


class TestLoadConfig:
    """Test load_config."""

    def test_from_env(self):
        env = {"TELEGRAM_BOT_TOKEN": "tok123"}
        with patch.dict(os.environ, env, clear=True):
            cfg = deliver_report.load_config()
        assert cfg["bot_token"] == "tok123"
        assert cfg["chat_id"] == "-4872065090"

    def test_missing_token_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                deliver_report.load_config()

    def test_custom_chat_id(self):
        env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "-999"}
        with patch.dict(os.environ, env, clear=True):
            cfg = deliver_report.load_config()
        assert cfg["chat_id"] == "-999"


class TestDeliverReportMain:
    """Test main() exit codes."""

    def test_missing_file_exits_not_found(self):
        test_args = ["deliver_report.py", "--file", "/nonexistent.html"]
        with patch.object(sys, "argv", test_args):
            result = deliver_report.main()
        assert result == deliver_report.EXIT_FILE_NOT_FOUND

    def test_missing_token_exits_config_error(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        test_args = ["deliver_report.py", "--file", str(f)]
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", test_args):
                result = deliver_report.main()
        assert result == deliver_report.EXIT_CONFIG_ERROR

    def test_dry_run_success(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        test_args = ["deliver_report.py", "--file", str(f), "--dry-run"]
        env = {"TELEGRAM_BOT_TOKEN": "tok"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(sys, "argv", test_args):
                with patch("deliver_report.logging.basicConfig"):
                    result = deliver_report.main()
        assert result == deliver_report.EXIT_SUCCESS

    def test_verbose_sets_debug(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        test_args = ["deliver_report.py", "--file", str(f), "--dry-run", "--verbose"]
        env = {"TELEGRAM_BOT_TOKEN": "tok"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(sys, "argv", test_args):
                with patch("deliver_report.logging.basicConfig") as mock_log:
                    deliver_report.main()
        args, kwargs = mock_log.call_args
        assert kwargs["level"] == deliver_report.logging.DEBUG


# =============================================================================
# premarket_report.py
# =============================================================================

class TestFormatEarningsBadge:
    """Test _format_earnings_badge."""

    def test_none_returns_dash(self):
        assert premarket_report._format_earnings_badge(None) == "—"

    def test_zero_or_negative_returns_blocked(self):
        assert premarket_report._format_earnings_badge(0) == "⛔ today"
        assert premarket_report._format_earnings_badge(-1) == "⛔ today"

    def test_one_day_returns_alert(self):
        assert premarket_report._format_earnings_badge(1) == "🚨 1d"

    def test_within_week_returns_warning(self):
        assert premarket_report._format_earnings_badge(3) == "⚠️ 3d"
        assert premarket_report._format_earnings_badge(7) == "⚠️ 7d"

    def test_within_month_returns_calendar(self):
        assert premarket_report._format_earnings_badge(14) == "📅 14d"
        assert premarket_report._format_earnings_badge(30) == "📅 30d"

    def test_far_future_returns_dash(self):
        assert premarket_report._format_earnings_badge(31) == "—"


class TestPremarketHtmlReport:
    """Test generate_html_report in premarket_report.py."""

    def test_generates_html_with_sections(self, tmp_path):
        report_data = {
            "date": "2024-01-15",
            "regime": "🟢 BULL",
            "futures": [
                {"symbol": "/ES", "price": 4500.0, "change": 10.0, "pct": 0.22, "arrow": "↑"}
            ],
            "vix": {"price": 16.5, "change": -0.5, "level": "Low <18"},
            "crypto": {"btc_price": 42000, "btc_change": 100, "btc_pct": 0.24, "eth_price": 2500, "eth_change": 10, "eth_pct": 0.4},
            "regime_signals": [("SPY > 50MA", True), ("QQQ > 50MA", True), ("IWM > 50MA", False), ("VIX < 18", True)],
            "bullish_count": 3,
            "economic": {"events": [{"time": "08:30", "event": "CPI", "impact": "🔴"}], "risk_level": "🔴", "advice": "Reduce size"},
            "indices": [
                {"ticker": "SPY", "close": 450, "above_20": True, "above_50": True, "above_200": True}
            ],
            "sector_leaders": [
                {"overall_rank": 1, "ticker": "XLK", "name": "Technology", "ret_1w": 1.5, "ret_1m": 3.2, "ret_3m": 5.1, "ret_6m": 8.0, "stage2_score": 4}
            ],
            "watchlist": [
                {"ticker": "AAPL", "tier": "1", "entry_score": 65, "current": 185.0, "pivot": 190.0, "dist_to_pivot": 2.7, "risk_pct": 2.5, "stage2": 4, "ret_6m": 12.0, "sector": "Technology", "earnings_days": None}
            ],
            "ready_tickers": ["AAPL"],
            "action_items": [{"text": "Test action", "checked": False}],
            "earnings_today": [],
            "earnings_tomorrow": [],
            "earnings_7d": [],
            "verdict_action": "Execute best setups.",
        }
        output = tmp_path / "premarket.html"
        premarket_report.generate_html_report(report_data, output)
        html = output.read_text()
        assert "Pre-Market Report" in html
        assert "AAPL" in html
        assert "BULL" in html
        assert "CPI" in html
        assert "Technology" in html
        assert "Ready: AAPL" in html
        assert "Execute best setups." in html


class TestFetchEconomicCalendar:
    """Test fetch_economic_calendar with mocked EconomicCalendar."""

    def test_parses_usd_events(self):
        from traderlib.economic_calendar import EconomicEvent
        from datetime import datetime
        today_str = datetime.now().strftime('%Y-%m-%d')
        fake_event = EconomicEvent(
            date=today_str,
            time="08:30",
            country="US",
            event="CPI Report",
            impact="high",
            estimate="+0.3%",
            previous="+0.4%"
        )
        mock_cal = MagicMock()
        mock_cal.get_events.return_value = [fake_event]

        with patch("traderlib.economic_calendar.EconomicCalendar", return_value=mock_cal):
            result = premarket_report.fetch_economic_calendar()
        assert result["today"]
        assert any("CPI" in e.event for e in result["today"])

    def test_network_error_returns_empty(self):
        mock_cal = MagicMock()
        mock_cal.get_events.side_effect = Exception("network")

        with patch("traderlib.economic_calendar.EconomicCalendar", return_value=mock_cal):
            result = premarket_report.fetch_economic_calendar()
        assert result == {"today": [], "tomorrow": []}


# =============================================================================
# postmarket_report.py
# =============================================================================

class TestDetectGaps:
    """Test detect_gaps."""

    def test_detects_positive_gap(self):
        perf = [{"ticker": "AAPL", "change_pct": 5.0, "volume_ratio": 2.5}]
        gaps = postmarket_report.detect_gaps(perf)
        assert len(gaps) == 1
        assert gaps[0]["ticker"] == "AAPL"
        assert gaps[0]["gap_pct"] == 5.0

    def test_detects_negative_gap(self):
        perf = [{"ticker": "TSLA", "change_pct": -4.5, "volume_ratio": 1.8}]
        gaps = postmarket_report.detect_gaps(perf)
        assert len(gaps) == 1
        assert gaps[0]["gap_pct"] == -4.5

    def test_ignores_small_changes(self):
        perf = [{"ticker": "MSFT", "change_pct": 1.5, "volume_ratio": 1.0}]
        gaps = postmarket_report.detect_gaps(perf)
        assert len(gaps) == 0

    def test_empty_list(self):
        assert postmarket_report.detect_gaps([]) == []


class TestPostmarketHtmlReport:
    """Test generate_html_report in postmarket_report.py."""

    def test_generates_html_with_sections(self, tmp_path):
        report_data = {
            "date": "2024-01-15",
            "indices": [
                {"ticker": "SPY", "close": 450, "change": 5, "pct": 1.12, "high": 455, "low": 445, "above_20": True, "above_50": True, "above_200": True},
                {"ticker": "QQQ", "close": 350, "change": 3, "pct": 0.86, "high": 355, "low": 345, "above_20": True, "above_50": True, "above_200": True},
            ],
            "vix": {"price": 16.5, "change": -0.5, "level": "Low <18"},
            "crypto": {"btc_price": 42000, "btc_change": 100, "btc_pct": 0.24, "eth_price": 2500, "eth_change": 10, "eth_pct": 0.4},
            "watchlist_performance": [
                {"ticker": "AAPL", "change_pct": 2.5, "volume_ratio": 1.5, "close": 185, "pivot": 180, "dist_to_pivot": 2.8, "tier": "1"}
            ],
            "gaps": [{"ticker": "NVDA", "gap_pct": 5.2, "volume_ratio": 2.5, "reason": "Earnings/Move"}],
            "action_items": [{"text": "Review gaps", "checked": False}],
            "regime_signals": [("SPY > 50MA", True), ("QQQ > 50MA", True)],
            "bullish_count": 2,
        }
        output = tmp_path / "postmarket.html"
        postmarket_report.generate_html_report(report_data, output)
        html = output.read_text()
        assert "Post-Market Report" in html
        assert "AAPL" in html
        assert "NVDA" in html
        assert "BULL CLOSE" in html
        assert "Review gaps" in html
        assert "Gap Analysis" in html
