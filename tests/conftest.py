import sys
from pathlib import Path
import os
import tempfile
import shutil

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

# Standardize the Python path for all tests
# We add the project root to the path. This allows tests to use
# absolute imports like 'from scripts.alpaca_client import ...'
# which prevents namespace collisions with installed libraries like 'alpaca-py'.
root_dir = Path(__file__).parent.parent.absolute()

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Note: We explicitly avoid adding 'scripts' or 'scripts/lib' directly to sys.path
# to prevent 'alpaca_client.py' from shadowing the 'alpaca' package.


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
