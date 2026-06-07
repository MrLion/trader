import sys
from pathlib import Path
import os
import tempfile
import shutil

# Local test-only helper. Imported at the top so the rest of the file
# can refer to the session-scope fixture and the marker registration.
import tests._isolation_check as _isolation_check

# =============================================================================
# TEST DATA ISOLATION: Prevent tests from writing to production data/
# =============================================================================
# Set PAPER_TRADING_DATA_DIR to a temp directory before any imports happen.
# This ensures all modules use isolated test data instead of production files.
# =============================================================================

# Create temp directory for test data
_test_data_dir = tempfile.mkdtemp(prefix='paper_trading_test_')
os.environ['PAPER_TRADING_DATA_DIR'] = _test_data_dir

# PHASE 2: Mark test mode for metadata tagging
os.environ['PAPER_TRADING_TEST_MODE'] = 'true'

# Create empty files to prevent errors
test_positions = Path(_test_data_dir) / 'paper_positions.json'
test_account = Path(_test_data_dir) / 'paper_account.json'
test_trades = Path(_test_data_dir) / 'paper_trades.jsonl'
test_watchlist = Path(_test_data_dir) / 'watchlist.csv'

# Initialize with empty state
test_positions.write_text('{}')
test_account.write_text('{"initial_capital": 100000.0, "cash": 100000.0, "equity": 100000.0}')
test_trades.write_text('')
test_watchlist.write_text('Ticker,Pivot_Price,Sector\n')

print(f"[conftest] Using test data dir: {_test_data_dir}")

# Cleanup function - registered with atexit to clean up temp dir
def _cleanup_test_data():
    if Path(_test_data_dir).exists():
        shutil.rmtree(_test_data_dir, ignore_errors=True)
        print(f"[conftest] Cleaned up test data dir: {_test_data_dir}")

import atexit
atexit.register(_cleanup_test_data)

# =============================================================================
# NAMESPACE SHIELD: Fix alpaca module collision
# =============================================================================
# There's a system binary /Library/Frameworks/Python.framework/Versions/3.14/bin/alpaca.py
# that conflicts with the alpaca-py package. When Python tries to import from
# alpaca.data.historical, it finds this single file first and fails with:
#   "'alpaca' is not a package"
#
# Fix: Detect and remove the incorrectly loaded module before tests run.
# =============================================================================

# Check if alpaca module is loaded and pointing to the wrong location
if 'alpaca' in sys.modules:
    alpaca_module = sys.modules['alpaca']
    module_file = getattr(alpaca_module, '__file__', '')
    # If it's the binary in bin/ directory, remove it to force proper reload
    if '/bin/alpaca.py' in str(module_file) or module_file.endswith('/alpaca.py'):
        # Remove all alpaca submodules from cache
        modules_to_remove = [mod for mod in sys.modules.keys() if mod.startswith('alpaca')]
        for mod in modules_to_remove:
            del sys.modules[mod]

# Also add the scripts directory to help with imports
scripts_dir = Path(__file__).parent.parent / 'scripts'
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# Add traderlib to path for library imports
tradelib_dir = Path(__file__).parent.parent / 'traderlib'
if str(tradelib_dir) not in sys.path:
    sys.path.insert(0, str(tradelib_dir))

# Standardize the Python path for all tests
# We add the project root to the path. This allows tests to use
# absolute imports like 'from scripts.alpaca_client import ...'
# which prevents namespace collisions with installed libraries like 'alpaca-py'.
root_dir = Path(__file__).parent.parent.absolute()

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Note: We now use traderlib/ for library modules and scripts/ for CLI tools.
# Imports should use: from traderlib.module_name import ...


# =============================================================================
# Pytest Fixtures
# =============================================================================

import pytest


@pytest.fixture
def test_data_dir():
    """Provide path to test data directory."""
    return Path(_test_data_dir)


@pytest.fixture
def clean_test_data():
    """Reset test data to clean state before a test."""
    # Reset files
    test_positions.write_text('{}')
    test_account.write_text('{"initial_capital": 100000.0, "cash": 100000.0, "equity": 100000.0}')
    test_trades.write_text('')
    yield
    # Cleanup after test
    test_positions.write_text('{}')
    test_account.write_text('{"initial_capital": 100000.0, "cash": 100000.0, "equity": 100000.0}')
    test_trades.write_text('')


# =============================================================================
# Test Isolation Hardening — Task 4: production-data safety net
# =============================================================================
# A session-scope autouse fixture that snapshots the production data/ tree
# at session start and asserts it is unchanged at session teardown. Any
# test that writes to data/ (directly or via a module that resolves a
# hardcoded production path) will fail the entire session.
#
# Opt-out mechanisms:
#   - @pytest.mark.allow_production_writes — register the test as
#     intentionally touching production paths.
#   - pytest --no-isolation-check — ad-hoc CLI escape hatch for
#     debugging. The flag is checked in tests/_isolation_check.py.
# =============================================================================


def pytest_addoption(parser):
    """Register custom command-line options with pytest's argparse.

    ``--no-isolation-check`` is a debug escape hatch that lets a
    developer skip the production-data safety net. We must register
    it here so pytest's argparse does not reject the flag with
    "unrecognized arguments". The actual gating logic lives in
    :func:`tests._isolation_check.is_check_disabled`, which inspects
    ``sys.argv`` at conftest-load time.
    """
    parser.addoption(
        "--no-isolation-check",
        action="store_true",
        default=False,
        help="Skip the production-data isolation check (debug hatch).",
    )


def pytest_configure(config):
    """Register custom markers with pytest.

    Called once at pytest startup. Without this, any test marked with
    ``@pytest.mark.allow_production_writes`` would emit a "unknown
    marker" warning.
    """
    config.addinivalue_line(
        "markers",
        "allow_production_writes: opt a test out of the production-data isolation check",
    )


@pytest.fixture(scope="session", autouse=True)
def _isolation_check_session(request):
    """Snapshot production data/ at session start, verify at teardown.

    This fixture runs once per ``pytest`` invocation. On session start,
    it captures a baseline snapshot of ``<project_root>/data/`` (if the
    check is not disabled). On session finish, it walks the tree again
    and raises :class:`AssertionError` with a diff report if anything
    changed. The failure is reported as a session-level teardown error
    and fails the entire test run.
    """
    disabled = _isolation_check.is_check_disabled()
    if disabled:
        print("[isolation_check] Disabled via --no-isolation-check")
    else:
        _isolation_check._capture_snapshot()
        print("[isolation_check] Production data snapshot captured")

    yield

    if not disabled:
        try:
            _isolation_check.assert_clean_production_data()
        except AssertionError as exc:
            # Re-raise so pytest reports this as a teardown failure.
            # The message is the joined diff lines emitted by
            # assert_clean_production_data().
            raise exc
        else:
            print("[isolation_check] Production data unchanged")
