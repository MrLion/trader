#!/usr/bin/env python3
"""Validation script for Alpaca paper trading setup."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))


def validate_dependencies():
    """Check required dependencies are installed."""
    print("🔍 Checking dependencies...")

    required = {
        'alpaca': ['alpaca.data', 'alpaca.trading'],
        'core': ['pandas', 'numpy', 'pytz']
    }

    missing = []

    for category, modules in required.items():
        for module in modules:
            try:
                __import__(module)
            except ImportError:
                missing.append(module)

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("\nInstall with:")
        print("  pip install alpaca-py pandas numpy pytz")
        return False

    print("✅ All dependencies installed")
    return True


def validate_credentials():
    """Check Alpaca credentials are configured."""
    print("\n🔍 Checking Alpaca credentials...")

    import os
    from alpaca_client import AlpacaClient

    try:
        # Try to initialize client (will fail if no credentials)
        client = AlpacaClient(mode='paper')
        print("✅ Credentials configured")
        return True
    except ValueError as e:
        print(f"❌ {e}")
        print("\nConfigure credentials:")
        print("  python3 scripts/setup_alpaca.py")
        print("\nOr set environment variables:")
        print("  export ALPACA_API_KEY='your_key'")
        print("  export ALPACA_SECRET_KEY='your_secret'")
        return False


def validate_account():
    """Check Alpaca account is active."""
    print("\n🔍 Checking Alpaca account...")

    try:
        from alpaca_client import AlpacaClient

        client = AlpacaClient(mode='paper')
        account = client.get_account()

        if account['status'] != 'ACTIVE':
            print(f"⚠️ Account status: {account['status']}")
            return False

        print(f"✅ Account active")
        print(f"   Cash: ${account['cash']:,.2f}")
        print(f"   Equity: ${account['equity']:,.2f}")
        print(f"   Buying Power: ${account['buying_power']:,.2f}")

        return True

    except Exception as e:
        print(f"❌ Error checking account: {e}")
        return False


def validate_data_access():
    """Check data access works."""
    print("\n🔍 Testing data access...")

    try:
        from alpaca_client import AlpacaClient

        client = AlpacaClient(mode='paper')

        # Test price fetch
        price = client.get_latest_price('AAPL')
        if price is None:
            print("❌ Failed to fetch price")
            return False

        print(f"✅ Price data: AAPL @ ${price:.2f}")

        # Test historical bars
        bars = client.get_historical_bars('AAPL', days=20)
        if bars is None or len(bars) == 0:
            print("❌ Failed to fetch historical data")
            return False

        print(f"✅ Historical data: {len(bars)} bars")

        return True

    except Exception as e:
        print(f"❌ Error accessing data: {e}")
        return False


def validate_order_manager():
    """Check order manager works."""
    print("\n🔍 Testing order manager...")

    try:
        from alpaca_client import AlpacaClient
        from order_manager import OrderManager

        client = AlpacaClient(mode='paper')
        manager = OrderManager(client)

        # Check sync
        positions = client.list_positions()
        print(f"✅ Order manager initialized")
        print(f"   Current positions: {len(positions)}")
        print(f"   Pending orders: {manager.get_pending_count()}")

        return True

    except Exception as e:
        print(f"❌ Error with order manager: {e}")
        return False


def validate_rate_limiter():
    """Check rate limiter works."""
    print("\n🔍 Testing rate limiter...")

    try:
        from traderlib.rate_limiter import RateLimiter, health_monitor

        limiter = RateLimiter()
        status = limiter.get_status()

        print(f"✅ Rate limiter initialized")
        print(f"   Requests in window: {status['requests_in_window']}/{status['max_requests']}")
        print(f"   Circuit: {'🔴 OPEN' if status['circuit_open'] else '🟢 CLOSED'}")

        # Test health monitor
        hm_status = health_monitor.get_status()
        print(f"   Providers: alpaca={'✅' if hm_status['providers']['alpaca']['healthy'] else '❌'}, "
              f"yfinance={'✅' if hm_status['providers']['yfinance']['healthy'] else '❌'}")

        return True

    except Exception as e:
        print(f"❌ Error with rate limiter: {e}")
        return False


def run_unit_tests():
    """Run unit tests."""
    print("\n" + "=" * 60)
    print("🧪 RUNNING UNIT TESTS")
    print("=" * 60)
    print()

    try:
        from test_alpaca_integration import run_tests
        return run_tests()
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def print_next_steps():
    """Print next steps."""
    print()
    print("=" * 60)
    print("📋 NEXT STEPS")
    print("=" * 60)
    print()
    print("1. Start the Alpaca trading engine:")
    print("   python3 scripts/paper_engine_alpaca.py")
    print()
    print("2. Monitor in another terminal:")
    print("   python3 scripts/paper_portfolio.py status")
    print("   python3 scripts/paper_portfolio.py live")
    print()
    print("3. For production (real money), use:")
    print("   python3 scripts/paper_engine_alpaca.py --mode live")
    print()
    print("4. To run tests again:")
    print("   python3 tests/test_alpaca_integration.py")
    print()


def main():
    """Run all validations."""
    print("=" * 60)
    print("🔬 ALPACA VALIDATION SUITE")
    print("=" * 60)
    print()

    results = []

    # Run validations
    results.append(('Dependencies', validate_dependencies()))
    results.append(('Credentials', validate_credentials()))
    results.append(('Account', validate_account()))
    results.append(('Data Access', validate_data_access()))
    results.append(('Order Manager', validate_order_manager()))
    results.append(('Rate Limiter', validate_rate_limiter()))

    # Print summary
    print()
    print("=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print()
        print("🎉 All validations passed!")
        print_next_steps()
        return True
    else:
        print()
        print("⚠️  Some validations failed. Please fix the issues above.")
        return False


if __name__ == '__main__':
    success = main()
    if success:
        # Run unit tests too
        print()
        run_unit_tests()
    sys.exit(0 if success else 1)
