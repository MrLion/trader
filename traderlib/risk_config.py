"""Risk configuration management for trading engine.

Loads risk parameters from YAML config with support for:
- Default configuration
- Named profiles (conservative, aggressive, etc.)
- Environment variable overrides
- Runtime validation
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class AccountRiskConfig:
    """Account-level risk settings."""
    risk_per_trade_pct: float = 0.0075  # 0.75%
    daily_loss_limit_pct: float = 0.02   # 2%
    max_sector_positions: int = 3
    max_entries_per_day: int = 10


@dataclass
class PositionRiskConfig:
    """Position-level risk settings."""
    max_position_pct: float = 0.05   # 5%
    min_position_pct: float = 0.005  # 0.5%


@dataclass
class StopLossConfig:
    """Stop loss calculation settings."""
    method: str = "atr_or_support"  # atr, atr_or_support, percent, pivot_based
    fixed_pct: float = 0.07
    atr_period: int = 14
    atr_multiplier: float = 2.0
    min_stop_distance_pct: float = 0.03  # 3%
    max_stop_distance_pct: float = 0.10   # 10%
    fallback_pct: float = 0.07


@dataclass
class ProfitTargetConfig:
    """Profit target and trailing stop settings."""
    min_r_multiple: float = 2.0
    fallback_target_pct: float = 0.10  # 10% above entry
    breakeven_at_r: float = 1.0
    ema10_at_r: float = 1.5
    ema21_at_r: float = 3.0
    ema_short_period: int = 10  # EMA for early trailing
    ema_long_period: int = 21   # EMA for late trailing


@dataclass
class CacheConfig:
    """Cache settings."""
    ttl_seconds: int = 300  # 5 minutes


@dataclass
class EntryConfig:
    """Entry criteria thresholds."""
    min_entry_score: int = 60
    max_dist_to_pivot_pct: float = 1.0
    min_volume_ratio: float = 1.5


@dataclass
class MarketFilterConfig:
    """Market environment filters."""
    max_spy_decline_pct: float = -0.5
    max_vix: Optional[float] = None


@dataclass
class CooldownConfig:
    """Re-entry cooldown settings to prevent chasing losses.

    See: memory/2026-04-11-fly-reentry-lesson.md - FLY case study
    """
    # Minutes to wait before re-entering same ticker after exit
    reentry_cooldown_minutes: int = 60  # 1 hour default

    # Only apply cooldown if previous trade was a loss (set to 0.0 to always apply)
    min_loss_to_trigger_cooldown_pct: float = 0.0  # 0% = any loss triggers cooldown

    # Maximum cooldown after consecutive losses (exponential backoff)
    max_cooldown_minutes: int = 240  # 4 hours cap

    # Increase cooldown multiplier after each consecutive loss on same ticker
    consecutive_loss_multiplier: float = 2.0


@dataclass
class RiskConfig:
    """Complete risk configuration."""
    account: AccountRiskConfig = field(default_factory=AccountRiskConfig)
    position: PositionRiskConfig = field(default_factory=PositionRiskConfig)
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    profit_target: ProfitTargetConfig = field(default_factory=ProfitTargetConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)
    market: MarketFilterConfig = field(default_factory=MarketFilterConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    cooldown: CooldownConfig = field(default_factory=CooldownConfig)


class RiskConfigManager:
    """Manages loading and accessing risk configuration."""

    def __init__(self, config_path: Optional[Path] = None, profile: Optional[str] = None):
        """Initialize with optional config path and profile.

        Args:
            config_path: Path to YAML config file (default: config/risk_config.yaml)
            profile: Named profile to load (default: use base config)
        """
        self.config_path = config_path or self._default_config_path()
        self.profile = profile
        self.config = self._load_config()

    def _default_config_path(self) -> Path:
        """Get default config path relative to repo root."""
        repo_root = Path(__file__).parent.parent
        return repo_root / "config" / "risk_config.yaml"

    def _load_config(self) -> RiskConfig:
        """Load configuration from YAML with optional profile overlay."""
        import yaml

        config = RiskConfig()

        if not self.config_path.exists():
            print(f"⚠️  Risk config not found at {self.config_path}, using defaults")
            return config

        try:
            with open(self.config_path, 'r') as f:
                data = yaml.safe_load(f)

            if data is None:
                return config

            # Load base configuration
            self._apply_config_dict(config, data)

            # Apply profile overlay if specified
            if self.profile and 'profiles' in data:
                profile_data = data['profiles'].get(self.profile)
                if profile_data:
                    print(f"🔧 Applying risk profile: {self.profile}")
                    self._apply_config_dict(config, profile_data)
                else:
                    available = list(data['profiles'].keys())
                    print(f"⚠️  Profile '{self.profile}' not found. Available: {available}")

            # Apply environment variable overrides
            self._apply_env_overrides(config)

            return config

        except Exception as e:
            print(f"⚠️  Error loading risk config: {e}, using defaults")
            return config

    def _apply_config_dict(self, config: RiskConfig, data: Dict):
        """Apply configuration values from dict to config object."""
        if 'account' in data:
            for key, val in data['account'].items():
                if hasattr(config.account, key):
                    setattr(config.account, key, val)

        if 'position' in data:
            for key, val in data['position'].items():
                if hasattr(config.position, key):
                    setattr(config.position, key, val)

        if 'stop_loss' in data:
            sl_data = data['stop_loss']
            for key, val in sl_data.items():
                if key == 'atr':
                    # Handle nested ATR config
                    if 'period' in val:
                        config.stop_loss.atr_period = val['period']
                    if 'multiplier' in val:
                        config.stop_loss.atr_multiplier = val['multiplier']
                elif hasattr(config.stop_loss, key):
                    setattr(config.stop_loss, key, val)

        if 'profit_target' in data:
            pt_data = data['profit_target']
            if 'trailing_stops' in pt_data:
                ts = pt_data['trailing_stops']
                if 'breakeven_at_r' in ts:
                    config.profit_target.breakeven_at_r = ts['breakeven_at_r']
                if 'ema10_at_r' in ts:
                    config.profit_target.ema10_at_r = ts['ema10_at_r']
                if 'ema21_at_r' in ts:
                    config.profit_target.ema21_at_r = ts['ema21_at_r']
            if 'min_r_multiple' in pt_data:
                config.profit_target.min_r_multiple = pt_data['min_r_multiple']
            if 'fallback_target_pct' in pt_data:
                config.profit_target.fallback_target_pct = pt_data['fallback_target_pct']
            if 'ema_periods' in pt_data:
                ema = pt_data['ema_periods']
                if 'short' in ema:
                    config.profit_target.ema_short_period = ema['short']
                if 'long' in ema:
                    config.profit_target.ema_long_period = ema['long']

        if 'cache' in data:
            for key, val in data['cache'].items():
                if hasattr(config.cache, key):
                    setattr(config.cache, key, val)

        if 'entry' in data:
            for key, val in data['entry'].items():
                if hasattr(config.entry, key):
                    setattr(config.entry, key, val)

        if 'market' in data:
            for key, val in data['market'].items():
                if hasattr(config.market, key):
                    setattr(config.market, key, val)

        if 'cooldown' in data:
            for key, val in data['cooldown'].items():
                if hasattr(config.cooldown, key):
                    setattr(config.cooldown, key, val)

    def _apply_env_overrides(self, config: RiskConfig):
        """Apply environment variable overrides.

        Supported overrides:
        - RISK_ACCOUNT_RISK_PCT: Account risk per trade
        - RISK_POSITION_MAX_PCT: Max position size
        - RISK_STOP_MAX_PCT: Max stop distance
        - RISK_PROFILE: Risk profile name
        """
        env_mappings = {
            'RISK_ACCOUNT_RISK_PCT': ('account', 'risk_per_trade_pct', float),
            'RISK_POSITION_MAX_PCT': ('position', 'max_position_pct', float),
            'RISK_STOP_MAX_PCT': ('stop_loss', 'max_stop_distance_pct', float),
            'RISK_STOP_MIN_PCT': ('stop_loss', 'min_stop_distance_pct', float),
            'RISK_DAILY_LOSS_PCT': ('account', 'daily_loss_limit_pct', float),
        }

        for env_var, (section, key, type_fn) in env_mappings.items():
            val = os.environ.get(env_var)
            if val:
                try:
                    section_obj = getattr(config, section)
                    setattr(section_obj, key, type_fn(val))
                    print(f"🔧 ENV override: {env_var}={val}")
                except (ValueError, TypeError) as e:
                    print(f"⚠️  Invalid value for {env_var}: {val} ({e})")

    def get_config(self) -> RiskConfig:
        """Get current configuration."""
        return self.config

    def reload(self):
        """Reload configuration from disk."""
        self.config = self._load_config()

    def print_summary(self):
        """Print configuration summary."""
        cfg = self.config
        print("\n" + "="*50)
        print("RISK CONFIGURATION SUMMARY")
        print("="*50)
        print(f"Profile: {self.profile or 'default'}")
        print(f"Config file: {self.config_path}")
        print("-"*50)
        print(f"Account Risk/Trade: {cfg.account.risk_per_trade_pct*100:.2f}%")
        print(f"Daily Loss Limit:   {cfg.account.daily_loss_limit_pct*100:.2f}%")
        print(f"Max Position Size:  {cfg.position.max_position_pct*100:.2f}%")
        print(f"Min Position Size:  {cfg.position.min_position_pct*100:.2f}%")
        print(f"Stop Method:        {cfg.stop_loss.method}")
        print(f"Max Stop Distance:  {cfg.stop_loss.max_stop_distance_pct*100:.2f}%")
        print(f"Min Stop Distance:  {cfg.stop_loss.min_stop_distance_pct*100:.2f}%")
        print(f"Min R Target:       {cfg.profit_target.min_r_multiple}")
        print(f"Entry Threshold:    {cfg.entry.min_entry_score}")
        print(f"EMA Periods:        {cfg.profit_target.ema_short_period}/{cfg.profit_target.ema_long_period}")
        print(f"Cache TTL:          {cfg.cache.ttl_seconds}s")
        print(f"Cooldown:           {cfg.cooldown.reentry_cooldown_minutes}min (loss threshold: {cfg.cooldown.min_loss_to_trigger_cooldown_pct*100:.1f}%)")
        print("="*50)


def calculate_position_size_with_constraints(
    equity: float,
    entry_price: float,
    stop_price: float,
    config: RiskConfig
) -> tuple[int, dict]:
    """Calculate position size with dual constraint system.

    Args:
        equity: Total account equity
        entry_price: Planned entry price
        stop_price: Planned stop price
        config: Risk configuration

    Returns:
        Tuple of (shares, metadata_dict)
        metadata includes the calculation details for logging
    """
    risk_per_share = entry_price - stop_price
    stop_distance_pct = abs(risk_per_share) / entry_price

    metadata = {
        'entry_price': entry_price,
        'stop_price': stop_price,
        'risk_per_share': risk_per_share,
        'stop_distance_pct': stop_distance_pct * 100,
        'constraints_applied': []
    }

    # Validate stop distance is within limits
    if stop_distance_pct < config.stop_loss.min_stop_distance_pct:
        # Stop is too tight - increase to minimum
        adjusted_stop = entry_price * (1 - config.stop_loss.min_stop_distance_pct)
        risk_per_share = entry_price - adjusted_stop
        stop_distance_pct = config.stop_loss.min_stop_distance_pct
        metadata['adjusted_stop'] = adjusted_stop
        metadata['constraints_applied'].append(f"stop_too_tight_using_min_{config.stop_loss.min_stop_distance_pct*100:.1f}%")

    if stop_distance_pct > config.stop_loss.max_stop_distance_pct:
        # Stop is too wide - reject or cap
        metadata['constraints_applied'].append(f"stop_too_wide_max_{config.stop_loss.max_stop_distance_pct*100:.1f}%")
        metadata['rejected'] = True
        metadata['rejection_reason'] = f"Stop {stop_distance_pct*100:.1f}% exceeds max {config.stop_loss.max_stop_distance_pct*100:.1f}%"
        return 0, metadata

    # Calculate account-risk-based position size
    account_risk_dollars = equity * config.account.risk_per_trade_pct
    shares_by_account_risk = int(account_risk_dollars / risk_per_share) if risk_per_share > 0 else 0

    # Calculate position-cap-based position size
    max_position_value = equity * config.position.max_position_pct
    shares_by_position_cap = int(max_position_value / entry_price)

    # Take the minimum of the two constraints
    shares = min(shares_by_account_risk, shares_by_position_cap)

    # Calculate minimum position (don't take tiny positions)
    min_position_value = equity * config.position.min_position_pct
    min_shares = int(min_position_value / entry_price)

    metadata['shares_by_account_risk'] = shares_by_account_risk
    metadata['shares_by_position_cap'] = shares_by_position_cap
    metadata['position_value'] = shares * entry_price
    metadata['position_pct'] = (shares * entry_price) / equity * 100
    metadata['account_risk_dollars'] = shares * risk_per_share
    metadata['account_risk_pct'] = (shares * risk_per_share) / equity * 100

    if shares < min_shares:
        metadata['constraints_applied'].append(f"below_min_position_{min_shares}_shares")
        return 0, metadata

    # Round to nearest 10 for cleaner numbers (only when shares >= 10)
    if shares >= 10:
        shares = (shares // 10) * 10

    if shares == shares_by_position_cap:
        metadata['constraints_applied'].append("capped_by_position_limit")
    else:
        metadata['constraints_applied'].append("limited_by_account_risk")

    return max(shares, 0), metadata


# Global instance for module-level access
_default_manager: Optional[RiskConfigManager] = None


def get_risk_config(config_path: Optional[Path] = None, profile: Optional[str] = None) -> RiskConfig:
    """Get risk configuration (creates singleton if needed)."""
    global _default_manager
    if _default_manager is None:
        _default_manager = RiskConfigManager(config_path, profile)
    return _default_manager.get_config()


def reload_risk_config():
    """Reload configuration from disk."""
    global _default_manager
    if _default_manager:
        _default_manager.reload()


def print_risk_summary():
    """Print current risk configuration."""
    global _default_manager
    if _default_manager:
        _default_manager.print_summary()
    else:
        RiskConfigManager().print_summary()
