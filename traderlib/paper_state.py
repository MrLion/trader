#!/usr/bin/env python3
"""Paper trading state management - positions, account, and persistence."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field


def _atomic_write_json(filepath: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename.

    Prevents data corruption if process crashes during write.
    FINDING-009: Concurrent file writes protection.
    """
    filepath = Path(filepath)
    dir_name = filepath.parent

    # Write to temp file in same directory (atomic rename requires same filesystem)
    fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        # Atomic rename - replaces target file only if write succeeds
        os.replace(temp_path, filepath)
    except Exception:
        # Clean up temp file on any error
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise

# Data paths - configurable via environment variable for testing
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
POSITIONS_FILE = DATA_DIR / 'paper_positions.json'
DAILY_TRACKER_FILE = DATA_DIR / 'daily_tracker.json'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'

# Trading limits - configurable via environment variables
MAX_SECTOR_POSITIONS = int(os.environ.get('MAX_SECTOR_POSITIONS', '3'))

# PHASE 3: Data validation constants
# These values prevent obviously fake/test data from being logged
VALIDATION = {
    'MAX_ENTRY_PRICE': float(os.environ.get('PAPER_MAX_ENTRY_PRICE', '5000.0')),
    'MAX_SHARES': int(os.environ.get('PAPER_MAX_SHARES', '500')),
    'MAX_POSITION_VALUE': float(os.environ.get('PAPER_MAX_POSITION_VALUE', '50000.0')),
    'MAX_PNL_ABS': float(os.environ.get('PAPER_MAX_PNL_ABS', '10000.0')),
    'SKIP_VALIDATION': os.environ.get('PAPER_SKIP_VALIDATION', 'false').lower() == 'true'
}


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
    exit_phase: str = 'phase1'  # 'phase1' = ratchet mode | 'phase2' = EMA trail mode
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    # FINDING-013: Immutable initial stop - never changes after entry
    # Used for accurate R-multiple calculation regardless of stop ratcheting
    initial_stop_price: Optional[float] = None
    entry_min_r: Optional[float] = None  # min_r_multiple from config at entry time
    # NEW: Scale-out tracking for hybrid trailing mode
    # Records R-levels at which scale-outs were executed to prevent duplicate triggers
    scale_out_history: list = field(default_factory=list)

    def record_scale_out(self, r_level: float):
        """Record that a scale-out occurred at the given R-level.

        Used by hybrid trailing mode to track which scale-out steps have
        been executed, preventing duplicate sales at the same R-level.

        Args:
            r_level: The R-multiple that triggered the scale-out (e.g., 3.0).
                     Rounded to 6 decimal places for safe float comparison.
        """
        rounded = round(r_level, 6)
        if rounded not in self.scale_out_history:
            self.scale_out_history.append(rounded)

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
        if 'sector' not in mapped_data:
            mapped_data['sector'] = 'Unknown'

        # DANGEROUS FALLBACK FIX: Don't silently default stop_price to 5% below entry
        # Missing stop_price means position is UNSYNCED - must be explicitly set
        if 'stop_price' not in mapped_data or mapped_data['stop_price'] is None:
            # Mark as UNSYNCED - requires manual review or explicit stop setting
            mapped_data['stop_price'] = 0.0
            mapped_data['current_stop_type'] = 'UNSYNCED'

        # Only calculate target/initial_risk if stop_price is valid
        if 'target_price' not in mapped_data:
            entry = mapped_data.get('entry_price', 0)
            stop = mapped_data.get('stop_price', 0)
            if entry and stop and stop > 0:
                risk = entry - stop
                mapped_data['target_price'] = entry + (risk * 2)
            else:
                # No target without valid stop
                mapped_data['target_price'] = 0.0

        # Validate/recalculate initial_risk
        entry = mapped_data.get('entry_price', 0)
        stop = mapped_data.get('stop_price', 0)
        shares = mapped_data.get('shares', 0)

        if 'initial_risk' not in mapped_data or mapped_data['initial_risk'] == 0:
            # Recalculate if missing or zero (but only if we have valid data)
            if entry and stop and shares and stop > 0:
                calculated_risk = (entry - stop) * shares
                # Only update if we calculated a non-zero value, or if entry == stop (breakeven)
                mapped_data['initial_risk'] = calculated_risk
            elif 'initial_risk' not in mapped_data:
                mapped_data['initial_risk'] = 0.0

        # FINDING-013: Migration - set initial_stop_price if missing
        # Use stop_price as the source of truth for initial stop
        # This handles legacy positions created before this field existed
        if 'initial_stop_price' not in mapped_data or mapped_data['initial_stop_price'] is None:
            if stop and stop > 0:
                mapped_data['initial_stop_price'] = stop
            else:
                mapped_data['initial_stop_price'] = None

        return cls(**mapped_data)


class PaperState:
    """Manages paper trading state - positions, account, and persistence.

    Note: Cash is fetched from Alpaca API, not stored locally (avoids stale data).
    Only daily tracker (last_entry_reset) is persisted.
    """

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.cash = initial_capital  # Will be fetched from API when needed
        self.day_pnl = 0.0
        self.trade_count = 0
        self.entries_today = 0
        self.last_entry_reset = datetime.now().strftime('%Y-%m-%d')

        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing state if available
        self._load_state()

    def _load_state(self):
        """Load positions from disk and daily tracker."""
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

        # Load daily tracker (for last_entry_reset only)
        if DAILY_TRACKER_FILE.exists():
            try:
                with open(DAILY_TRACKER_FILE, 'r') as f:
                    data = json.load(f)
                    self.last_entry_reset = data.get('last_entry_reset', datetime.now().strftime('%Y-%m-%d'))
            except Exception as e:
                print(f"⚠️ Error loading daily tracker: {e}")

        # Reset daily counters if new day
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_entry_reset != current_date:
            self.day_pnl = 0.0
            self.entries_today = 0
            self.last_entry_reset = current_date
            self._save_daily_tracker()

        # Reconcile counters with trade log (source of truth)
        self._reconcile_counters_from_log()

    def _is_test_trade(self, trade: dict) -> bool:
        """Detect test trades using metadata patterns."""
        meta = trade.get('_meta', {})
        ticker = trade.get('ticker', '')
        price = trade.get('entry_price', 0)

        # Explicit test mode flag
        if meta.get('test_mode'):
            return True

        # Known test pattern: AAPL at exactly $150.00 (synthetic test price)
        # This catches trades even if validation was bypassed or passed
        if ticker == 'AAPL' and price == 150.0:
            return True

        # Known test patterns in validation failures
        if meta.get('validation_failed'):
            # Other known test tickers at suspicious prices
            if ticker in ('MSFT', 'GOOGL', 'STOCK0', 'STOCK1', 'STOCK2'):
                return True

        return False

    def _reconcile_counters_from_log(self) -> dict:
        """
        Reconcile counters with trade log, excluding test trades.
        Called during _load_state to ensure accuracy.
        Returns stats for reporting.
        """
        if not TRADES_FILE.exists():
            return {'error': 'No trade log file'}

        today = datetime.now().strftime('%Y-%m-%d')
        stats = {
            'total_trades': 0,
            'production_trades': 0,
            'test_trades': 0,
            'entries_today': 0,
            'production_entries_today': 0,
            'day_pnl': 0.0,
        }

        try:
            with open(TRADES_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trade = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    stats['total_trades'] += 1

                    if self._is_test_trade(trade):
                        stats['test_trades'] += 1
                        continue

                    stats['production_trades'] += 1

                    ts = trade.get('timestamp', '')
                    is_today = ts.startswith(today)

                    # Count today's production entries
                    if trade.get('event') == 'ENTRY' and is_today:
                        stats['production_entries_today'] += 1

                    # Sum today's realized P&L for day_pnl recovery
                    if trade.get('event') == 'EXIT' and is_today:
                        pnl = trade.get('realized_pnl')
                        if pnl is not None:
                            stats['day_pnl'] += pnl

        except Exception as e:
            return {'error': f'Failed to read trade log: {e}'}

        # Update state counters to match log
        self.trade_count = stats['production_trades']
        self.entries_today = stats['production_entries_today']
        self.day_pnl = stats['day_pnl']

        return stats

    def save_state(self):
        """Save current state to disk (positions + daily tracker only).

        Uses atomic writes to prevent corruption if process crashes.
        FINDING-009: Concurrent file writes protection.
        """
        # Save positions atomically
        positions_dict = {ticker: pos.to_dict() for ticker, pos in self.positions.items()}
        _atomic_write_json(POSITIONS_FILE, positions_dict)

        # Save daily tracker atomically
        self._save_daily_tracker()

    def _save_daily_tracker(self):
        """Save daily tracking data atomically.

        FINDING-009: Concurrent file writes protection.
        """
        daily_data = {
            'last_entry_reset': self.last_entry_reset,
            'timestamp': datetime.now().isoformat()
        }
        _atomic_write_json(DAILY_TRACKER_FILE, daily_data)

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

    def can_enter_position(self, sector: str, position_value: float,
                           risk_config=None) -> tuple:
        """Check if entry is allowed based on risk rules.

        Args:
            sector: Stock sector
            position_value: Dollar value of position
            risk_config: Optional RiskConfig object (uses defaults if None)
        """
        equity = self.get_equity()

        # Get thresholds from config or use defaults
        if risk_config:
            max_entries = risk_config.account.max_entries_per_day
            max_sector = risk_config.account.max_sector_positions
            max_position_pct = risk_config.position.max_position_pct
            daily_loss_pct = risk_config.account.daily_loss_limit_pct
        else:
            max_entries = 10
            max_sector = MAX_SECTOR_POSITIONS
            max_position_pct = 0.20
            daily_loss_pct = 0.02

        # Check daily entry limit
        if self.entries_today >= max_entries:
            return False, f"Daily entry limit reached ({max_entries})"

        # Check sector limit
        sector_counts = self.get_sector_counts()
        if sector_counts.get(sector, 0) >= max_sector:
            return False, f"Sector limit reached ({max_sector} in {sector})"

        # Check position size limit
        if position_value > equity * max_position_pct:
            return False, f"Position size {position_value:,.0f} exceeds {max_position_pct*100:.0f}% of equity"

        # Check buying power
        if position_value > self.cash:
            return False, f"Insufficient cash (${self.cash:,.2f} < ${position_value:,.2f})"

        # Check daily loss limit
        if self.day_pnl < -daily_loss_pct * self.initial_capital:
            return False, f"Daily loss limit hit (${self.day_pnl:,.2f})"

        return True, "OK"

    def enter_position(self, ticker: str, entry_price: float, shares: int,
                     stop_price: float, target_price: float, sector: str,
                     entry_min_r: Optional[float] = None) -> Position:
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
            sector=sector,
            initial_stop_price=stop_price,  # FINDING-013: Immutable initial stop
            entry_min_r=entry_min_r,
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

    def update_stop(self, ticker: str, new_stop: float, stop_type: str,
                    exit_phase: Optional[str] = None):
        """Update stop price for a position.

        Args:
            ticker:     Position symbol.
            new_stop:   New stop price.
            stop_type:  Label stored in current_stop_type (e.g. 'TRAIL_EMA20').
            exit_phase: Optional phase transition ('phase1' | 'phase2').
                        When supplied the position's exit_phase is updated so
                        _print_status can show the correct phase badge.
        """
        if ticker in self.positions:
            self.positions[ticker].stop_price = new_stop
            self.positions[ticker].current_stop_type = stop_type
            if exit_phase is not None:
                self.positions[ticker].exit_phase = exit_phase
            self.save_state()

    def _validate_trade(self, position: Position) -> tuple[bool, str]:
        """
        PHASE 3: Validate trade data to prevent obviously fake/test entries.

        Returns: (is_valid, reason)
        """
        if VALIDATION['SKIP_VALIDATION']:
            return True, ""

        # Check entry price
        if position.entry_price > VALIDATION['MAX_ENTRY_PRICE']:
            return False, f"entry_price {position.entry_price} > {VALIDATION['MAX_ENTRY_PRICE']}"

        # Check shares
        if position.shares > VALIDATION['MAX_SHARES']:
            return False, f"shares {position.shares} > {VALIDATION['MAX_SHARES']}"

        # Check position value
        position_value = position.entry_price * position.shares
        if position_value > VALIDATION['MAX_POSITION_VALUE']:
            return False, f"position_value {position_value} > {VALIDATION['MAX_POSITION_VALUE']}"

        # Check P&L on exits
        if position.realized_pnl is not None:
            if abs(position.realized_pnl) > VALIDATION['MAX_PNL_ABS']:
                return False, f"realized_pnl {position.realized_pnl} exceeds limit"

        return True, ""

    def _log_trade(self, event_type: str, position: Position):
        """Append trade to history log."""
        # PHASE 3: Validate before logging
        is_valid, reason = self._validate_trade(position)
        if not is_valid:
            # Log to stderr but don't raise (prevents breaking trading loop)
            import sys
            print(f"⚠️  WARNING: Trade validation failed - {reason}", file=sys.stderr)
            print(f"   Trade not logged: {position.ticker} @ ${position.entry_price}", file=sys.stderr)
            # Add validation failure metadata for debugging
            trade_record = {
                'event': event_type,
                'timestamp': datetime.now().isoformat(),
                'ticker': position.ticker,
                'entry_price': position.entry_price,
                'shares': position.shares,
                '_meta': {
                    'test_mode': os.environ.get('PAPER_TRADING_TEST_MODE', 'false').lower() == 'true',
                    'data_dir': str(DATA_DIR),
                    'source': 'paper_state',
                    'validation_failed': True,
                    'validation_reason': reason
                }
            }
            with open(TRADES_FILE, 'a') as f:
                f.write(json.dumps(trade_record) + '\n')
            return

        trade_record = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            'ticker': position.ticker,
            'entry_price': position.entry_price,
            'exit_price': position.exit_price,
            'shares': position.shares,
            'realized_pnl': position.realized_pnl,
            'exit_reason': position.exit_reason,
            'stop_type': position.current_stop_type,
            # PHASE 2: Test isolation metadata
            '_meta': {
                'test_mode': os.environ.get('PAPER_TRADING_TEST_MODE', 'false').lower() == 'true',
                'data_dir': str(DATA_DIR),
                'source': 'paper_state',
                'validation_passed': True
            }
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
