#!/usr/bin/env python3
"""Tests for doctor module (configuration validation).

Covers:
1. check_python_version — pass/fail on version
2. check_dependencies — present/missing packages
3. check_alpaca_credentials — env vars, .env file, missing
4. check_directories — existing/missing directories
5. check_watchlist — populated, empty, missing, corrupted
6. check_telegram_config — env var, .env file, missing
7. check_git_hooks — installed/not installed
8. run_checks — returns correct tuple structure
9. main — exit codes
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import doctor


def _make_version_info(major, minor, micro=0):
    """Create a version_info-like namedtuple for mocking."""
    vi = SimpleNamespace(major=major, minor=minor, micro=micro)
    return vi


class TestCheckPythonVersion:
    """Test check_python_version."""

    def test_passes_on_python_311(self):
        with patch.object(sys, "version_info", _make_version_info(3, 11)):
            ok, status, fix = doctor.check_python_version()
        assert ok is True
        assert "3.11" in status
        assert fix == "OK"

    def test_passes_on_python_312(self):
        with patch.object(sys, "version_info", _make_version_info(3, 12)):
            ok, status, fix = doctor.check_python_version()
        assert ok is True

    def test_fails_on_python_310(self):
        with patch.object(sys, "version_info", _make_version_info(3, 10)):
            ok, status, fix = doctor.check_python_version()
        assert ok is False
        assert "3.10" in status
        assert "3.11+" in fix

    def test_fails_on_python_2(self):
        with patch.object(sys, "version_info", _make_version_info(2, 7)):
            ok, status, fix = doctor.check_python_version()
        assert ok is False


class TestCheckDependencies:
    """Test check_dependencies."""

    def test_all_present(self):
        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: MagicMock()):
            ok, status, fix = doctor.check_dependencies()
        assert ok is True
        assert "All required" in status
        assert fix == "OK"

    def test_missing_packages(self):
        def fake_import(name, *args, **kwargs):
            if name == "pandas":
                raise ImportError("No module named pandas")
            return MagicMock()

        with patch("builtins.__import__", side_effect=fake_import):
            ok, status, fix = doctor.check_dependencies()
        assert ok is False
        assert "pandas" in status
        assert "pip3 install" in fix


class TestCheckAlpacaCredentials:
    """Test check_alpaca_credentials."""

    def test_from_env_vars(self):
        env = {
            "ALPACA_PAPER_API_KEY": "key123",
            "ALPACA_PAPER_SECRET_KEY": "secret456",
        }
        with patch.dict("os.environ", env, clear=True):
            ok, status, fix = doctor.check_alpaca_credentials()
        assert ok is True
        assert "Paper keys found" in status
        assert "env vars" in status

    def test_from_generic_env_vars(self):
        env = {
            "ALPACA_API_KEY": "key123",
            "ALPACA_SECRET_KEY": "secret456",
        }
        with patch.dict("os.environ", env, clear=True):
            ok, status, fix = doctor.check_alpaca_credentials()
        assert ok is True
        assert "env vars" in status

    def test_from_dotenv_file(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("ALPACA_PAPER_API_KEY=filekey\nALPACA_PAPER_SECRET_KEY=filesecret\n")
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                ok, status, fix = doctor.check_alpaca_credentials()
        assert ok is True
        assert ".env file" in status

    def test_incomplete_dotenv(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("ALPACA_PAPER_API_KEY=filekey\n")
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                ok, status, fix = doctor.check_alpaca_credentials()
        assert ok is False
        assert ".env exists but keys incomplete" in status

    def test_not_configured(self, tmp_path):
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                ok, status, fix = doctor.check_alpaca_credentials()
        assert ok is False
        assert "Not configured" in status


class TestCheckDirectories:
    """Test check_directories."""

    def test_all_exist(self, tmp_path):
        for d in ["data", "scans", "reports", "memory"]:
            (tmp_path / d).mkdir()
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_directories()
        assert ok is True
        assert "All directories exist" in status

    def test_missing_directories(self, tmp_path):
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_directories()
        assert ok is False
        assert "Missing" in status
        assert "data" in status


class TestCheckWatchlist:
    """Test check_watchlist."""

    def test_populated_watchlist(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        watchlist = data_dir / "watchlist.csv"
        df = pd.DataFrame({"Ticker": ["AAPL", "MSFT"]})
        df.to_csv(watchlist, index=False)

        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_watchlist()
        assert ok is True
        assert "2 tickers" in status

    def test_empty_watchlist(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        watchlist = data_dir / "watchlist.csv"
        pd.DataFrame({"Ticker": []}).to_csv(watchlist, index=False)

        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_watchlist()
        assert ok is False
        assert "empty" in status

    def test_missing_watchlist(self, tmp_path):
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_watchlist()
        assert ok is False
        assert "not found" in status

    def test_corrupted_watchlist(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        watchlist = data_dir / "watchlist.csv"
        watchlist.write_text("not,csv\n1")

        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            with patch("pandas.read_csv", side_effect=pd.errors.EmptyDataError("No data")):
                ok, status, fix = doctor.check_watchlist()
        assert ok is False
        assert "Corrupted" in status


class TestCheckTelegramConfig:
    """Test check_telegram_config."""

    def test_from_env_var(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "token123"}, clear=True):
            ok, status, fix = doctor.check_telegram_config()
        assert ok is True
        assert "TELEGRAM_BOT_TOKEN set" in status

    def test_from_dotenv(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("TELEGRAM_BOT_TOKEN=token456\n")
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                ok, status, fix = doctor.check_telegram_config()
        assert ok is True
        assert ".env" in status

    def test_not_configured(self, tmp_path):
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                ok, status, fix = doctor.check_telegram_config()
        assert ok is True  # Optional — still passes
        assert "Not configured" in status


class TestCheckGitHooks:
    """Test check_git_hooks."""

    def test_hooks_installed(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "pre-commit").write_text("#!/bin/sh")

        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_git_hooks()
        assert ok is True
        assert "installed" in status

    def test_hooks_not_installed(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir()

        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_git_hooks()
        assert ok is False
        assert "not installed" in status

    def test_not_a_git_repo(self, tmp_path):
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            ok, status, fix = doctor.check_git_hooks()
        assert ok is True
        assert "Not a git repo" in status


class TestRunChecks:
    """Test run_checks returns correct structure."""

    def test_returns_list_of_tuples(self, tmp_path):
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            checks = doctor.run_checks()
        assert isinstance(checks, list)
        assert len(checks) == 7
        for item in checks:
            assert len(item) == 4
            name, ok, status, fix = item
            assert isinstance(name, str)
            assert isinstance(ok, bool)
            assert isinstance(status, str)
            assert isinstance(fix, str)


class TestMain:
    """Test main entry point."""

    def test_returns_zero_when_all_pass(self, tmp_path):
        # Set up a perfect environment
        for d in ["data", "scans", "reports", "memory"]:
            (tmp_path / d).mkdir()
        data_dir = tmp_path / "data"
        pd.DataFrame({"Ticker": ["AAPL"]}).to_csv(data_dir / "watchlist.csv", index=False)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hooks").mkdir()
        (git_dir / "hooks" / "pre-commit").write_text("#!/bin/sh")

        env = {
            "ALPACA_PAPER_API_KEY": "k",
            "ALPACA_PAPER_SECRET_KEY": "s",
            "TELEGRAM_BOT_TOKEN": "t",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch.object(doctor, "PROJECT_ROOT", tmp_path):
                with patch.object(sys, "version_info", _make_version_info(3, 12)):
                    with patch.object(doctor, "check_dependencies", return_value=(True, "All OK", "OK")):
                        with patch("sys.stdout"):
                            result = doctor.main()
        assert result == 0

    def test_returns_nonzero_when_some_fail(self, tmp_path):
        with patch.object(doctor, "PROJECT_ROOT", tmp_path):
            with patch("sys.stdout"):
                result = doctor.main()
        assert result == 1
