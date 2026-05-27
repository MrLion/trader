#!/usr/bin/env python3
"""Tests for backtest CLI (scripts/backtest.py).

Covers:
1. argparse — all flags parse correctly
2. main() dry-run path — prints config, exits 0
3. main() invalid strategy — prints error, exits 1
4. main() invalid date format — raises ValueError
5. watchlist path resolution — relative path preserved
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# scripts/backtest.py conflicts with traderlib/backtest/__init__.py when the full
# test suite runs (pytest collection may populate sys.modules with the package
# before this module is imported). Load the CLI module with a unique name.
_backtest_path = Path(__file__).parent.parent / "scripts" / "backtest.py"
_spec = importlib.util.spec_from_file_location("scripts_backtest", str(_backtest_path))
backtest = importlib.util.module_from_spec(_spec)
sys.modules["scripts_backtest"] = backtest
_spec.loader.exec_module(backtest)


class TestArgparse:
    """Test argument parsing."""

    def test_required_args(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ]
        with patch.object(sys, "argv", test_args):
            args = backtest.parser.parse_args()
        assert args.start == "2024-01-01"
        assert args.end == "2024-12-31"
        assert args.capital == 100_000
        assert args.risk_profile == "conservative"

    def test_all_optional_args(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--capital", "50000",
            "--tickers", "AAPL", "MSFT",
            "--watchlist", "/tmp/watchlist.csv",
            "--risk-profile", "aggressive",
            "--slippage", "10",
            "--max-positions", "5",
            "--csv", "/tmp/trades.csv",
            "--trades",
            "--dry-run",
            "--alpaca-mode", "paper",
            "--strategy", "stage2_momentum",
        ]
        with patch.object(sys, "argv", test_args):
            args = backtest.parser.parse_args()
        assert args.capital == 50000
        assert args.tickers == ["AAPL", "MSFT"]
        assert args.watchlist == Path("/tmp/watchlist.csv")
        assert args.risk_profile == "aggressive"
        assert args.slippage == 10.0
        assert args.max_positions == 5
        assert args.csv == "/tmp/trades.csv"
        assert args.trades is True
        assert args.dry_run is True
        assert args.alpaca_mode == "paper"
        assert args.strategy == "stage2_momentum"

    def test_missing_required_args_exits(self):
        test_args = ["backtest.py", "--start", "2024-01-01"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                backtest.parser.parse_args()

    def test_default_strategy(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ]
        with patch.object(sys, "argv", test_args):
            args = backtest.parser.parse_args()
        assert args.strategy == "stage2_momentum"


class TestMainDryRun:
    """Test main() dry-run execution path."""

    def test_dry_run_prints_and_exits_zero(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--dry-run",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout"):
                result = backtest.main()
        assert result is None  # dry-run returns early

    def test_dry_run_with_custom_values(self):
        test_args = [
            "backtest.py",
            "--start", "2024-06-01",
            "--end", "2024-06-30",
            "--capital", "250000",
            "--risk-profile", "aggressive",
            "--slippage", "3",
            "--max-positions", "15",
            "--dry-run",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout"):
                result = backtest.main()
        assert result is None


class TestMainInvalidStrategy:
    """Test main() with unknown strategy."""

    def test_invalid_strategy_exits_one(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--strategy", "nonexistent_strategy_xyz",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout"):
                with patch("sys.stderr"):
                    with patch("traderlib.alpaca_client.AlpacaClient"):
                        with patch.object(backtest, "AlpacaDataProvider"):
                            with patch.object(backtest, "RiskConfigManager"):
                                with patch.object(backtest, "ExitEngine"):
                                    with pytest.raises(SystemExit) as exc:
                                        backtest.main()
        assert exc.value.code == 1


class TestWatchlistResolution:
    """Test watchlist path resolution logic."""

    def test_absolute_path_unchanged(self, tmp_path):
        watchlist = tmp_path / "my_watchlist.csv"
        df = pd.DataFrame({"Ticker": ["AAPL"]})
        df.to_csv(watchlist, index=False)

        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--watchlist", str(watchlist),
        ]
        with patch.object(sys, "argv", test_args):
            args = backtest.parser.parse_args()
        assert args.watchlist == watchlist

    def test_relative_path(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--watchlist", "watchlist.csv",
        ]
        with patch.object(sys, "argv", test_args):
            args = backtest.parser.parse_args()
        assert args.watchlist == Path("watchlist.csv")


class TestDateParsing:
    """Test date parsing in main()."""

    def test_valid_iso_dates(self):
        test_args = [
            "backtest.py",
            "--start", "2024-01-15",
            "--end", "2024-06-30",
            "--dry-run",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout"):
                result = backtest.main()
        assert result is None

    def test_invalid_date_format_raises_valueerror(self):
        test_args = [
            "backtest.py",
            "--start", "01-15-2024",
            "--end", "2024-06-30",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout"):
                with pytest.raises(ValueError):
                    backtest.main()
