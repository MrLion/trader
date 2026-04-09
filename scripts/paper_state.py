#!/usr/bin/env python3
"""Paper trading state management - positions, account, and persistence."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Data paths - configurable via environment variable for testing
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
POSITIONS_FILE = DATA_DIR / 'paper_positions.json'
ACCOUNT_FILE = DATA_DIR / 'paper_account.json'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'

# Trading limits - configurable via environment variables
MAX_SECTOR_POSITIONS = int(os.environ.get('MAX_SECTOR_POSITIONS', '3'))


@dataclass
class Position:
    """Represents an open paper trade position."""
    ticker: str
    status: str  # 'OPEN', 'CLOSED'
    entry_date: str
    entry_price: float
    shares: int
    stop_price: float
    target_price: float
    initial_risk: float
    sector: str
    current_stop_type: str = 'HARD'  # HARD, BREAKEVEN, EMA10, EMA21
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None

    @property
    def position_value(self) -> float:
        return self.entry_price * self.shares

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        # Map Alpaca field names to internal field names
        field_map = {
            'symbol': 'ticker',
            'avg_entry_price': 'entry_price',
            'qty': 'shares',
            'unrealized_pl': 'unrealized_pnl',
        }
        mapped_data = {}
        for k, v in data.items():
            # Map Alpaca field names to internal names
            internal_key = field_map.get(k, k)
            if internal_key in cls.__dataclass_fields__:
                mapped_data[internal_key] = v

        # Provide defaults for required fields not in Alpaca data
        if 'status' not in mapped_data:
            mapped_data['status'] = 'OPEN'
        if 'entry_date' not in mapped_data:
            mapped_data['entry_date'] = datetime.now().isoformat()
        if 'stop_price' not in mapped_data:
            # Default to 5% below entry (will be recalculated properly)
            entry = mapped_data.get('entry_price', 0)
            mapped_data['stop_price'] = entry * 0.95 if entry else 0
        if 'target_price' not in mapped_data:
            # Default to 2x risk (will be recalculated properly)
            entry = mapped_data.get('entry_price', 0)
            stop = mapped_data.get('stop_price', entry * 0.95)
            risk = entry - stop if entry and stop else entry * 0.05
            mapped_data['target_price'] = entry + (risk * 2) if entry else entry
        if 'initial_risk' not in mapped_data:
            entry = mapped_data.get('entry_price', 0)
            stop = mapped_data.get('stop_price', entry * 0.95)
            shares = mapped_data.get('shares', 0)
            mapped_data['initial_risk'] = (entry - stop) * shares if entry and stop else 0
        if 'sector' not in mapped_data:
            mapped_data['sector'] = 'Unknown'

        return cls(**mapped_data)


class PaperState:
    """Manages paper trading state - positions, account, and persistence."""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.cash = initial_capital
        self.day_pnl = 0.0
        self.trade_count = 0
        self.entries_today = 0
        self.last_entry_reset = datetime.now().strftime('%Y-%m-%d')

        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing state if available
        self._load_state()

    def _load_state(self):
        """Load positions and account from disk."""
        # Load positions
        if POSITIONS_FILE.exists():
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    data = json.load(f)
                    # Handle both dict format (from paper_state) and list format (from Alpaca/sync_state)
                    if isinstance(data, list):
                        # Alpaca format: list of position dicts with 'symbol' key
                        for pos_data in data:
                            ticker = pos_data.get('symbol')
                            if ticker:
                                self.positions[ticker] = Position.from_dict(pos_data)
                    else:
                        # Internal format: dict with ticker as key
                        for ticker, pos_data in data.items():
                            self.positions[ticker] = Position.from_dict(pos_data)
            except Exception as e:
                print(f"⚠️ Error loading positions: {e}")

        # Load account
        if ACCOUNT_FILE.exists():
            try:
                with open(ACCOUNT_FILE, 'r') as f:
                    data = json.load(f)
                    self.cash = data.get('cash', self.initial_capital)
                    self.day_pnl = data.get('day_pnl', 0.0)
                    self.trade_count = data.get('trade_count', 0)
                    self.entries_today = data.get('entries_today', 0)
                    self.last_entry_reset = data.get('last_entry_reset', datetime.now().strftime('%Y-%m-%d'))
            except Exception as e:
                print(f"⚠️ Error loading account: {e}")

        # Reset daily counters if new day
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_entry_reset != current_date:
            self.day_pnl = 0.0
            self.entries_today = 0
            self.last_entry_reset = current_date

    def save_state(self):
        """Save current state to disk."""
        # Save positions
        positions_dict = {ticker: pos.to_dict() for ticker, pos in self.positions.items()}
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(positions_dict, f, indent=2)

        # Save account
        account_data = {
            'initial_capital': self.initial_capital,
            'cash': self.cash,
            'equity': self.get_equity(),
            'day_pnl': self.day_pnl,
            'day_return_pct': (self.day_pnl / self.initial_capital) * 100 if self.initial_capital else 0,
            'trade_count': self.trade_count,
            'entries_today': self.entries_today,
            'last_entry_reset': self.last_entry_reset,
            'open_positions': len(self.positions),
            'timestamp': datetime.now().isoformat()
        }
        with open(ACCOUNT_FILE, 'w') as f:
            json.dump(account_data, f, indent=2)

    def get_equity(self) -> float:
        """Calculate total equity (cash + position values)."""
        # Phase 1: Use entry price for simplicity
        # Phase 2: Will fetch live prices
        position_value = sum(
            pos.entry_price * pos.shares for pos in self.positions.values()
        )
        return self.cash + position_value

    def get_sector_counts(self) -> Dict[str, int]:
        """Count positions per sector."""
        counts = {}
        for pos in self.positions.values():
            counts[pos.sector] = counts.get(pos.sector, 0) + 1
        return counts

    def can_enter_position(self, sector: str, position_value: float) -> tuple:
        """Check if entry is allowed based on risk rules."""
        equity = self.get_equity()

        # Check daily entry limit
        if self.entries_today >= 10:
            return False, "Daily entry limit reached (10)"

        # Check sector limit
        sector_counts = self.get_sector_counts()
        if sector_counts.get(sector, 0) >= MAX_SECTOR_POSITIONS:
            return False, f"Sector limit reached ({MAX_SECTOR_POSITIONS} in {sector})"

        # Check position size limit (20% of equity)
        if position_value > equity * 0.20:
            return False, f"Position size {position_value:,.0f} exceeds 20% of equity"

        # Check buying power
        if position_value > self.cash:
            return False, f"Insufficient cash (${self.cash:,.2f} < ${position_value:,.2f})"

        # Check daily loss limit (-2%)
        if self.day_pnl < -0.02 * self.initial_capital:
            return False, f"Daily loss limit hit (${self.day_pnl:,.2f})"

        return True, "OK"

    def enter_position(self, ticker: str, entry_price: float, shares: int,
                     stop_price: float, target_price: float, sector: str) -> Position:
        """Create and record a new position."""
        position_value = entry_price * shares
        initial_risk = (entry_price - stop_price) * shares

        position = Position(
            ticker=ticker,
            status='OPEN',
            entry_date=datetime.now().isoformat(),
            entry_price=entry_price,
            shares=shares,
            stop_price=stop_price,
            target_price=target_price,
            initial_risk=initial_risk,
            sector=sector
        )

        self.positions[ticker] = position
        self.cash -= position_value
        self.entries_today += 1
        self.trade_count += 1

        self.save_state()
        self._log_trade('ENTRY', position)

        return position

    def close_position(self, ticker: str, exit_price: float, reason: str) -> Optional[Position]:
        """Close an open position."""
        if ticker not in self.positions:
            return None

        pos = self.positions[ticker]

        # Calculate P&L
        realized_pnl = (exit_price - pos.entry_price) * pos.shares

        # Update position
        pos.status = 'CLOSED'
        pos.exit_price = exit_price
        pos.exit_date = datetime.now().isoformat()
        pos.exit_reason = reason
        pos.realized_pnl = realized_pnl

        # Update account
        self.cash += exit_price * pos.shares
        self.day_pnl += realized_pnl

        # Remove from open positions
        del self.positions[ticker]

        self.save_state()
        self._log_trade('EXIT', pos)

        return pos

    def update_stop(self, ticker: str, new_stop: float, stop_type: str):
        """Update stop price for a position."""
        if ticker in self.positions:
            self.positions[ticker].stop_price = new_stop
            self.positions[ticker].current_stop_type = stop_type
            self.save_state()

    def _log_trade(self, event_type: str, position: Position):
        """Append trade to history log."""
        trade_record = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            'ticker': position.ticker,
            'entry_price': position.entry_price,
            'exit_price': position.exit_price,
            'shares': position.shares,
            'realized_pnl': position.realized_pnl,
            'exit_reason': position.exit_reason,
            'stop_type': position.current_stop_type
        }

        with open(TRADES_FILE, 'a') as f:
            f.write(json.dumps(trade_record) + '\n')

    def get_open_positions(self) -> List[Position]:
        """Return list of open positions."""
        return list(self.positions.values())

    def get_stats(self) -> dict:
        """Return trading statistics."""
        return {
            'cash': self.cash,
            'equity': self.get_equity(),
            'open_positions': len(self.positions),
            'day_pnl': self.day_pnl,
            'total_trades': self.trade_count,
            'entries_today': self.entries_today,
            'day_return_pct': (self.day_pnl / self.initial_capital) * 100
        }
