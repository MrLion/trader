#!/usr/bin/env python3
"""GS-002: Doctor command for configuration validation.

Checks system configuration and provides actionable fixes.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Project root
PROJECT_ROOT = Path(__file__).parent.parent


def colorize(text: str, color: str = '') -> str:
    """Apply color if NO_COLOR is not set."""
    if os.environ.get('NO_COLOR', '').strip():
        return text

    colors = {
        'green': '\033[32m',
        'red': '\033[31m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'cyan': '\033[36m',
        'reset': '\033[0m'
    }

    if color not in colors:
        return text

    return f"{colors[color]}{text}{colors['reset']}"


def check_python_version() -> Tuple[bool, str, str]:
    """Check Python version is 3.11+."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        return False, f"Python {version.major}.{version.minor}.{version.micro}", "Python 3.11+ required"
    return True, f"Python {version.major}.{version.minor}.{version.micro}", "OK"


def check_dependencies() -> Tuple[bool, str, str]:
    """Check if required dependencies are installed."""
    required = ['pandas', 'numpy', 'yfinance', 'alpaca_trade_api']
    missing = []

    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            missing.append(pkg)

    if missing:
        return False, f"Missing: {', '.join(missing)}", "Run: pip3 install -r requirements/requirements.txt"
    return True, "All required packages installed", "OK"


def check_alpaca_credentials() -> Tuple[bool, str, str]:
    """Check Alpaca API credentials are configured.

    Checks in priority order:
      1. Mode-specific env vars (ALPACA_PAPER_API_KEY / ALPACA_LIVE_API_KEY)
      2. Generic env vars (ALPACA_API_KEY / ALPACA_SECRET_KEY)
      3. .env file in project root (loaded by alpaca_client on startup)
    """
    from dotenv import dotenv_values

    # Merge shell env + .env file to simulate what alpaca_client sees at runtime
    env_path = PROJECT_ROOT / '.env'
    dotenv_vars = dotenv_values(env_path) if env_path.exists() else {}
    combined = {**dotenv_vars, **os.environ}  # shell env wins over .env

    paper_key = combined.get('ALPACA_PAPER_API_KEY') or combined.get('ALPACA_API_KEY')
    paper_secret = combined.get('ALPACA_PAPER_SECRET_KEY') or combined.get('ALPACA_SECRET_KEY')

    if paper_key and paper_secret:
        source = 'env vars' if 'ALPACA_PAPER_API_KEY' in os.environ or 'ALPACA_API_KEY' in os.environ else '.env file'
        return True, f"Paper keys found ({source})", "OK"

    if env_path.exists():
        content = env_path.read_text()
        if 'ALPACA' in content:
            return False, ".env exists but keys incomplete", "Run: python3 scripts/setup_alpaca.py"

    return False, "Not configured", "Run: python3 scripts/setup_alpaca.py"


def check_directories() -> Tuple[bool, str, str]:
    """Check required directories exist."""
    required = ['data', 'scans', 'reports', 'memory']
    missing = []

    for dir_name in required:
        dir_path = PROJECT_ROOT / dir_name
        if not dir_path.exists():
            missing.append(dir_name)

    if missing:
        return False, f"Missing: {', '.join(missing)}", "Run: mkdir -p " + " ".join(missing)

    return True, "All directories exist", "OK"


def check_watchlist() -> Tuple[bool, str, str]:
    """Check watchlist exists and has data."""
    watchlist_path = PROJECT_ROOT / 'data' / 'watchlist.csv'

    if not watchlist_path.exists():
        return False, "Watchlist not found", "Run: python3 scripts/watchlist_manager.py add AAPL"

    # Check if empty
    try:
        import pandas as pd
        df = pd.read_csv(watchlist_path)
        count = len(df)
        if count == 0:
            return False, "Watchlist is empty", "Run: python3 scripts/watchlist_manager.py add TICKER"
        return True, f"{count} tickers in watchlist", "OK"
    except Exception:
        return False, "Corrupted watchlist file", "Delete and recreate: rm data/watchlist.csv"


def check_telegram_config() -> Tuple[bool, str, str]:
    """Check Telegram configuration (optional)."""
    if os.environ.get('TELEGRAM_BOT_TOKEN'):
        return True, "TELEGRAM_BOT_TOKEN set", "OK"

    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            if 'TELEGRAM_BOT_TOKEN' in f.read():
                return True, "TELEGRAM_BOT_TOKEN in .env", "OK"

    return True, "Not configured (optional)", "Set TELEGRAM_BOT_TOKEN for report delivery"


def check_git_hooks() -> Tuple[bool, str, str]:
    """Check pre-commit hooks are installed."""
    git_dir = PROJECT_ROOT / '.git'
    if not git_dir.exists():
        return True, "Not a git repo (OK)", "OK"

    hooks_dir = git_dir / 'hooks'
    pre_commit = hooks_dir / 'pre-commit'

    if pre_commit.exists():
        return True, "pre-commit hooks installed", "OK"

    return False, "pre-commit hooks not installed", "Run: pre-commit install"


def run_checks() -> List[Tuple[str, bool, str, str]]:
    """Run all configuration checks."""
    checks = [
        ("Python Version", *check_python_version()),
        ("Dependencies", *check_dependencies()),
        ("Alpaca Credentials", *check_alpaca_credentials()),
        ("Directories", *check_directories()),
        ("Watchlist", *check_watchlist()),
        ("Telegram (optional)", *check_telegram_config()),
        ("Git Hooks", *check_git_hooks()),
    ]
    return checks


def print_header():
    """Print doctor header."""
    print()
    print("=" * 60)
    print("  🔧 TRADER DOCTOR - Configuration Check")
    print("=" * 60)
    print()


def print_results(checks: List[Tuple[str, bool, str, str]]):
    """Print check results."""
    passed = sum(1 for _, ok, _, _ in checks if ok)
    total = len(checks)

    print()
    print(f"Results: {passed}/{total} checks passed")
    print()

    for name, ok, status, fix in checks:
        icon = "✅" if ok else "❌"
        status_color = "green" if ok else "red"
        print(f"{icon} {name:25} {colorize(status, status_color)}")
        if not ok and fix:
            print(f"   💡 Fix: {fix}")
    print()


def print_summary(passed: int, total: int):
    """Print final summary."""
    print("=" * 60)

    if passed == total:
        print(colorize("✅ All checks passed! System is ready.", "green"))
        print()
        print("Next steps:")
        print("  make test              # Run test suite")
        print("  make lint              # Run linter")
        print("  python3 scripts/entry_signals.py  # Scan for entry signals")
    elif passed >= total - 2:
        print(colorize(f"⚠️  {total - passed} minor issues found.", "yellow"))
        print()
        print("System is functional but has warnings.")
        print("Review the fixes above to resolve.")
    else:
        print(colorize(f"❌ {total - passed} critical issues found.", "red"))
        print()
        print("System is NOT ready for trading.")
        print("Fix the issues above before proceeding.")

    print("=" * 60)
    print()


def main():
    """Main doctor command."""
    print_header()

    print("Running configuration checks...")
    print()

    checks = run_checks()
    print_results(checks)

    passed = sum(1 for _, ok, _, _ in checks if ok)
    total = len(checks)

    print_summary(passed, total)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
