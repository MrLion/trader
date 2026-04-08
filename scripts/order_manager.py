#!/usr/bin/env python3
"""Order lifecycle manager for Alpaca paper trading."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


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

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        data['status'] = OrderStatus(data['status'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class OrderManager:
    """Manages order lifecycle and position synchronization."""

    def __init__(self, alpaca_client):
        """Initialize order manager.

        Args:
            alpaca_client: Instance of AlpacaClient
        """
        self.alpaca = alpaca_client

        # Order tracking
        self.pending_orders: Dict[str, Order] = {}  # Orders waiting to be filled
        self.filled_orders: Dict[str, Order] = {}   # Completed orders

        # Position tracking
        self.expected_positions: Dict[str, int] = {}  # Shares we expect to have

        # Persistence
        self.data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
        self.orders_file = self.data_dir / 'alpaca_orders.json'

        # Load existing orders
        self._load_orders()

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
        """Save orders to disk."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {
                'pending': {k: v.to_dict() for k, v in self.pending_orders.items()},
                'filled': {k: v.to_dict() for k, v in self.filled_orders.items()},
                'timestamp': datetime.now().isoformat()
            }
            with open(self.orders_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving orders: {e}")

    def submit_entry(self, ticker: str, shares: int, stop_price: float) -> Optional[Order]:
        """Submit a buy order.

        Args:
            ticker: Stock symbol
            shares: Number of shares to buy
            stop_price: Stop loss price

        Returns:
            Order object or None if submission failed
        """
        # Submit to Alpaca
        result = self.alpaca.submit_market_order(ticker, shares, 'buy', stop_price)

        if not result:
            print(f"❌ Failed to submit entry order for {ticker}")
            return None

        # Create local order record
        order = Order(
            id=result['id'],
            ticker=ticker,
            side='buy',
            qty=shares,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=stop_price
        )

        self.pending_orders[order.id] = order
        self.expected_positions[ticker] = shares
        self._save_orders()

        print(f"📤 Order submitted: {ticker} {shares} shares @ market")
        return order

    def submit_exit(self, ticker: str, shares: int, reason: str) -> Optional[Order]:
        """Submit a sell order.

        Args:
            ticker: Stock symbol
            shares: Number of shares to sell
            reason: Exit reason (e.g., 'STOP_HIT', 'TARGET_HIT')

        Returns:
            Order object or None if submission failed
        """
        # Submit to Alpaca
        result = self.alpaca.close_position(ticker)

        if not result:
            print(f"❌ Failed to submit exit order for {ticker}")
            return None

        # Create local order record
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
        if not alpaca_order and (order_id.startswith('test-order-') or order_id.startswith('mock-')):
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

        if new_status != old_status:
            order.status = new_status

            if new_status == OrderStatus.FILLED:
                order.filled_at = datetime.now().isoformat()
                order.filled_price = alpaca_order.get('filled_price')
                order.filled_qty = alpaca_order.get('filled_qty')

                # Move to filled orders
                self.filled_orders[order.id] = order
                del self.pending_orders[order.id]

                print(f"✅ Order filled: {order.ticker} "
                      f"@${order.filled_price:.2f} x {order.filled_qty}")

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
                    # Position exists both places - check quantity
                    local_qty = local_positions[ticker].shares
                    if alpaca_qty != local_qty:
                        result['discrepancies'].append({
                            'ticker': ticker,
                            'alpaca_qty': alpaca_qty,
                            'local_qty': local_qty
                        })
                    else:
                        result['synced'].append(ticker)

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
            'pending_tickers': [o.ticker for o in self.pending_orders.values()]
        }


if __name__ == "__main__":
    # Test order manager
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    from alpaca_client import AlpacaClient

    print("Testing Order Manager...")

    try:
        alpaca = AlpacaClient(mode='paper')
        manager = OrderManager(alpaca)

        print(f"\n📋 Current Orders:")
        summary = manager.get_orders_summary()
        print(f"   Pending: {summary['pending']}")
        print(f"   Filled: {summary['filled']}")

        if summary['pending'] > 0:
            print(f"\n   Processing pending orders...")
            filled = manager.process_all_pending()
            print(f"   Newly filled: {len(filled)}")

        print("\n✅ Order manager initialized successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
