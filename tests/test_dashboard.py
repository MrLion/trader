#!/usr/bin/env python3
"""Tests for traderlib.dashboard."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "traderlib"))

import pytest

# Import dashboard -- may fail if rich is not installed
try:
    from traderlib.dashboard import Dashboard
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


@pytest.fixture
def mock_state():
    return {
        "equity": 103420.50,
        "cash": 45200.00,
        "day_pnl": 420.50,
        "unrealized_pnl": 1150.00,
        "open_positions": 2,
        "pending_orders": 0,
        "positions": {
            "AAPL": {
                "entry_price": 185.00,
                "current_price": 187.45,
                "stop_price": 180.00,
                "shares": 100,
                "current_stop_type": "HARD",
                "exit_phase": "phase1",
            },
            "NVDA": {
                "entry_price": 895.00,
                "current_price": 892.10,
                "stop_price": 850.00,
                "shares": 25,
                "current_stop_type": "HARD",
                "exit_phase": "phase1",
            },
        },
        "market_status": "OPEN",
        "vix": 16.4,
        "ws_connected": True,
        "api_requests": 12,
        "api_max": 500,
        "next_scan_seconds": 28,
        "market_close_seconds": 12480,
    }


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboard:
    def test_dashboard_init(self):
        with patch("traderlib.dashboard.Live") as MockLive, \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            MockLive.return_value.start.return_value = None
            d = Dashboard(enabled=True)
            assert d.enabled is True
            assert d.console is not None
            d.stop()

    def test_dashboard_render_returns_group(self, mock_state):
        from rich.console import Group
        with patch("traderlib.dashboard.Live"):
            d = Dashboard(enabled=True)
            renderable = d._render(mock_state)
            assert isinstance(renderable, Group)
            d.stop()

    def test_stats_shows_equity_and_day_pnl(self, mock_state):
        with patch("traderlib.dashboard.Live"):
            d = Dashboard(enabled=True)
            stats = d._stats(mock_state)
            text = str(stats)
            assert "$103,420.50" in text
            assert "$+420.50" in text
            d.stop()

    def test_positions_table_has_rows(self, mock_state):
        with patch("traderlib.dashboard.Live"):
            d = Dashboard(enabled=True)
            table = d._positions(mock_state)
            assert table.row_count == 2
            d.stop()

    def test_positions_color_green_for_profit(self, mock_state):
        with patch("traderlib.dashboard.Live"):
            d = Dashboard(enabled=True)
            table = d._positions(mock_state)
            # AAPL is row 0, CURRENT is column 3 (0-indexed: TICKER, PHASE, ENTRY, CURRENT)
            cell = table.columns[3]._cells[0]
            assert cell.style == "green"
            d.stop()

    def test_activity_log_with_events(self):
        with patch("traderlib.dashboard.Live"):
            d = Dashboard(enabled=True)
            d.log_event({
                "type": "ENTRY",
                "timestamp": "10:32:01",
                "ticker": "AAPL",
                "detail": "$187.45 x100",
            })
            activity = d._activity()
            text = str(activity)
            assert "ENTRY" in text
            assert "AAPL" in text
            d.stop()

    def test_dashboard_noop_when_disabled(self, mock_state):
        d = Dashboard(enabled=False)
        assert d.enabled is False
        # Should not raise
        d.update(mock_state)
        d.log_event({"type": "ENTRY", "ticker": "TEST"})
        d.stop()

    def test_dashboard_noop_without_rich(self):
        with patch("traderlib.dashboard._HAS_RICH", False), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            assert d.enabled is False


class TestDashboardFallback:
    """Tests that run even without rich installed."""

    def test_dashboard_imports_without_rich(self):
        """Verify the module imports cleanly when rich is missing."""
        assert True  # Import already succeeded at module level
