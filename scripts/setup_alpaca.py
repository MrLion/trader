#!/usr/bin/env python3
"""Setup script for Alpaca API configuration."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/config')
CONFIG_FILE = CONFIG_DIR / 'alpaca_config.json'


def setup():
    print("🔌 Alpaca API Setup")
    print("=" * 60)
    print()
    print("You need Alpaca API credentials to use the real-time trading engine.")
    print()
    print("Get your keys from: https://app.alpaca.markets/paper/dashboard")
    print()

    # Check if already configured
    if os.getenv('ALPACA_API_KEY'):
        print("✅ Environment variable ALPACA_API_KEY is already set")
        use_env = input("Use environment variables? (y/n): ").lower() == 'y'
        if use_env:
            print("\n✅ Using environment variables for API credentials")
            return

    if CONFIG_FILE.exists():
        print(f"⚠️ Config file already exists: {CONFIG_FILE}")
        overwrite = input("Overwrite? (y/n): ").lower() == 'y'
        if not overwrite:
            return

    # Get credentials
    print("\n📋 Enter your Alpaca credentials:")
    print("(Leave blank if you only want to use environment variables)")
    print()

    api_key = input("Paper API Key: ").strip()
    secret_key = input("Paper Secret Key: ").strip()

    if not api_key or not secret_key:
        print("\n⚠️ No credentials entered.")
        print("Set environment variables instead:")
        print("  export ALPACA_API_KEY='your_key'")
        print("  export ALPACA_SECRET_KEY='your_secret'")
        return

    # Historical data configuration
    print("\n📊 Historical Data Configuration:")
    print("  Default is 365 days (needed for full Stage 2 scoring)")
    print("  Use 90 days if you want faster analysis with limited history")
    days_input = input("Historical days [365]: ").strip()
    historical_days = int(days_input) if days_input else 365

    # Create config
    config = {
        "_comment": "Alpaca API credentials - NEVER commit this file!",
        "paper": {
            "api_key": api_key,
            "secret_key": secret_key,
            "base_url": "https://paper-api.alpaca.markets"
        },
        "live": {
            "api_key": "",
            "secret_key": "",
            "base_url": "https://api.alpaca.markets"
        },
        "data_feed": "iex",
        "historical_days": historical_days,
        "mode": "paper"
    }

    # Save config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    # Set permissions (owner read/write only)
    os.chmod(CONFIG_FILE, 0o600)

    print()
    print(f"✅ Config saved to: {CONFIG_FILE}")
    print("   Permissions: 600 (owner read/write only)")
    print()
    print("🔒 Security: This file is gitignored and will not be committed.")
    print()
    print("Next steps:")
    print("  1. Test the connection:")
    print("     python3 scripts/alpaca_client.py")
    print()
    print("  2. Start the Alpaca trading engine:")
    print("     python3 scripts/paper_engine_alpaca.py")


def test_connection():
    """Test Alpaca connection."""
    print("🔍 Testing Alpaca connection...")
    print()

    try:
        from alpaca_client import AlpacaClient

        client = AlpacaClient(mode='paper')
        account = client.get_account()

        print("✅ Connection successful!")
        print()
        print("📊 Account Info:")
        print(f"   Status: {account['status']}")
        print(f"   Cash: ${account['cash:,.2f']}")
        print(f"   Equity: ${account['equity:,.2f']}")
        print(f"   Buying Power: ${account['buying_power:,.2f']}")

        # Check positions
        positions = client.list_positions()
        print()
        print(f"📋 Open Positions: {len(positions)}")
        for p in positions:
            print(f"   {p['symbol']}: {p['qty']} shares")

        return True

    except ValueError as e:
        print(f"❌ {e}")
        print()
        print("To configure Alpaca, run:")
        print("   python3 scripts/setup_alpaca.py")
        return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        test_connection()
    else:
        setup()
