#!/usr/bin/env python3
"""Order lifecycle manager for Alpaca paper trading."""

import json
import os
import queue
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum


def _atomic_write_json(filepath: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename.

    Prevents data corruption if process crashes during write.
    FINDING-009: Concurrent file writes protection.
    """
    filepath = Path(filepath)
    dir_name = filepath.parent

    fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, filepath)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


class OrderStatus(Enum):
    """Order status states."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class Order:
    """Represents an order in the system."""
    id: str
    ticker: str
    side: str  # 'buy' or 'sell'
    qty: int
    status: OrderStatus
    submitted_at: str
    filled_at: Optional[str] = None
    filled_price: Optional[float] = None
    filled_qty: Optional[float] = None
    stop_price: Optional[float] = None
    reason: Optional[str] = None  # For exits
    # Entry metadata (only for buy orders, used when creating position on fill)
    target_price: Optional[float] = None
    sector: Optional[str] = None
    expected_entry_price: Optional[float] = None  # Used for position creation on fill
    # Telemetry — pivot technique and entry mode for performance evaluation (Phase 5)
    pivot_type: Optional[str] = None       # 'vcp', 'range_20d', 'pocket_pivot', 'manual'
    entry_mode: Optional[str] = None       # 'breakout' or 'immediate'
    trigger_price: Optional[float] = None  # For buy-stop: the resting trigger price

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        data['status'] = OrderStatus(data['status'])
        # Handle optional fields that may not exist in older saved orders
        for field in ['target_price', 'sector', 'expected_entry_price']:
            if field not in data:
                data[field] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class QueuedOrder:
    """Represents an order waiting in the submission queue."""
    order_type: str  # 'entry' or 'exit'
    ticker: str
    shares: int
    callback: Optional[Callable] = None  # Callback with result
    # Entry-specific fields
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    sector: Optional[str] = None
    expected_entry_price: Optional[float] = None
    # Exit-specific fields
    reason: Optional[str] = None
    # Telemetry
    pivot_type: Optional[str] = None
    entry_mode: Optional[str] = None
    trigger_price: Optional[float] = None
    # Queue metadata
    queued_at: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: int = 0  # Higher = processed first


class OrderManager:
    """Manages order lifecycle and position synchronization.

    Includes order storm protection via submission queue with TPS limiting.
    """

    def __init__(self, alpaca_client, max_tps: float = 2.0, max_queue_size: int = 50):
        """Initialize order manager.

        Args:
            alpaca_client: Instance of AlpacaClient
            max_tps: Maximum transactions per second (order submission rate)
            max_queue_size: Maximum number of orders in queue before rejection
        """
        self.alpaca = alpaca_client

        # Order tracking
        self.pending_orders: Dict[str, Order] = {}  # Orders waiting to be filled
        self.filled_orders: Dict[str, Order] = {}   # Completed orders

        # Position tracking
        self.expected_positions: Dict[str, int] = {}  # Shares we expect to have

        # Persistence - configurable via environment variable for testing
        default_data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
        self.data_dir = Path(os.environ.get('PAPER_TRADING_DATA_DIR', default_data_dir))
        self.orders_file = self.data_dir / 'alpaca_orders.json'

        # Order storm protection - TPS limiting
        self.max_tps = max_tps
        self.min_interval = 1.0 / max_tps  # Minimum seconds between orders
        self.last_submit_time = 0.0
        self.submit_lock = threading.Lock()

        # Submission queue for burst protection
        self.submission_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_queue_size)
        self.queue_stats = {
            'submitted': 0,
            'queued': 0,
            'rejected': 0,
            'errors': 0
        }

        # Start background worker thread
        self._stop_worker = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

        # Load existing orders
        self._load_orders()

    def _process_queue(self):
        """Background worker to process queued orders with TPS limiting."""
        while not self._stop_worker.is_set():
            try:
                # Get order from queue with timeout to allow checking stop event
                priority, queued_order = self.submission_queue.get(timeout=0.5)

                # Enforce TPS limiting
                with self.submit_lock:
                    elapsed = time.time() - self.last_submit_time
                    if elapsed < self.min_interval:
                        wait_time = self.min_interval - elapsed
                        time.sleep(wait_time)

                    self.last_submit_time = time.time()

                # Process the order
                self._execute_queued_order(queued_order)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ Queue processing error: {e}")
                self.queue_stats['errors'] += 1

    def _execute_queued_order(self, queued: QueuedOrder) -> Optional[Order]:
        """Execute a queued order based on type."""
        try:
            if queued.order_type == 'entry':
                result = self._submit_entry_direct(
                    ticker=queued.ticker,
                    shares=queued.shares,
                    stop_price=queued.stop_price,
                    target_price=queued.target_price,
                    sector=queued.sector,
                    expected_entry_price=queued.expected_entry_price
                )
            elif queued.order_type == 'stop_entry':
                result = self._submit_stop_entry_to_alpaca(
                    ticker=queued.ticker,
                    shares=queued.shares,
                    trigger_price=queued.trigger_price,
                    stop_price=queued.stop_price,
                    target_price=queued.target_price,
                    sector=queued.sector,
                    expected_entry_price=queued.expected_entry_price,
                    pivot_type=queued.pivot_type,
                    entry_mode=queued.entry_mode
                )
            else:  # exit
                result = self._submit_exit_direct(
                    ticker=queued.ticker,
                    shares=queued.shares,
                    reason=queued.reason
                )

            # Call callback if provided
            if queued.callback:
                try:
                    queued.callback(result)
                except Exception as e:
                    print(f"⚠️ Callback error for {queued.ticker}: {e}")

            if result:
                self.queue_stats['submitted'] += 1
            else:
                self.queue_stats['errors'] += 1

            return result

        except Exception as e:
            print(f"❌ Error executing queued order for {queued.ticker}: {e}")
            self.queue_stats['errors'] += 1
            if queued.callback:
                try:
                    queued.callback(None)
                except Exception:
                    pass
            return None

    def _can_submit_directly(self) -> bool:
        """Check if we can submit directly or need to queue."""
        with self.submit_lock:
            elapsed = time.time() - self.last_submit_time
            return elapsed >= self.min_interval and self.submission_queue.empty()

    def _submit_entry_direct(self, **kwargs) -> Optional[Order]:
        """Submit entry order directly (bypasses queue - internal use only)."""
        return self._submit_entry_to_alpaca(**kwargs)

    def _submit_exit_direct(self, **kwargs) -> Optional[Order]:
        """Submit exit order directly (bypasses queue - internal use only)."""
        return self._submit_exit_to_alpaca(**kwargs)

    def _load_orders(self):
        """Load orders from disk."""
        if self.orders_file.exists():
            try:
                with open(self.orders_file, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        return  # Empty file, nothing to load
                    data = json.loads(content)
                    for order_id, order_data in data.get('pending', {}).items():
                        self.pending_orders[order_id] = Order.from_dict(order_data)
                    for order_id, order_data in data.get('filled', {}).items():
                        self.filled_orders[order_id] = Order.from_dict(order_data)
            except Exception as e:
                print(f"⚠️ Error loading orders: {e}")

    def _save_orders(self):
        """Save orders to disk atomically.

        FINDING-009: Concurrent file writes protection.
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {
                'pending': {k: v.to_dict() for k, v in self.pending_orders.items()},
                'filled': {k: v.to_dict() for k, v in self.filled_orders.items()},
                'timestamp': datetime.now().isoformat()
            }
            _atomic_write_json(self.orders_file, data)
        except Exception as e:
            print(f"⚠️ Error saving orders: {e}")

    def submit_entry(self, ticker: str, shares: int, stop_price: float,
                    target_price: Optional[float] = None,
                    sector: Optional[str] = None,
                    expected_entry_price: Optional[float] = None,
                    priority: int = 0,
                    callback: Optional[Callable] = None) -> Optional[Order]:
        """Submit a buy order (with storm protection queue).

        Args:
            ticker: Stock symbol
            shares: Number of shares to buy
            stop_price: Stop loss price
            target_price: Target price for position
            sector: Stock sector
            expected_entry_price: Expected fill price
            priority: Higher priority orders processed first (default 0)
            callback: Optional callback function(order_result) called when processed

        Returns:
            Order object if submitted directly, None if queued or failed
        """
        # Check if we can submit directly (no recent orders and queue empty)
        if self._can_submit_directly():
            result = self._submit_entry_to_alpaca(
                ticker, shares, stop_price, target_price, sector, expected_entry_price
            )
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    print(f"⚠️ Callback error for {ticker}: {e}")
            return result

        # Queue the order for later submission
        try:
            queued = QueuedOrder(
                order_type='entry',
                ticker=ticker,
                shares=shares,
                stop_price=stop_price,
                target_price=target_price,
                sector=sector,
                expected_entry_price=expected_entry_price,
                priority=priority,
                callback=callback
            )
            self.submission_queue.put((-priority, queued), block=False)  # Negative for highest first
            self.queue_stats['queued'] += 1
            print(f"⏳ Order queued: {ticker} {shares} shares (position {self.submission_queue.qsize()} in queue)")
            return None  # Will be processed asynchronously

        except queue.Full:
            self.queue_stats['rejected'] += 1
            print(f"❌ Order rejected: {ticker} - submission queue full (max {self.submission_queue.maxsize})")
            return None

    def _submit_entry_to_alpaca(self, ticker: str, shares: int, stop_price: float,
                                target_price: Optional[float] = None,
                                sector: Optional[str] = None,
                                expected_entry_price: Optional[float] = None) -> Optional[Order]:
        """Internal: Submit entry directly to Alpaca."""
        result = self.alpaca.submit_market_order(ticker, shares, 'buy', stop_price)

        if not result:
            print(f"❌ Failed to submit entry order for {ticker}")
            return None

        order = Order(
            id=result['id'],
            ticker=ticker,
            side='buy',
            qty=shares,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=stop_price,
            target_price=target_price,
            sector=sector,
            expected_entry_price=expected_entry_price
        )

        self.pending_orders[order.id] = order
        self._save_orders()

        print(f"📤 Order submitted: {ticker} {shares} shares @ market")
        return order

    def submit_stop_entry(self, ticker: str, shares: int, trigger_price: float,
                          stop_price: float,
                          target_price: Optional[float] = None,
                          sector: Optional[str] = None,
                          expected_entry_price: Optional[float] = None,
                          pivot_type: Optional[str] = None,
                          entry_mode: Optional[str] = None,
                          priority: int = 0,
                          callback: Optional[Callable] = None) -> Optional[Order]:
        """Submit a buy-stop order (resting order above pivot).

        Args:
            ticker: Stock symbol
            shares: Number of shares to buy
            trigger_price: Stop price (triggers market order when reached)
            stop_price: Stop-loss price for the position
            target_price: Target price for the position
            sector: Stock sector
            expected_entry_price: Expected fill price
            pivot_type: Technique that produced the pivot (for telemetry)
            entry_mode: 'breakout' or 'immediate' (for telemetry)
            priority: Higher priority orders processed first (default 0)
            callback: Optional callback function(order_result) called when processed

        Returns:
            Order object if submitted directly, None if queued or failed
        """
        if self._can_submit_directly():
            result = self._submit_stop_entry_to_alpaca(
                ticker, shares, trigger_price, stop_price, target_price,
                sector, expected_entry_price, pivot_type, entry_mode
            )
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    print(f"⚠️ Callback error for {ticker}: {e}")
            return result

        try:
            queued = QueuedOrder(
                order_type='stop_entry',
                ticker=ticker,
                shares=shares,
                stop_price=stop_price,
                target_price=target_price,
                sector=sector,
                expected_entry_price=expected_entry_price,
                pivot_type=pivot_type,
                entry_mode=entry_mode,
                trigger_price=trigger_price,
                priority=priority,
                callback=callback
            )
            self.submission_queue.put((-priority, queued), block=False)
            self.queue_stats['queued'] += 1
            print(f"⏳ Stop-entry queued: {ticker} {shares} shares @ ${trigger_price:.2f} (position {self.submission_queue.qsize()} in queue)")
            return None

        except queue.Full:
            self.queue_stats['rejected'] += 1
            print(f"❌ Stop-entry rejected: {ticker} - submission queue full (max {self.submission_queue.maxsize})")
            return None

    def _submit_stop_entry_to_alpaca(self, ticker: str, shares: int, trigger_price: float,
                                     stop_price: float,
                                     target_price: Optional[float] = None,
                                     sector: Optional[str] = None,
                                     expected_entry_price: Optional[float] = None,
                                     pivot_type: Optional[str] = None,
                                     entry_mode: Optional[str] = None) -> Optional[Order]:
        """Internal: Submit stop-entry directly to Alpaca."""
        result = self.alpaca.submit_stop_order(ticker, shares, trigger_price, 'buy')

        if not result:
            print(f"❌ Failed to submit stop-entry order for {ticker}")
            return None

        order = Order(
            id=result['id'],
            ticker=ticker,
            side='buy',
            qty=shares,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=stop_price,
            target_price=target_price,
            sector=sector,
            expected_entry_price=expected_entry_price,
            pivot_type=pivot_type,
            entry_mode=entry_mode,
            trigger_price=trigger_price
        )

        self.pending_orders[order.id] = order
        self._save_orders()

        print(f"📤 Stop-entry submitted: {ticker} {shares} shares @ ${trigger_price:.2f} (triggers market order)")
        return order

    def cancel_stop_entry(self, ticker: str) -> bool:
        """Cancel pending stop-entry orders for a ticker.

        Called when setup degrades (score drops, VCP invalidates, etc.).

        Returns:
            True if any orders were cancelled, False otherwise
        """
        cancelled = False
        orders_to_cancel = [
            (oid, o) for oid, o in self.pending_orders.items()
            if o.ticker == ticker and o.entry_mode == 'breakout' and o.trigger_price is not None
        ]

        for oid, order in orders_to_cancel:
            try:
                self.alpaca.cancel_order(oid)
                order.status = OrderStatus.CANCELED
                self.filled_orders[oid] = order
                del self.pending_orders[oid]
                cancelled = True
                print(f"🚫 Stop-entry cancelled: {ticker} @ ${order.trigger_price:.2f}")
            except Exception as e:
                print(f"⚠️ Failed to cancel stop-entry for {ticker}: {e}")

        if cancelled:
            self._save_orders()

        return cancelled

    def submit_exit(self, ticker: str, shares: int, reason: str,
                   priority: int = 0,
                   callback: Optional[Callable] = None) -> Optional[Order]:
        """Submit a sell order (with storm protection queue).

        Args:
            ticker: Stock symbol
            shares: Number of shares to sell
            reason: Exit reason (e.g., 'STOP_HIT', 'TARGET_HIT')
            priority: Higher priority orders processed first (default 0)
            callback: Optional callback function(order_result) called when processed

        Returns:
            Order object if submitted directly, None if queued or failed
        """
        # Check if we can submit directly
        if self._can_submit_directly():
            result = self._submit_exit_to_alpaca(ticker, shares, reason)
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    print(f"⚠️ Callback error for {ticker}: {e}")
            return result

        # Queue the exit order
        try:
            queued = QueuedOrder(
                order_type='exit',
                ticker=ticker,
                shares=shares,
                reason=reason,
                priority=priority,
                callback=callback
            )
            self.submission_queue.put((-priority, queued), block=False)
            self.queue_stats['queued'] += 1
            print(f"⏳ Exit queued: {ticker} ({reason}) - position {self.submission_queue.qsize()} in queue")
            return None

        except queue.Full:
            self.queue_stats['rejected'] += 1
            print(f"❌ Exit rejected: {ticker} - submission queue full")
            return None

    def _submit_exit_to_alpaca(self, ticker: str, shares: int, reason: str) -> Optional[Order]:
        """Internal: Submit exit directly to Alpaca."""
        result = self.alpaca.close_position(ticker)

        if not result:
            print(f"❌ Failed to submit exit order for {ticker}")
            return None

        order = Order(
            id=result['id'],
            ticker=ticker,
            side='sell',
            qty=shares,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            reason=reason
        )

        self.pending_orders[order.id] = order
        self._save_orders()

        print(f"📤 Exit submitted: {ticker} ({reason})")
        return order

    def check_order_status(self, order_id: str) -> Optional[Order]:
        """Check and update order status from Alpaca.

        Args:
            order_id: Alpaca order ID

        Returns:
            Updated Order or None
        """
        if order_id not in self.pending_orders:
            return self.filled_orders.get(order_id)

        order = self.pending_orders[order_id]

        # Get latest status from Alpaca
        alpaca_order = self.alpaca.get_order(order_id)

        # Auto-detect and purge stale test/mock orders that don't exist in Alpaca
        # Catch 'test-order', 'test-order-*', 'mock-*' patterns
        is_test_order = order_id == 'test-order' or order_id.startswith('test-order-') or order_id.startswith('mock-')
        if not alpaca_order and is_test_order:
            print(f"🧹 Cleaning up stale test order: {order_id}")
            del self.pending_orders[order_id]
            self._save_orders()
            return None

        if not alpaca_order:
            print(f"⚠️ Could not fetch order status for {order_id}")
            return order

        # Update local order
        old_status = order.status
        new_status = self._map_alpaca_status(alpaca_order['status'])

        # PARTIAL FILL FIX: Always update filled_qty from Alpaca (accumulates across checks)
        alpaca_filled_qty = alpaca_order.get('filled_qty')
        if alpaca_filled_qty is not None:
            order.filled_qty = float(alpaca_filled_qty)
        alpaca_filled_price = alpaca_order.get('filled_avg_price') or alpaca_order.get('filled_price')
        if alpaca_filled_price is not None:
            order.filled_price = float(alpaca_filled_price)

        if new_status != old_status:
            order.status = new_status

            if new_status == OrderStatus.FILLED:
                order.filled_at = datetime.now().isoformat()
                # filled_qty and filled_price already captured above

                # Move to filled orders
                self.filled_orders[order.id] = order
                del self.pending_orders[order.id]

                print(f"✅ Order filled: {order.ticker} "
                      f"@${order.filled_price:.2f} x {order.filled_qty}")

            elif new_status == OrderStatus.PARTIAL_FILL:
                # PARTIAL FILL FIX: Update fill info but keep order pending
                # Position creation only happens when fully filled
                print(f"⏳ Order partially filled: {order.ticker} "
                      f"{order.filled_qty}/{order.qty} shares @ ${order.filled_price or 0:.2f}")

            elif new_status in [OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED]:
                # Move to filled with error status
                self.filled_orders[order.id] = order
                del self.pending_orders[order.id]

                print(f"⚠️ Order {new_status.value}: {order.ticker} {order.id}")

        self._save_orders()
        return order

    def _map_alpaca_status(self, alpaca_status: str) -> OrderStatus:
        """Map Alpaca status to our status enum."""
        status_map = {
            'new': OrderStatus.SUBMITTED,
            'accepted': OrderStatus.ACCEPTED,
            'partially_filled': OrderStatus.PARTIAL_FILL,
            'filled': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELED,
            'expired': OrderStatus.EXPIRED,
            'rejected': OrderStatus.REJECTED
        }
        return status_map.get(alpaca_status.lower(), OrderStatus.PENDING)

    def sync_positions(self, local_positions: Dict) -> Dict:
        """Sync local positions with Alpaca.

        Args:
            local_positions: Current local position dict

        Returns:
            Dict with 'synced', 'added', 'removed', 'discrepancies'
        """
        result = {
            'synced': [],
            'added': [],
            'removed': [],
            'discrepancies': []
        }

        try:
            alpaca_positions = self.alpaca.list_positions()
            alpaca_tickers = {p['symbol'] for p in alpaca_positions}

            # Check for positions in Alpaca but not locally
            for alpaca_pos in alpaca_positions:
                ticker = alpaca_pos['symbol']
                alpaca_qty = int(alpaca_pos['qty'])

                if ticker not in local_positions:
                    # Position exists in Alpaca but not locally
                    result['added'].append({
                        'ticker': ticker,
                        'qty': alpaca_qty,
                        'avg_price': alpaca_pos['avg_entry_price']
                    })
                else:
                    # Position exists both places - check quantity and track avg price
                    local_qty = local_positions[ticker].shares
                    if alpaca_qty != local_qty:
                        result['discrepancies'].append({
                            'ticker': ticker,
                            'alpaca_qty': alpaca_qty,
                            'local_qty': local_qty
                        })
                    else:
                        result['synced'].append({
                            'ticker': ticker,
                            'avg_price': alpaca_pos['avg_entry_price']
                        })

            # Check for positions locally but not in Alpaca
            for ticker in list(local_positions.keys()):
                if ticker not in alpaca_tickers:
                    result['removed'].append(ticker)

            return result

        except Exception as e:
            print(f"⚠️ Error syncing positions: {e}")
            return result

    def get_pending_count(self) -> int:
        """Get number of pending orders."""
        return len(self.pending_orders)

    def get_pending_for_ticker(self, ticker: str) -> List[Order]:
        """Get pending orders for a specific ticker."""
        return [o for o in self.pending_orders.values() if o.ticker == ticker]

    def has_pending_order(self, ticker: str) -> bool:
        """Check if there are pending orders for ticker."""
        return any(o.ticker == ticker for o in self.pending_orders.values())

    def process_all_pending(self) -> List[Order]:
        """Check status of all pending orders.

        Returns:
            List of orders that changed status
        """
        updated = []
        for order_id in list(self.pending_orders.keys()):
            order = self.check_order_status(order_id)
            if order and order.status == OrderStatus.FILLED:
                updated.append(order)
        return updated

    def get_orders_summary(self) -> Dict:
        """Get summary of all orders."""
        return {
            'pending': len(self.pending_orders),
            'filled': len(self.filled_orders),
            'pending_tickers': [o.ticker for o in self.pending_orders.values()],
            'queue_size': self.submission_queue.qsize(),
            'queue_stats': self.queue_stats.copy()
        }

    def get_queue_status(self) -> Dict:
        """Get order storm protection queue status."""
        return {
            'queue_size': self.submission_queue.qsize(),
            'max_size': self.submission_queue.maxsize,
            'tps_limit': self.max_tps,
            'min_interval': self.min_interval,
            'stats': self.queue_stats.copy(),
            'worker_alive': self._worker_thread.is_alive()
        }

    def wait_for_queue_empty(self, timeout: Optional[float] = None) -> bool:
        """Wait for submission queue to empty.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            True if queue empty, False if timeout reached
        """
        start = time.time()
        while not self.submission_queue.empty():
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)
        return True

    def shutdown(self, wait_for_queue: bool = True, timeout: float = 30.0):
        """Shutdown the order manager and stop queue worker.

        Args:
            wait_for_queue: Whether to wait for pending queue items
            timeout: Max seconds to wait for queue to empty
        """
        if wait_for_queue and not self.submission_queue.empty():
            print(f"⏳ Waiting for {self.submission_queue.qsize()} queued orders...")
            if not self.wait_for_queue_empty(timeout=timeout):
                print(f"⚠️ Timeout waiting for queue ({timeout}s)")

        self._stop_worker.set()
        self._worker_thread.join(timeout=5.0)
        if self._worker_thread.is_alive():
            print("⚠️ Queue worker thread did not terminate gracefully")

        # Final save
        self._save_orders()


if __name__ == "__main__":
    # Test order manager
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    from alpaca_client import AlpacaClient

    print("Testing Order Manager...")

    try:
        alpaca = AlpacaClient(mode='paper')
        manager = OrderManager(alpaca, max_tps=2.0)

        print(f"\n📋 Current Orders:")
        summary = manager.get_orders_summary()
        print(f"   Pending: {summary['pending']}")
        print(f"   Filled: {summary['filled']}")

        # Show storm protection status
        queue_status = manager.get_queue_status()
        print(f"\n🛡️ Order Storm Protection:")
        print(f"   TPS Limit: {queue_status['tps_limit']:.1f} orders/sec")
        print(f"   Queue: {queue_status['queue_size']}/{queue_status['max_size']}")
        print(f"   Worker: {'✅ Running' if queue_status['worker_alive'] else '❌ Dead'}")

        if summary['pending'] > 0:
            print(f"\n   Processing pending orders...")
            filled = manager.process_all_pending()
            print(f"   Newly filled: {len(filled)}")

        print("\n✅ Order manager initialized successfully")

        # Test queue functionality
        print("\n🧪 Testing order storm protection...")

        # Simulate multiple simultaneous orders
        def test_callback(result):
            if result:
                print(f"   ✅ Callback: Order {result.ticker} processed")

        # Queue some test orders (won't actually submit)
        for i in range(3):
            manager.submit_entry(
                ticker=f"TEST{i}",
                shares=10,
                stop_price=90.0,
                priority=3-i,  # Higher priority first
                callback=test_callback
            )

        # Show queue status
        time.sleep(0.5)
        status = manager.get_queue_status()
        print(f"\n   Queue stats: {status['stats']}")

        # Shutdown gracefully
        manager.shutdown(wait_for_queue=True, timeout=5.0)
        print("\n✅ Shutdown complete")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
