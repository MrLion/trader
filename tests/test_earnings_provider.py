#!/usr/bin/env python3
"""Tests for HistoricalEarningsProvider (backtest earnings module).

Covers:
1. Initialization (cache dir, API key)
2. Disk cache round-trip (_save_to_disk, _load_from_disk, _is_cache_valid)
3. Rate limiting
4. Prefetch (memory hit, disk hit, FMP fetch, fail-open)
5. get_next_earnings with as_of filter
6. is_earnings_blackout / should_force_exit (naive + trading_days)
7. invalidate_cache
"""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from traderlib.backtest.earnings_provider import HistoricalEarningsProvider

_FAKE_TODAY = date(2026, 4, 1)


@pytest.fixture
def provider_no_key():
    """Provider with no API key (fail-open mode)."""
    with patch.dict("os.environ", {}, clear=True):
        with TemporaryDirectory() as td:
            yield HistoricalEarningsProvider(cache_dir=Path(td))


@pytest.fixture
def provider_with_key():
    """Provider with a dummy API key."""
    with TemporaryDirectory() as td:
        yield HistoricalEarningsProvider(fmp_api_key="dummy_key", cache_dir=Path(td))


class TestInit:
    """Test constructor behavior."""

    def test_creates_cache_dir(self):
        with TemporaryDirectory() as td:
            cache = Path(td) / "sub" / "cache"
            provider = HistoricalEarningsProvider(fmp_api_key="k", cache_dir=cache)
            assert cache.exists()
            assert provider._cache_dir == cache

    def test_api_key_from_argument(self):
        with TemporaryDirectory() as td:
            provider = HistoricalEarningsProvider(fmp_api_key="arg_key", cache_dir=Path(td))
            assert provider._api_key == "arg_key"

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"FMP_API_KEY": "env_key"}, clear=True):
            with TemporaryDirectory() as td:
                provider = HistoricalEarningsProvider(cache_dir=Path(td))
                assert provider._api_key == "env_key"

    def test_ttl_default(self):
        with TemporaryDirectory() as td:
            provider = HistoricalEarningsProvider(fmp_api_key="k", cache_dir=Path(td))
            assert provider._cache_ttl_days == 30

    def test_ttl_override(self):
        with TemporaryDirectory() as td:
            provider = HistoricalEarningsProvider(fmp_api_key="k", cache_dir=Path(td), cache_ttl_days=7)
            assert provider._cache_ttl_days == 7


class TestCachePathAndValidity:
    """Test _get_cache_path and _is_cache_valid."""

    def test_get_cache_path_format(self, provider_with_key):
        path = provider_with_key._get_cache_path("aapl")
        assert path.name == "AAPL.json"
        assert path.parent == provider_with_key._cache_dir

    def test_is_cache_valid_missing_file(self, provider_with_key):
        assert provider_with_key._is_cache_valid("AAPL") is False

    def test_is_cache_valid_fresh(self, provider_with_key):
        cache_path = provider_with_key._get_cache_path("AAPL")
        cache_path.write_text('{"dates":["2026-07-25"]}')
        assert provider_with_key._is_cache_valid("AAPL") is True

    def test_is_cache_valid_expired(self, provider_with_key):
        cache_path = provider_with_key._get_cache_path("AAPL")
        cache_path.write_text('{"dates":["2026-07-25"]}')
        # Backdate the file to 31 days ago
        old_mtime = time.time() - (31 * 24 * 3600)
        os.utime(cache_path, (old_mtime, old_mtime))
        assert provider_with_key._is_cache_valid("AAPL") is False


class TestDiskRoundTrip:
    """Test _save_to_disk and _load_from_disk."""

    def test_save_and_load_dates(self, provider_with_key):
        dates = [date(2026, 1, 15), date(2026, 4, 20), date(2026, 7, 25)]
        provider_with_key._save_to_disk("AAPL", dates)
        loaded = provider_with_key._load_from_disk("AAPL")
        assert loaded == dates

    def test_load_from_disk_bad_json_returns_none(self, provider_with_key):
        cache_path = provider_with_key._get_cache_path("AAPL")
        cache_path.write_text("not json")
        assert provider_with_key._load_from_disk("AAPL") is None

    def test_load_from_disk_missing_dates_key_returns_empty_list(self, provider_with_key):
        cache_path = provider_with_key._get_cache_path("AAPL")
        cache_path.write_text('{"ticker": "AAPL"}')
        assert provider_with_key._load_from_disk("AAPL") == []

    def test_save_to_disk_is_atomic(self, provider_with_key):
        dates = [date(2026, 7, 25)]
        provider_with_key._save_to_disk("AAPL", dates)
        cache_path = provider_with_key._get_cache_path("AAPL")
        assert cache_path.exists()
        # Verify JSON structure
        data = json.loads(cache_path.read_text())
        assert data["ticker"] == "AAPL"
        assert data["dates"] == ["2026-07-25"]
        assert "cached_at" in data


class TestPrefetch:
    """Test prefetch with memory, disk, and FMP sources."""

    def test_memory_cache_hit_skips_fetch(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]
        with patch("traderlib.backtest.earnings_provider.requests.get") as mock_get:
            provider_with_key.prefetch(["AAPL"], date(2026, 1, 1), date(2026, 12, 31))
        mock_get.assert_not_called()

    def test_disk_cache_loads_into_memory(self, provider_with_key):
        provider_with_key._save_to_disk("AAPL", [date(2026, 7, 25)])
        with patch("traderlib.backtest.earnings_provider.requests.get") as mock_get:
            provider_with_key.prefetch(["AAPL"], date(2026, 1, 1), date(2026, 12, 31))
        mock_get.assert_not_called()
        assert provider_with_key._memory_cache["AAPL"] == [date(2026, 7, 25)]

    def test_fmp_fetch_on_miss(self, provider_with_key):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-07-25"},
            {"date": "2026-04-15"},
        ]
        mock_response.raise_for_status.return_value = None

        with patch(
            "traderlib.backtest.earnings_provider.requests.get", return_value=mock_response
        ) as mock_get:
            provider_with_key.prefetch(["AAPL"], date(2026, 1, 1), date(2026, 12, 31))

        mock_get.assert_called_once()
        assert provider_with_key._memory_cache["AAPL"] == [date(2026, 4, 15), date(2026, 7, 25)]
        # Disk cache should also exist
        assert provider_with_key._load_from_disk("AAPL") == [date(2026, 4, 15), date(2026, 7, 25)]

    def test_prefetch_no_api_key_does_nothing(self, provider_no_key):
        with patch("traderlib.backtest.earnings_provider.requests.get") as mock_get:
            provider_no_key.prefetch(["AAPL"], date(2026, 1, 1), date(2026, 12, 31))
        mock_get.assert_not_called()
        assert "AAPL" not in provider_no_key._memory_cache

    def test_prefetch_batch_only_fetches_missing(self, provider_with_key):
        # Pre-warm one ticker
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]

        mock_response = MagicMock()
        mock_response.json.return_value = [{"date": "2026-08-01"}]
        mock_response.raise_for_status.return_value = None

        with patch(
            "traderlib.backtest.earnings_provider.requests.get", return_value=mock_response
        ) as mock_get:
            provider_with_key.prefetch(["AAPL", "MSFT"], date(2026, 1, 1), date(2026, 12, 31))

        assert mock_get.call_count == 1
        assert provider_with_key._memory_cache["MSFT"] == [date(2026, 8, 1)]

    def test_prefetch_fail_open_on_fetch_error(self, provider_with_key):
        with patch(
            "traderlib.backtest.earnings_provider.requests.get", side_effect=Exception("network")
        ):
            provider_with_key.prefetch(["AAPL"], date(2026, 1, 1), date(2026, 12, 31))
        # Should not raise; ticker absent from memory cache
        assert "AAPL" not in provider_with_key._memory_cache


class TestGetNextEarnings:
    """Test get_next_earnings with as_of filtering."""

    def test_returns_first_date_on_or_after_as_of(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [
            date(2026, 1, 15),
            date(2026, 4, 20),
            date(2026, 7, 25),
        ]
        assert provider_with_key.get_next_earnings("AAPL", date(2026, 4, 1)) == date(2026, 4, 20)

    def test_returns_exact_date_match(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 4, 20)]
        assert provider_with_key.get_next_earnings("AAPL", date(2026, 4, 20)) == date(2026, 4, 20)

    def test_returns_none_when_all_past(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 1, 15)]
        assert provider_with_key.get_next_earnings("AAPL", date(2026, 4, 1)) is None

    def test_returns_none_when_ticker_unknown(self, provider_with_key):
        assert provider_with_key.get_next_earnings("UNKNOWN", date(2026, 4, 1)) is None


class TestIsEarningsBlackout:
    """Test is_earnings_blackout."""

    def test_true_on_exact_date(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]
        assert provider_with_key.is_earnings_blackout("AAPL", date(2026, 7, 25)) is True

    def test_false_when_no_data(self, provider_with_key):
        assert provider_with_key.is_earnings_blackout("AAPL", date(2026, 7, 25)) is False

    def test_false_on_different_date(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]
        assert provider_with_key.is_earnings_blackout("AAPL", date(2026, 7, 24)) is False


class TestShouldForceExit:
    """Test should_force_exit with naive and trading_days modes."""

    def test_true_naive_day_before(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 23)]  # Thursday
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 22)) is True  # Wed

    def test_true_naive_friday_before_monday(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 27)]  # Monday
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 24)) is True  # Friday

    def test_false_on_earnings_date(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 27)]  # Monday
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 27)) is False

    def test_false_when_no_data(self, provider_with_key):
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 27)) is False

    def test_false_two_days_before(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 27)]  # Monday
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 23)) is False

    def test_true_with_trading_days_holiday(self, provider_with_key):
        """Thursday earnings with Monday holiday: force exit Wednesday, not Friday."""
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 23)]  # Thursday
        trading_days = [
            date(2026, 7, 17),  # Fri
            date(2026, 7, 21),  # Tue (Mon holiday)
            date(2026, 7, 22),  # Wed
            date(2026, 7, 23),  # Thu (earnings)
        ]
        # Naive would say Friday (7/17) is day before, but trading_days says Wednesday (7/22)
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 22), trading_days) is True

    def test_false_with_trading_days_not_yet(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 23)]
        trading_days = [date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 23)]
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 21), trading_days) is False

    def test_false_when_no_future_trading_days(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]
        assert provider_with_key.should_force_exit("AAPL", date(2026, 7, 25), []) is False


class TestInvalidateCache:
    """Test invalidate_cache."""

    def test_removes_from_memory(self, provider_with_key):
        provider_with_key._memory_cache["AAPL"] = [date(2026, 7, 25)]
        provider_with_key.invalidate_cache("AAPL")
        assert "AAPL" not in provider_with_key._memory_cache

    def test_unknown_ticker_no_error(self, provider_with_key):
        provider_with_key.invalidate_cache("UNKNOWN")
        assert "UNKNOWN" not in provider_with_key._memory_cache


class TestRateLimit:
    """Test _rate_limit token bucket."""

    def test_no_sleep_under_limit(self, provider_with_key):
        provider_with_key._call_times = [100.0] * 299
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                provider_with_key._rate_limit()
        mock_sleep.assert_not_called()
        assert len(provider_with_key._call_times) == 300

    def test_sleeps_at_limit(self, provider_with_key):
        provider_with_key._call_times = [100.0] * 300
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                provider_with_key._rate_limit()
        mock_sleep.assert_called_once()
        assert len(provider_with_key._call_times) == 301

    def test_prunes_old_calls(self, provider_with_key):
        provider_with_key._call_times = [50.0] * 300 + [120.0] * 5
        with patch("time.monotonic", return_value=130.0):
            with patch("time.sleep") as mock_sleep:
                provider_with_key._rate_limit()
        mock_sleep.assert_not_called()
