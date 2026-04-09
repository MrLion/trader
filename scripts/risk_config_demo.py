#!/usr/bin/env python3
"""Demo script showing the flexible risk configuration system.

Usage:
    python scripts/risk_config_demo.py
    python scripts/risk_config_demo.py --profile conservative
    python scripts/risk_config_demo.py --profile tight_stops
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.risk_config import (
    RiskConfigManager,
    calculate_position_size_with_constraints
)


def demo_position_sizing():
    """Demonstrate position sizing with different stop distances."""
    print("\n" + "="*70)
    print("POSITION SIZING DEMONSTRATION")
    print("="*70)

    equity = 100_000
    entry_price = 150.00

    # Test different stop scenarios
    scenarios = [
        ("Tight stop (3%)", entry_price * 0.97, "Good for high-conviction setups"),
        ("Normal stop (7%)", entry_price * 0.93, "Standard ATR-based stop"),
        ("Wide stop (12%)", entry_price * 0.88, "Volatility expansion"),
        ("Very wide (18%)", entry_price * 0.82, "Should be rejected by max_stop"),
    ]

    manager = RiskConfigManager()
    config = manager.get_config()

    print(f"\nAccount Equity: ${equity:,.0f}")
    print(f"Account Risk per Trade: {config.account.risk_per_trade_pct*100:.2f}%")
    print(f"Max Position Size: {config.position.max_position_pct*100:.1f}%")
    print(f"Max Stop Distance: {config.stop_loss.max_stop_distance_pct*100:.1f}%")
    print(f"Min Stop Distance: {config.stop_loss.min_stop_distance_pct*100:.1f}%")

    for name, stop_price, note in scenarios:
        print(f"\n--- {name} ---")
        print(f"Stop: ${stop_price:.2f}")
        print(f"Note: {note}")

        shares, meta = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, config
        )

        if meta.get('rejected'):
            print(f"❌ REJECTED: {meta['rejection_reason']}")
        else:
            stop_dist = (entry_price - stop_price) / entry_price * 100
            position_pct = meta['position_pct']
            account_risk = meta['account_risk_pct']

            print(f"✅ Shares: {shares}")
            print(f"   Stop Distance: {stop_dist:.1f}%")
            print(f"   Position Value: ${meta['position_value']:,.0f} ({position_pct:.1f}% of equity)")
            print(f"   Account Risk: ${meta['account_risk_dollars']:,.2f} ({account_risk:.2f}%)")
            print(f"   Constraint: {meta['constraints_applied'][-1] if meta['constraints_applied'] else 'account_risk'}")


def demo_risk_profiles():
    """Demonstrate different risk profiles."""
    print("\n" + "="*70)
    print("RISK PROFILE COMPARISON")
    print("="*70)

    profiles = [None, "conservative", "aggressive", "tight_stops"]
    equity = 100_000
    entry_price = 150.00
    stop_price = 140.50  # ~6.3% stop

    print(f"\nTest Scenario:")
    print(f"  Equity: ${equity:,.0f}")
    print(f"  Entry: ${entry_price:.2f}")
    print(f"  Stop: ${stop_price:.2f} ({(entry_price-stop_price)/entry_price*100:.1f}% away)")

    for profile in profiles:
        name = profile or "default"
        print(f"\n{'='*40}")
        print(f"Profile: {name.upper()}")
        print('='*40)

        manager = RiskConfigManager(profile=profile)
        config = manager.get_config()

        print(f"  Account Risk: {config.account.risk_per_trade_pct*100:.2f}%")
        print(f"  Max Position: {config.position.max_position_pct*100:.1f}%")
        print(f"  Max Stop: {config.stop_loss.max_stop_distance_pct*100:.1f}%")

        shares, meta = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, config
        )

        if meta.get('rejected'):
            print(f"  ❌ REJECTED: {meta['rejection_reason']}")
        else:
            print(f"  ✅ Shares: {shares}")
            print(f"     Position: ${meta['position_pct']:.1f}% of account")
            print(f"     Risk: ${meta['account_risk_dollars']:,.2f}")


def demo_environment_overrides():
    """Demonstrate environment variable overrides."""
    print("\n" + "="*70)
    print("ENVIRONMENT VARIABLE OVERRIDES")
    print("="*70)

    import os

    # Set an override
    os.environ['RISK_ACCOUNT_RISK_PCT'] = '0.005'  # 0.5%
    os.environ['RISK_POSITION_MAX_PCT'] = '0.03'    # 3%

    print("\nSetting environment variables:")
    print("  RISK_ACCOUNT_RISK_PCT=0.005")
    print("  RISK_POSITION_MAX_PCT=0.03")

    manager = RiskConfigManager()
    config = manager.get_config()

    print(f"\nResulting configuration:")
    print(f"  Account Risk: {config.account.risk_per_trade_pct*100:.2f}%")
    print(f"  Max Position: {config.position.max_position_pct*100:.1f}%")

    # Clean up
    del os.environ['RISK_ACCOUNT_RISK_PCT']
    del os.environ['RISK_POSITION_MAX_PCT']


def main():
    parser = argparse.ArgumentParser(description='Risk Configuration Demo')
    parser.add_argument('--profile', type=str, default=None,
                        help='Risk profile to use')
    parser.add_argument('--demo', choices=['sizing', 'profiles', 'env', 'all'],
                        default='all', help='Which demo to run')
    args = parser.parse_args()

    if args.profile:
        print(f"\n🔧 Using risk profile: {args.profile}")
        manager = RiskConfigManager(profile=args.profile)
        manager.print_summary()

    if args.demo in ['sizing', 'all']:
        demo_position_sizing()

    if args.demo in ['profiles', 'all']:
        demo_risk_profiles()

    if args.demo in ['env', 'all']:
        demo_environment_overrides()

    print("\n" + "="*70)
    print("Demo complete!")
    print("="*70)
    print("\nTo use in paper engine:")
    print("  python scripts/paper_engine_alpaca.py --risk-profile conservative")
    print("\nTo see risk summary:")
    print("  python scripts/paper_engine_alpaca.py --risk-summary")


if __name__ == "__main__":
    main()
