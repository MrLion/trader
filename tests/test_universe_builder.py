#!/usr/bin/env python3
"""Tests for universe_builder module.

Covers:
1. Config loading (success, missing file, fallback defaults)
2. Cache path generation
3. Cache load/save (valid, expired, corrupted, atomic write)
4. Asset fetching with mocked Alpaca
5. Full build_universe pipeline with mocked prices and dollar volumes
6. ETF detection, exchange exclusion, marginable filtering
7. Profile resolution helpers
8. Sector enrichment via FMP
"""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from traderlib.universe_builder import UniverseBuilder, UniverseResult


def _make_asset(symbol, name="", tradable=True, exchange="NASDAQ", marginable=True):
    """Helper to create a mock asset object."""
    a = Mock()
    a.symbol = symbol
    a.name = name
    a.tradable = tradable
    a.exchange = exchange
    a.marginable = marginable
    return a


@pytest.fixture
def mock_alpaca():
    """Patch AlpacaClient inside universe_builder to avoid real API calls."""
    with patch("traderlib.universe_builder.AlpacaClient") as mock_cls:
        mock_instance = Mock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def builder(tmp_path, mock_alpaca):
    """UniverseBuilder with a temp config dir, mocked Alpaca, and isolated cache."""
    config_path = tmp_path / "screener_config.yaml"
    config_path.write_text("""
universes:
  default: large_cap
  large_cap:
    min_price: 10
    min_dollar_volume: 80000000
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
  high_octane:
    min_price: 2
    min_dollar_volume: 20000000
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
""")
    b = UniverseBuilder(config_path=config_path)
    # Isolate cache to temp dir so tests don't pollute data/universes
    b.UNIVERSES_DIR = tmp_path / "universes"
    b.UNIVERSES_DIR.mkdir(parents=True, exist_ok=True)
    return b


class TestInit:
    """Test constructor behavior."""

    def test_loads_config_from_path(self, builder):
        assert builder.config["default"] == "large_cap"
        assert builder.config["large_cap"]["min_price"] == 10

    def test_creates_cache_dir(self, builder):
        assert builder.UNIVERSES_DIR.exists()

    def test_has_alpaca_client(self, builder):
        assert builder.alpaca is not None


class TestLoadConfig:
    """Test _load_config edge cases."""

    def test_missing_file_uses_defaults(self, tmp_path, mock_alpaca):
        missing_config = tmp_path / "nonexistent.yaml"
        builder = UniverseBuilder(config_path=missing_config)
        assert builder.config["default"] == "large_cap"
        assert builder.config["large_cap"]["min_price"] == 10

    def test_invalid_yaml_uses_defaults(self, tmp_path, mock_alpaca):
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("not: valid: yaml: [")
        builder = UniverseBuilder(config_path=bad_config)
        assert builder.config["default"] == "large_cap"


class TestCachePath:
    """Test _get_cache_path."""

    def test_includes_profile_and_date(self, builder):
        path = builder._get_cache_path("large_cap")
        today = datetime.now().strftime("%Y-%m-%d")
        assert path.name == f"large_cap_{today}.csv"
        assert path.parent == builder.UNIVERSES_DIR


class TestLoadCached:
    """Test _load_cached."""

    def test_valid_cache_returns_result(self, builder):
        cache_path = builder._get_cache_path("large_cap")
        df = pd.DataFrame({
            "Ticker": ["AAPL", "MSFT"],
            "Profile": ["large_cap", "large_cap"],
            "GeneratedDate": ["2026-01-01 12:00:00", "2026-01-01 12:00:00"],
            "TotalAssets": [1000, 1000],
            "AfterTradable": [500, 500],
            "AfterPrice": [200, 200],
            "AfterDVol": [50, 50],
        })
        df.to_csv(cache_path, index=False)

        result = builder._load_cached(cache_path)
        assert result is not None
        assert result.tickers == ["AAPL", "MSFT"]
        assert result.cache_hit is True
        assert result.total_assets == 1000
        assert result.after_tradable_filter == 500
        assert result.after_price_filter == 200
        assert result.after_dvol_filter == 50

    def test_expired_cache_returns_none(self, builder):
        cache_path = builder._get_cache_path("large_cap")
        df = pd.DataFrame({"Ticker": ["AAPL"]})
        df.to_csv(cache_path, index=False)
        # Backdate the file to 5 hours ago (TTL is 4 hours)
        import os
        import time
        old_mtime = time.time() - (5 * 3600)
        os.utime(cache_path, (old_mtime, old_mtime))

        assert builder._load_cached(cache_path) is None

    def test_corrupted_csv_returns_none(self, builder):
        cache_path = builder._get_cache_path("large_cap")
        cache_path.write_text("not,a,csv\n1,2")
        assert builder._load_cached(cache_path) is None


class TestSaveCache:
    """Test _save_cache atomic write."""

    def test_atomic_write_creates_file(self, builder):
        cache_path = builder._get_cache_path("large_cap")
        result = UniverseResult(
            tickers=["AAPL", "MSFT"],
            profile="large_cap",
            total_assets=1000,
            after_tradable_filter=500,
            after_price_filter=200,
            after_dvol_filter=50,
        )
        builder._save_cache(result, cache_path)
        assert cache_path.exists()

    def test_includes_funnel_metrics(self, builder):
        cache_path = builder._get_cache_path("large_cap")
        result = UniverseResult(
            tickers=["AAPL"],
            profile="large_cap",
            total_assets=1000,
            after_tradable_filter=500,
            after_price_filter=200,
            after_dvol_filter=50,
        )
        builder._save_cache(result, cache_path)
        df = pd.read_csv(cache_path)
        assert "TotalAssets" in df.columns
        assert df["TotalAssets"].iloc[0] == 1000
        assert df["AfterTradable"].iloc[0] == 500
        assert df["AfterPrice"].iloc[0] == 200
        assert df["AfterDVol"].iloc[0] == 50

    def test_no_temp_file_left_behind_on_error(self, builder, tmp_path):
        # Use a read-only directory to force atomic rename to fail
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        cache_path = ro_dir / "large_cap_2026-01-01.csv"
        result = UniverseResult(tickers=["AAPL"], profile="large_cap")

        # Make directory read-only (os.chmod on Unix)
        import os
        os.chmod(ro_dir, 0o555)
        try:
            builder._save_cache(result, cache_path)
        except Exception:
            pass
        finally:
            os.chmod(ro_dir, 0o755)

        # Temp file should not exist
        assert not (ro_dir / "large_cap_2026-01-01.csv.tmp").exists()


class TestFetchAssets:
    """Test _fetch_assets."""

    def test_returns_assets_from_alpaca(self, builder, mock_alpaca):
        mock_alpaca.get_assets.return_value = [
            Mock(symbol="AAPL", tradable=True, exchange="NASDAQ", marginable=True),
            Mock(symbol="OTCBB", tradable=True, exchange="OTC", marginable=True),
        ]
        assets = builder._fetch_assets()
        assert len(assets) == 2
        mock_alpaca.get_assets.assert_called_once_with(status="active", asset_class="us_equity")

    def test_returns_empty_on_exception(self, builder, mock_alpaca):
        mock_alpaca.get_assets.side_effect = Exception("API error")
        assets = builder._fetch_assets()
        assert assets == []


class TestBuildUniverse:
    """Test full build_universe pipeline with mocked dependencies."""

    def test_full_pipeline_large_cap(self, builder, mock_alpaca):
        assets = [
            _make_asset("AAPL", name="Apple Inc", marginable=True),
            _make_asset("MSFT", name="Microsoft Corp", marginable=True),
            _make_asset("SPY", name="SPDR S&P 500 ETF Trust", marginable=True),
            _make_asset("OTCBB", name="OTC Stock", exchange="OTC", marginable=True),
            _make_asset("PENNY", name="Penny Stock", marginable=False),
        ]

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={
                "AAPL": 150.0,
                "MSFT": 300.0,
                "SPY": 400.0,
                "OTCBB": 5.0,
                "PENNY": 0.5,
            }):
                with patch.object(builder, "_compute_dollar_volumes", return_value={
                    "AAPL": 100_000_000,
                    "MSFT": 120_000_000,
                }):
                    result = builder.build_universe("large_cap")

        assert isinstance(result, UniverseResult)
        assert result.profile == "large_cap"
        assert "AAPL" in result.tickers
        assert "MSFT" in result.tickers
        # ETF excluded
        assert "SPY" not in result.tickers
        # OTC excluded
        assert "OTCBB" not in result.tickers
        # Penny excluded by price
        assert "PENNY" not in result.tickers
        assert result.total_assets == 5
        assert result.after_tradable_filter == 3  # AAPL, MSFT, PENNY (excludes OTC, SPY)
        assert result.after_price_filter == 2  # AAPL, MSFT (PENNY excluded by price)
        assert result.after_dvol_filter == 2  # AAPL, MSFT

    def test_high_octane_requires_marginable(self, builder, mock_alpaca):
        assets = [
            _make_asset("AAPL", name="Apple", marginable=True),
            _make_asset("EBAY", name="eBay Inc", marginable=True),
            _make_asset("PENNY", name="Penny", marginable=False),
        ]

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={
                "AAPL": 50.0,
                "EBAY": 5.0,
                "PENNY": 1.0,
            }):
                with patch.object(builder, "_compute_dollar_volumes", return_value={
                    "AAPL": 50_000_000,
                    "EBAY": 30_000_000,
                }):
                    result = builder.build_universe("high_octane")

        assert "AAPL" in result.tickers
        assert "EBAY" in result.tickers
        assert "PENNY" not in result.tickers

    def test_etf_detection_by_name(self, builder, mock_alpaca):
        assets = [
            _make_asset("AAPL", name="Apple Inc"),
            _make_asset("SPY", name="SPDR S&P 500 ETF Trust"),
            _make_asset("QQQ", name="Invesco QQQ Trust"),
            _make_asset("VGT", name="Vanguard Information Technology ETF"),
            _make_asset("PIMCO", name="PIMCO Active Bond Fund"),
            _make_asset("WISDOM", name="WisdomTree SmallCap Fund"),
            _make_asset("REGULAR", name="Regular Company"),
        ]

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={
                "AAPL": 150.0,
                "SPY": 400.0,
                "QQQ": 350.0,
                "VGT": 300.0,
                "PIMCO": 100.0,
                "WISDOM": 50.0,
                "REGULAR": 75.0,
            }):
                with patch.object(builder, "_compute_dollar_volumes", return_value={
                    "AAPL": 100_000_000,
                    "REGULAR": 90_000_000,
                }):
                    result = builder.build_universe("large_cap")

        assert "AAPL" in result.tickers
        assert "REGULAR" in result.tickers
        assert "SPY" not in result.tickers
        assert "QQQ" not in result.tickers
        assert "VGT" not in result.tickers
        assert "PIMCO" not in result.tickers
        assert "WISDOM" not in result.tickers
        assert result.after_tradable_filter == 2
        assert result.after_price_filter == 2
        assert result.after_dvol_filter == 2

    def test_force_refresh_bypasses_cache(self, builder, mock_alpaca):
        cache_path = builder._get_cache_path("large_cap")
        df = pd.DataFrame({"Ticker": ["OLD"]})
        df.to_csv(cache_path, index=False)

        assets = [_make_asset("AAPL", name="Apple")]
        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={"AAPL": 150.0}):
                with patch.object(builder, "_compute_dollar_volumes", return_value={"AAPL": 100_000_000}):
                    result = builder.build_universe("large_cap", force_refresh=True)

        assert "AAPL" in result.tickers
        assert "OLD" not in result.tickers

    def test_cache_hit_returns_cached(self, builder, mock_alpaca):
        cache_path = builder._get_cache_path("large_cap")
        df = pd.DataFrame({
            "Ticker": ["CACHED"],
            "Profile": ["large_cap"],
            "GeneratedDate": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        })
        df.to_csv(cache_path, index=False)

        result = builder.build_universe("large_cap")
        assert result.tickers == ["CACHED"]
        assert result.cache_hit is True

    def test_max_dollar_volume_filter(self, builder, mock_alpaca):
        # Create a custom config with max_dollar_volume
        config_path = builder.config_path
        config_path.write_text("""
universes:
  default: test_profile
  test_profile:
    min_price: 10
    min_dollar_volume: 1000000
    max_dollar_volume: 50000000
    lookback_days: 60
    exclude_exchanges: ['OTC']
""")
        builder = UniverseBuilder(config_path=config_path)
        builder.UNIVERSES_DIR = builder.config_path.parent / "universes"
        builder.UNIVERSES_DIR.mkdir(parents=True, exist_ok=True)

        assets = [
            _make_asset("SMALL", name="Small Cap"),
            _make_asset("LARGE", name="Large Cap"),
        ]

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={
                "SMALL": 50.0,
                "LARGE": 200.0,
            }):
                with patch.object(builder, "_compute_dollar_volumes", return_value={
                    "SMALL": 30_000_000,
                    "LARGE": 100_000_000,
                }):
                    result = builder.build_universe("test_profile")

        assert "SMALL" in result.tickers
        assert "LARGE" not in result.tickers


class TestProfileHelpers:
    """Test get_profile_config and load_universe."""

    def test_get_profile_config_returns_profile(self, builder):
        cfg = builder.get_profile_config("large_cap")
        assert cfg["min_price"] == 10

    def test_get_profile_config_fallback_to_default(self, builder):
        cfg = builder.get_profile_config("nonexistent")
        assert cfg["min_price"] == 10  # falls back to large_cap

    def test_load_universe_uses_default_profile(self, builder, mock_alpaca):
        assets = [_make_asset("AAPL", name="Apple")]
        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={"AAPL": 150.0}):
                with patch.object(builder, "_compute_dollar_volumes", return_value={"AAPL": 100_000_000}):
                    result = builder.load_universe()

        assert result.profile == "large_cap"
        assert "AAPL" in result.tickers


class TestSectorEnrichment:
    """Sector enrichment via FMP."""

    def test_fetch_sectors_fail_open(self, mock_alpaca):
        """Without FMP_API_KEY, all sectors return Unknown."""
        builder = UniverseBuilder()
        sectors = builder._fetch_sectors_from_fmp(["FAKE"])
        assert sectors["FAKE"] == "Unknown"

    def test_build_universe_adds_sector_column(self, builder, mock_alpaca):
        assets = [
            _make_asset("AAPL", name="Apple Inc", marginable=True),
        ]

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={"AAPL": 200.0}):
                with patch.object(builder, "_compute_dollar_volumes", return_value={"AAPL": 100_000_000.0}):
                    with patch.object(builder, "_fetch_sectors_from_fmp", return_value={"AAPL": "Technology"}):
                        result = builder.build_universe("large_cap", force_refresh=True)

        assert result.sectors == {"AAPL": "Technology"}
        # Verify cache was saved with sector column
        cache_path = builder._get_cache_path("large_cap")
        df = pd.read_csv(cache_path)
        assert "Sector" in df.columns
        assert df["Sector"].iloc[0] == "Technology"

    def test_load_cached_restores_sectors(self, tmp_path, mock_alpaca):
        builder = UniverseBuilder()
        builder.UNIVERSES_DIR = tmp_path

        # Write a CSV with sector column
        csv_path = tmp_path / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL", "MSFT"],
            "Sector": ["Technology", "Technology"],
            "Profile": ["large_cap", "large_cap"],
            "TotalAssets": [1000, 1000],
            "AfterTradable": [500, 500],
            "AfterPrice": [300, 300],
            "AfterDVol": [100, 100],
        }).to_csv(csv_path, index=False)

        loaded = builder._load_cached(csv_path)
        assert loaded is not None
        assert loaded.sectors == {"AAPL": "Technology", "MSFT": "Technology"}


class TestProgressCallback:
    """Test progress callback invocation in slow methods."""

    def test_get_current_prices_emits_progress(self, builder, mock_alpaca):
        mock_alpaca.get_latest_prices_batch.return_value = {"AAPL": 150.0}
        updates = []

        def callback(update):
            updates.append(update)

        builder._get_current_prices(["AAPL"], progress_callback=callback)
        assert len(updates) == 1
        assert updates[0]["step"] == "prices"
        assert updates[0]["current"] == 1
        assert updates[0]["total"] == 1
        assert "Fetching prices" in updates[0]["message"]

    def test_compute_dollar_volumes_emits_progress(self, builder, mock_alpaca):
        """Test that _compute_dollar_volumes emits progress updates."""
        # Create mock bars that AlpacaClient would return
        mock_bar = Mock()
        mock_bar.close = 100.0
        mock_bar.volume = 1_000_000
        mock_bars = [mock_bar] * 20  # 20 bars

        # Mock the data_client.get_stock_bars response
        mock_response = Mock()
        mock_response.data = {"AAPL": mock_bars}
        mock_alpaca.data_client.get_stock_bars.return_value = mock_response

        updates = []

        def callback(update):
            updates.append(update)

        result = builder._compute_dollar_volumes(["AAPL"], 60, progress_callback=callback)
        assert len(updates) == 1
        assert updates[0]["step"] == "liquidity"
        assert updates[0]["current"] == 1
        assert updates[0]["total"] == 1
        assert "Computing liquidity" in updates[0]["message"]
        assert "AAPL" in result

    def test_build_universe_propagates_callback(self, builder, mock_alpaca):
        """Test that build_universe forwards callback to slow methods."""
        assets = [
            _make_asset("AAPL", name="Apple Inc", marginable=True),
        ]
        updates = []

        def callback(update):
            updates.append(update)

        def mock_get_prices(tickers, progress_callback=None):
            if progress_callback:
                progress_callback({"step": "prices", "current": 1, "total": 1, "message": "Fetching prices"})
            return {"AAPL": 150.0}

        def mock_compute_dvol(tickers, lookback, progress_callback=None):
            if progress_callback:
                progress_callback({"step": "liquidity", "current": 1, "total": 1, "message": "Computing liquidity"})
            return {"AAPL": 100_000_000}

        def mock_fetch_sectors(tickers, progress_callback=None):
            if progress_callback:
                progress_callback({"step": "sectors", "current": 1, "total": 1, "message": "Fetching sectors"})
            return {"AAPL": "Technology"}

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", side_effect=mock_get_prices):
                with patch.object(builder, "_compute_dollar_volumes", side_effect=mock_compute_dvol):
                    with patch.object(builder, "_fetch_sectors_from_fmp", side_effect=mock_fetch_sectors):
                        result = builder.build_universe("large_cap", progress_callback=callback)

        # Should receive at least prices and liquidity updates
        steps = [u["step"] for u in updates]
        assert "prices" in steps
        assert "liquidity" in steps
        assert "sectors" in steps
