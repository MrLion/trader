"""
TraderLib - Core trading utilities and analysis functions.

This package provides shared utilities for Stage 2 analysis,
entry scoring, and technical indicator calculations.
"""

from .stage2_utils import (
    calculate_stage2_score,
    get_entry_score,
    get_stage2_tier,
    get_stage2_details,
    calculate_ma_support_stop,
)
from .risk_config import (
    RiskConfig,
    RiskConfigManager,
    calculate_position_size_with_constraints,
    reset_risk_config,
)

__version__ = "0.3.1"
__all__ = [
    "calculate_stage2_score",
    "get_entry_score",
    "get_stage2_tier",
    "get_stage2_details",
    "calculate_ma_support_stop",
    "RiskConfig",
    "RiskConfigManager",
    "calculate_position_size_with_constraints",
    "reset_risk_config",
]
