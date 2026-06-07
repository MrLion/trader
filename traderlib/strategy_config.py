"""Strategy-specific configuration loader.

Each strategy has its own YAML file under config/strategies/<name>.yaml.
This keeps strategy tuning parameters separate from account-level risk
settings in risk_config.yaml.

Usage:
    from traderlib.strategy_config import load_strategy_config, get_param

    cfg = load_strategy_config('stage2_momentum')
    trail_ma = get_param(cfg, 'exit', 'phase2_trail_ma', default=20)
"""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from traderlib.paths import project_root

_CONFIG_DIR = project_root() / 'config' / 'strategies'


def load_strategy_config(strategy_name: str) -> Optional[Dict[str, Any]]:
    """Load strategy config from config/strategies/<strategy_name>.yaml.

    Returns None if the file does not exist so callers can fall back to
    risk_config defaults gracefully.

    Args:
        strategy_name: Strategy identifier, e.g. 'stage2_momentum'.

    Returns:
        Parsed YAML dict, or None if the file is missing.
    """
    path = _CONFIG_DIR / f'{strategy_name}.yaml'
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def get_param(config: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """Safely retrieve a value from a nested config dict.

    Example:
        get_param(cfg, 'exit', 'phase2_trail_ma', default=20)  # cfg['exit']['phase2_trail_ma']

    Args:
        config: Config dict (may be None — returns default immediately).
        *keys:  Sequence of nested keys to traverse.
        default: Value returned when any key is missing or config is None.

    Returns:
        The nested value, or default.
    """
    if config is None:
        return default
    val: Any = config
    for key in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(key)
        if val is None:
            return default
    return val
