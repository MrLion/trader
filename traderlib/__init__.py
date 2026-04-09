"""
TraderLib - Core trading utilities and analysis functions.

This package provides shared utilities for Stage 2 analysis,
entry scoring, and technical indicator calculations.
"""

from .stage2_utils import (
    calculate_stage2_score,
    get_entry_score,
    get_stage2_tier,
)

__version__ = "0.3.0"
__all__ = [
    "calculate_stage2_score",
    "get_entry_score",
    "get_stage2_tier",
]
