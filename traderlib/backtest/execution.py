"""Execution model for backtesting.

Deterministic, conservative fill simulation with slippage.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    """Configuration for execution simulation."""
    slippage_bps: float = 5.0             # 5 basis points one-way


@dataclass(frozen=True)
class FillResult:
    """Result of a simulated order fill."""
    ticker: str
    side: str           # 'BUY' or 'SELL'
    shares: int
    intended_price: float
    fill_price: float
    total_cost: float   # For BUY: fill_price * shares
                        # For SELL: fill_price * shares


class ExecutionModel:
    """Simulates order fills with slippage.

    Deterministic: same inputs always produce same outputs.
    Conservative: always assumes unfavorable price movement.
    """

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()

    def simulate_fill(self, ticker: str, side: str, shares: int,
                      reference_price: float) -> FillResult:
        """Simulate an order fill with realistic execution costs.

        BUY fills at reference * (1 + slippage) — you pay more.
        SELL fills at reference * (1 - slippage) — you receive less.

        Args:
            ticker: Stock symbol
            side: 'BUY' or 'SELL'
            shares: Number of shares
            reference_price: The reference price (e.g., T+1 open)

        Returns:
            FillResult with execution details
        """
        slippage_mult = self.config.slippage_bps / 10000  # Convert bps to decimal

        if side == 'BUY':
            fill_price = round(reference_price * (1 + slippage_mult), 4)
        else:
            fill_price = round(reference_price * (1 - slippage_mult), 4)

        total_cost = fill_price * shares

        return FillResult(
            ticker=ticker,
            side=side,
            shares=shares,
            intended_price=reference_price,
            fill_price=fill_price,
            total_cost=total_cost,
        )