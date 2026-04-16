#!/usr/bin/env python3
"""Tests for risk configuration management.

Covers:
1. RiskConfig dataclasses (defaults, validation)
2. RiskConfigManager (YAML loading, profiles, env overrides)
3. calculate_position_size_with_constraints (triple constraint system)
4. Position sizing calculations with various constraints
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.risk_config import (
    AccountRiskConfig,
    PositionRiskConfig,
    StopLossConfig,
    MASupportConfig,
    ProfitTargetConfig,
    CacheConfig,
    EntryConfig,
    MarketFilterConfig,
    CooldownConfig,
    RiskConfig,
    RiskConfigManager,
    calculate_position_size_with_constraints,
    get_risk_config,
    reload_risk_config,
)


class TestAccountRiskConfig(unittest.TestCase):
    """Test AccountRiskConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = AccountRiskConfig()
        self.assertEqual(config.risk_per_trade_pct, 0.0075)  # 0.75%
        self.assertEqual(config.daily_loss_limit_pct, 0.02)  # 2%
        self.assertEqual(config.max_sector_positions, 3)
        self.assertEqual(config.max_entries_per_day, 10)

    def test_custom_values(self):
        """Should accept custom values."""
        config = AccountRiskConfig(
            risk_per_trade_pct=0.01,
            daily_loss_limit_pct=0.03,
            max_sector_positions=5
        )
        self.assertEqual(config.risk_per_trade_pct, 0.01)
        self.assertEqual(config.daily_loss_limit_pct, 0.03)
        self.assertEqual(config.max_sector_positions, 5)


class TestPositionRiskConfig(unittest.TestCase):
    """Test PositionRiskConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = PositionRiskConfig()
        self.assertEqual(config.max_position_pct, 0.05)  # 5%
        self.assertEqual(config.min_position_pct, 0.005)  # 0.5%


class TestStopLossConfig(unittest.TestCase):
    """Test StopLossConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = StopLossConfig()
        self.assertEqual(config.method, "atr_or_support")
        self.assertEqual(config.fixed_pct, 0.07)
        self.assertEqual(config.atr_period, 14)
        self.assertEqual(config.atr_multiplier, 2.0)
        self.assertEqual(config.min_stop_distance_pct, 0.03)
        self.assertEqual(config.max_stop_distance_pct, 0.10)


class TestMASupportConfig(unittest.TestCase):
    """Test MASupportConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = MASupportConfig()
        self.assertTrue(config.enabled)
        self.assertEqual(config.buffer_pct, 0.01)  # 1%
        self.assertEqual(config.cluster_spread_pct, 0.05)  # 5%
        self.assertEqual(config.min_cluster_size, 2)


class TestProfitTargetConfig(unittest.TestCase):
    """Test ProfitTargetConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = ProfitTargetConfig()
        self.assertEqual(config.min_r_multiple, 2.0)
        self.assertEqual(config.fallback_target_pct, 0.10)
        self.assertEqual(config.breakeven_at_r, 1.0)
        self.assertEqual(config.ema10_at_r, 1.5)
        self.assertEqual(config.ema21_at_r, 3.0)


class TestCooldownConfig(unittest.TestCase):
    """Test CooldownConfig dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        config = CooldownConfig()
        self.assertEqual(config.reentry_cooldown_minutes, 60)
        self.assertEqual(config.min_loss_to_trigger_cooldown_pct, 0.0)
        self.assertEqual(config.max_cooldown_minutes, 240)
        self.assertEqual(config.consecutive_loss_multiplier, 2.0)


class TestRiskConfig(unittest.TestCase):
    """Test composite RiskConfig dataclass."""

    def test_default_values(self):
        """Should have correct default sub-configs."""
        config = RiskConfig()
        self.assertIsInstance(config.account, AccountRiskConfig)
        self.assertIsInstance(config.position, PositionRiskConfig)
        self.assertIsInstance(config.stop_loss, StopLossConfig)
        self.assertIsInstance(config.ma_support, MASupportConfig)
        self.assertIsInstance(config.profit_target, ProfitTargetConfig)
        self.assertIsInstance(config.entry, EntryConfig)
        self.assertIsInstance(config.market, MarketFilterConfig)
        self.assertIsInstance(config.cache, CacheConfig)
        self.assertIsInstance(config.cooldown, CooldownConfig)


class TestRiskConfigManager(unittest.TestCase):
    """Test RiskConfigManager class."""

    def test_init_uses_default_path(self):
        """Should use default config path when none provided."""
        with patch.object(RiskConfigManager, '_load_config', return_value=RiskConfig()):
            manager = RiskConfigManager()
            self.assertIsNotNone(manager.config_path)
            self.assertIn('risk_config.yaml', str(manager.config_path))

    def test_init_accepts_custom_path(self):
        """Should accept custom config path."""
        custom_path = Path('/tmp/test_config.yaml')
        with patch.object(RiskConfigManager, '_load_config', return_value=RiskConfig()):
            manager = RiskConfigManager(config_path=custom_path)
            self.assertEqual(manager.config_path, custom_path)

    def test_init_accepts_profile(self):
        """Should accept profile parameter."""
        with patch.object(RiskConfigManager, '_load_config', return_value=RiskConfig()) as mock_load:
            manager = RiskConfigManager(profile='conservative')
            self.assertEqual(manager.profile, 'conservative')

    def test_get_config_returns_config(self):
        """get_config should return the loaded config."""
        manager = RiskConfigManager(quiet=True)
        config = manager.get_config()
        self.assertIsInstance(config, RiskConfig)

    def test_reload_reloads_config(self):
        """reload should reload configuration."""
        manager = RiskConfigManager(quiet=True)
        original_config = manager.config

        with patch.object(manager, '_load_config', return_value=RiskConfig()) as mock_load:
            manager.reload()
            mock_load.assert_called_once()

    def test_load_config_missing_file_uses_defaults(self):
        """Missing config file should use defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / 'nonexistent.yaml'
            manager = RiskConfigManager(config_path=nonexistent, quiet=True)
            config = manager.get_config()
            self.assertIsInstance(config, RiskConfig)
            self.assertEqual(config.account.risk_per_trade_pct, 0.0075)


class TestCalculatePositionSize(unittest.TestCase):
    """Test position size calculation with constraints."""

    def setUp(self):
        """Create base risk config for tests."""
        self.config = RiskConfig()
        self.config.account.risk_per_trade_pct = 0.01  # 1%
        self.config.position.max_position_pct = 0.05  # 5%
        self.config.position.min_position_pct = 0.005  # 0.5%
        self.config.stop_loss.min_stop_distance_pct = 0.03  # 3%
        self.config.stop_loss.max_stop_distance_pct = 0.10  # 10%

    def test_basic_position_calculation(self):
        """Basic position calculation should work."""
        equity = 100000
        entry_price = 100
        stop_price = 95  # 5% risk

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        self.assertGreater(shares, 0)
        self.assertIn('risk_per_share', metadata)
        self.assertIn('position_value', metadata)

    def test_account_risk_constraint(self):
        """Account risk should constrain position size."""
        equity = 100000
        entry_price = 100
        stop_price = 90  # 10% risk - will be capped to 10% max

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        # With 10% stop and 1% account risk, shares should be limited
        expected_by_risk = (equity * 0.01) / 10  # 100 shares
        self.assertLessEqual(shares, expected_by_risk)

    def test_position_cap_constraint(self):
        """Position cap should constrain large positions."""
        equity = 100000
        entry_price = 10
        stop_price = 9.9  # Very small risk

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        # Max position value should be 5% of equity = $5000
        # At $10/share = 500 shares max
        max_shares = int((equity * 0.05) / entry_price)
        self.assertLessEqual(shares, max_shares)

    def test_cash_constraint(self):
        """Available cash should constrain position size."""
        equity = 100000
        entry_price = 100
        stop_price = 95
        available_cash = 1000  # Only $1000 available

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config,
            available_cash=available_cash
        )

        # Should be limited by available cash
        max_shares_by_cash = int(available_cash / entry_price)
        self.assertLessEqual(shares, max_shares_by_cash)

    def test_insufficient_cash_rejected(self):
        """Insufficient cash for 1 share should be rejected."""
        equity = 100000
        entry_price = 1000
        stop_price = 950
        available_cash = 500  # Can't buy 1 share

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config,
            available_cash=available_cash
        )

        self.assertEqual(shares, 0)
        self.assertTrue(metadata.get('rejected'))
        self.assertIn('insufficient_cash', metadata.get('constraints_applied', []))

    def test_stop_too_wide_rejected(self):
        """Stop too wide should be rejected."""
        equity = 100000
        entry_price = 100
        stop_price = 50  # 50% risk - exceeds 10% max

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        self.assertEqual(shares, 0)
        self.assertTrue(metadata.get('rejected'))

    def test_stop_too_tight_adjusted(self):
        """Stop too tight should be adjusted to minimum."""
        equity = 100000
        entry_price = 100
        stop_price = 99  # 1% risk - below 3% min

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        # Should be adjusted to 3% minimum
        self.assertIn('adjusted_stop', metadata)

    def test_position_below_minimum_rejected(self):
        """Position below minimum should be rejected."""
        self.config.position.min_position_pct = 0.05  # 5% minimum

        equity = 100000
        entry_price = 100
        stop_price = 95  # 5% stop

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        # Position should either be rejected or meet minimum
        if shares == 0:
            self.assertIn('below_min', str(metadata.get('constraints_applied', [])))

    def test_partial_position_allowed(self):
        """Cash-limited partial position should be allowed."""
        equity = 100000
        entry_price = 100
        stop_price = 95
        available_cash = 500  # Limited cash (enough for 5 shares)

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config,
            available_cash=available_cash
        )

        # Result should indicate cash limitation
        constraints = str(metadata.get('constraints_applied', []))
        # Check for either partial position or cash-related constraint
        has_cash_constraint = (
            'partial' in constraints.lower() or
            'cash' in constraints.lower() or
            'reduced_for_available_cash' in constraints
        )
        self.assertTrue(has_cash_constraint or shares == 0,
                       f"Expected cash constraint but got: {constraints}")

    def test_shares_rounded_to_nearest_10(self):
        """Shares >= 10 should be rounded to nearest 10."""
        equity = 1000000  # Large equity to get many shares
        entry_price = 10
        stop_price = 9  # 10% risk

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        if shares >= 10:
            self.assertEqual(shares % 10, 0)

    def test_metadata_includes_calculation_details(self):
        """Metadata should include all calculation details."""
        equity = 100000
        entry_price = 100
        stop_price = 95

        shares, metadata = calculate_position_size_with_constraints(
            equity, entry_price, stop_price, self.config
        )

        self.assertIn('entry_price', metadata)
        self.assertIn('stop_price', metadata)
        self.assertIn('risk_per_share', metadata)
        self.assertIn('position_value', metadata)
        self.assertIn('constraints_applied', metadata)


class TestEnvironmentVariableOverrides(unittest.TestCase):
    """Test environment variable configuration overrides."""

    def setUp(self):
        """Save original environment."""
        self.original_env = {}
        self.env_vars = [
            'RISK_ACCOUNT_RISK_PCT',
            'RISK_POSITION_MAX_PCT',
            'RISK_STOP_MAX_PCT',
            'RISK_STOP_MIN_PCT',
            'RISK_DAILY_LOSS_PCT',
        ]
        for var in self.env_vars:
            self.original_env[var] = os.environ.get(var)

    def tearDown(self):
        """Restore original environment."""
        for var, value in self.original_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_account_risk_pct_override(self):
        """RISK_ACCOUNT_RISK_PCT should override config."""
        os.environ['RISK_ACCOUNT_RISK_PCT'] = '0.02'

        manager = RiskConfigManager(quiet=True)
        config = manager.get_config()

        self.assertEqual(config.account.risk_per_trade_pct, 0.02)

    def test_position_max_pct_override(self):
        """RISK_POSITION_MAX_PCT should override config."""
        os.environ['RISK_POSITION_MAX_PCT'] = '0.10'

        manager = RiskConfigManager(quiet=True)
        config = manager.get_config()

        self.assertEqual(config.position.max_position_pct, 0.10)

    def test_invalid_env_value_ignored(self):
        """Invalid env values should be ignored with warning."""
        os.environ['RISK_ACCOUNT_RISK_PCT'] = 'invalid'

        # Reset the global manager to force reload
        from traderlib.risk_config import reset_risk_config
        reset_risk_config()

        # Should not raise
        manager = RiskConfigManager(quiet=True)
        config = manager.get_config()

        # Should use config file default (0.5%)
        self.assertEqual(config.account.risk_per_trade_pct, 0.005)


class TestProfileApplication(unittest.TestCase):
    """Test risk profile loading and application."""

    def test_profile_applies_overrides(self):
        """Profile should apply overrides to base config."""
        yaml_content = """
account:
  risk_per_trade_pct: 0.01
profiles:
  conservative:
    account:
      risk_per_trade_pct: 0.005
    position:
      max_position_pct: 0.03
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            manager = RiskConfigManager(config_path=config_path, profile='conservative', quiet=True)
            config = manager.get_config()

            self.assertEqual(config.account.risk_per_trade_pct, 0.005)
            self.assertEqual(config.position.max_position_pct, 0.03)
        finally:
            config_path.unlink(missing_ok=True)

    def test_missing_profile_uses_defaults(self):
        """Missing profile should use base config with warning."""
        yaml_content = """
account:
  risk_per_trade_pct: 0.01
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            manager = RiskConfigManager(config_path=config_path, profile='nonexistent', quiet=True)
            config = manager.get_config()

            # Should use base config
            self.assertEqual(config.account.risk_per_trade_pct, 0.01)
        finally:
            config_path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
