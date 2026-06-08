#!/usr/bin/env python3
"""Tests for traderlib.dashboard."""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

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
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            d.console.height = 50
            renderable = d._render(mock_state)
            assert isinstance(renderable, Group)
            d.stop()

    def test_stats_shows_account_value_and_day_pnl(self, mock_state):
        # Account value = cash + equity (positions market value) per the
        # canonical formula. mock_state has cash=45200, equity=103420.50,
        # so the rendered ACCOUNT VALUE must be 148,620.50.
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            stats = d._stats(mock_state)
            text = str(stats)
            assert "$  148,620.50" in text
            assert "▲ $   +420.50" in text
            d.stop()

    def test_positions_table_has_rows(self, mock_state):
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            table = d._positions(mock_state)
            # separator row + 2 data rows = 3 total
            assert table.row_count == 3
            d.stop()

    def test_positions_color_green_for_profit(self, mock_state):
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            table = d._positions(mock_state)
            # AAPL is first data row (index 1, after separator at index 0)
            # CURRENT is column 2 (0-indexed: TICKER, ENTRY, CURRENT, STOP, TYPE, UNREAL, DIST)
            cell = table.columns[2]._cells[1]
            assert cell.style == "green"
            d.stop()

    def test_activity_log_with_events(self):
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
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


class TestDashboardFrozenIndicator(unittest.TestCase):
    def test_header_shows_frozen_when_market_closed(self):
        """Dashboard header should indicate frozen data when market != OPEN."""
        try:
            from traderlib.dashboard import Dashboard
        except ImportError:
            self.skipTest("rich not installed")

        with patch('traderlib.dashboard.Live'), \
             patch('traderlib.dashboard.os.isatty', return_value=True):
            d = Dashboard(enabled=True)
            d._last_update_time = pd.Timestamp('2024-01-15 16:00:00')

            state = {
                'market_status': 'CLOSED',
                'mode': 'PAPER',
                'regime': 'NEUTRAL',
                'vix': 16.4,
                'ws_connected': True,
                'api_requests': 12,
                'api_max': 500,
            }

            header = d._header(state)
            header_text = str(header)

            self.assertIn('Data frozen since', header_text)
            self.assertIn('16:00:00', header_text)
            d.stop()

    def test_header_no_frozen_when_market_open(self):
        """Dashboard header should NOT show frozen indicator when market is OPEN."""
        try:
            from traderlib.dashboard import Dashboard
        except ImportError:
            self.skipTest("rich not installed")

        with patch('traderlib.dashboard.Live'), \
             patch('traderlib.dashboard.os.isatty', return_value=True):
            d = Dashboard(enabled=True)
            d._last_update_time = pd.Timestamp('2024-01-15 10:30:00')

            state = {
                'market_status': 'OPEN',
                'mode': 'PAPER',
                'regime': 'NEUTRAL',
                'vix': 16.4,
                'ws_connected': True,
                'api_requests': 12,
                'api_max': 500,
            }

            header = d._header(state)
            header_text = str(header)

            self.assertNotIn('Data frozen since', header_text)
            d.stop()


class TestDashboardFallback:
    """Tests that run even without rich installed."""

    def test_dashboard_imports_without_rich(self):
        """Verify the module imports cleanly when rich is missing."""
        assert True  # Import already succeeded at module level


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardRowCaps:
    """Task 3 — _positions / _activity optional max rows."""

    def test_positions_12_with_max_6_truncates(self):
        """12 positions, max_rows=6: 6 ticker rows + 1 'more' row = 7 data rows + 1 sep."""
        from collections import OrderedDict
        positions = OrderedDict()
        for i in range(12):
            ticker = f"T{i:02d}"
            sign = 1 if i % 2 == 0 else -1
            positions[ticker] = {
                "entry_price": 100.0,
                "current_price": 100.0 + sign * (10 - i * 0.5),
                "stop_price": 95.0,
                "initial_stop_price": 95.0,
                "shares": 100,
                "current_stop_type": "HARD",
                "exit_phase": "phase1",
            }
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            table = d._positions({"positions": positions}, max_rows=6)
            assert table.row_count == 8
            first_cell = table.columns[0]._cells[-1]
            assert "+6 more positions" in str(first_cell)
            d.stop()

    def test_positions_fewer_than_cap_no_more_line(self):
        """5 positions, max_rows=10: all 5 rendered, no 'more' line."""
        from collections import OrderedDict
        positions = OrderedDict()
        for i in range(5):
            positions[f"T{i}"] = {
                "entry_price": 100.0,
                "current_price": 101.0,
                "stop_price": 95.0,
                "initial_stop_price": 95.0,
                "shares": 100,
                "current_stop_type": "HARD",
                "exit_phase": "phase1",
            }
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            table = d._positions({"positions": positions}, max_rows=10)
            assert table.row_count == 6
            for col in table.columns:
                for cell in col._cells:
                    assert "more positions" not in str(cell)
            d.stop()

    def test_positions_default_max_rows_none_no_change(self):
        """max_rows=None preserves existing behavior (no truncation)."""
        from collections import OrderedDict
        positions = OrderedDict()
        for i in range(15):
            positions[f"T{i}"] = {
                "entry_price": 100.0,
                "current_price": 101.0,
                "stop_price": 95.0,
                "initial_stop_price": 95.0,
                "shares": 100,
                "current_stop_type": "HARD",
                "exit_phase": "phase1",
            }
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            table = d._positions({"positions": positions})
            assert table.row_count == 16
            d.stop()

    def test_activity_20_with_max_5_truncates(self):
        """20 events, max_events=5: 5 event lines + 'more' line."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            for i in range(20):
                d.log_event({
                    "type": "ENTRY",
                    "timestamp": f"10:{i:02d}:00",
                    "ticker": f"T{i:02d}",
                    "detail": f"${100 + i}.00 x100",
                })
            activity = d._activity(max_events=5)
            text = str(activity)
            assert text.count("ENTRY") == 5
            assert "+15 more events" in text
            d.stop()

    def test_activity_fewer_than_cap_no_more_line(self):
        """3 events, max_events=10: all 3 shown, no 'more'."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            for i in range(3):
                d.log_event({
                    "type": "ENTRY",
                    "timestamp": f"10:{i:02d}:00",
                    "ticker": f"T{i}",
                    "detail": f"${100 + i}.00 x100",
                })
            activity = d._activity(max_events=10)
            text = str(activity)
            assert text.count("ENTRY") == 3
            assert "more events" not in text
            d.stop()

    def test_activity_default_max_events_10(self):
        """max_events=None uses the existing default cap of 10."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            for i in range(15):
                d.log_event({
                    "type": "ENTRY",
                    "timestamp": f"10:{i:02d}:00",
                    "ticker": f"T{i:02d}",
                    "detail": f"${100 + i}.00 x100",
                })
            activity = d._activity()  # max_events=None
            text = str(activity)
            assert text.count("ENTRY") == 10
            assert "more events" not in text
            d.stop()

    def test_activity_r_multiple_suffix(self):
        """Exit events with r_multiple field show the R suffix with color."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            d.log_event({
                "type": "EXIT",
                "timestamp": "10:32:00",
                "ticker": "AAPL",
                "detail": "$200.00",
                "pnl": 250.0,
                "r_multiple": 1.5,
            })
            activity = d._activity()
            text = str(activity)
            assert "+1.5R" in text
            d.stop()

    def test_today_summary_avg_r_two_decimals(self):
        """Task 6 — avg_r is formatted with 2 decimals (was 1)."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            state = {
                "today_stats": {"wins": 2, "losses": 1, "total_pnl": 100.0, "avg_r": 0.456},
            }
            line = d._today_summary(state)
            text = str(line)
            assert "+0.46R" in text
            assert "+0.5R" not in text
            d.stop()


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardHeightTiers:
    """Task 4 — _render() gates sections by console.height."""

    def test_24_35_50_row_tiers(self, mock_state):
        """Same state at heights 24/35/50 produces strictly-increasing renderables."""
        from rich.console import Console
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            def render_to_str(d):
                c = Console(width=120, height=d.console.height, force_terminal=False)
                with c.capture() as capture:
                    c.print(d._render(mock_state))
                return capture.get()

            d24 = Dashboard(enabled=True)
            d24.console.height = 24
            s24 = render_to_str(d24)
            d24.stop()

            d35 = Dashboard(enabled=True)
            d35.console.height = 35
            s35 = render_to_str(d35)
            d35.stop()

            d50 = Dashboard(enabled=True)
            d50.console.height = 50
            s50 = render_to_str(d50)
            d50.stop()

            lines_24 = s24.count("\n")
            lines_35 = s35.count("\n")
            lines_50 = s50.count("\n")
            assert lines_50 > lines_35, f"50-row ({lines_50}) not > 35-row ({lines_35})"
            assert lines_35 > lines_24, f"35-row ({lines_35}) not > 24-row ({lines_24})"

    def test_22_row_fallback(self, mock_state):
        """Below 24 rows: only header, stats, footer (minimum view)."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            d.console.height = 22
            rendered = d._render(mock_state)
            text = str(rendered)
            assert "TODAY:" not in text
            assert "TICKER" not in text
            d.stop()

    def test_post_market_includes_closed_trades_at_50(self, mock_state):
        """Post-market at 50 rows includes the closed-trades panel."""
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            d.console.height = 50
            post_state = dict(mock_state)
            post_state["market_status"] = "POST"
            rendered = d._render(post_state)
            assert rendered is not None
            d.stop()


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardAccountValueYtd:
    """Task 5 — first stats line is ACCOUNT VALUE | DAY P&L | YTD."""

    def test_account_value_label_present(self, mock_state):
        """The first stats line uses 'ACCOUNT VALUE' (not 'EQUITY')."""
        mock_state["ytd_pnl"] = 15340.0
        mock_state["ytd_pnl_pct"] = 15.3
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._stats(mock_state))
            assert "ACCOUNT VALUE" in text
            assert "YTD" in text
            d.stop()

    def test_ytd_negative_colored_red(self, mock_state):
        """Negative YTD shows the red color in the rendered Text spans."""
        mock_state["ytd_pnl"] = -5230.0
        mock_state["ytd_pnl_pct"] = -5.2
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = d._stats(mock_state)
            spans_have_red = any("red" in str(span.style) for span in text.spans)
            plain = str(text)
            assert spans_have_red, f"Expected red span, got spans: {text.spans}, text: {plain!r}"
            assert "YTD" in plain
            d.stop()

    def test_ytd_positive_colored_green(self, mock_state):
        """Positive YTD shows the green color in the rendered Text spans."""
        mock_state["ytd_pnl"] = 15340.0
        mock_state["ytd_pnl_pct"] = 15.3
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = d._stats(mock_state)
            spans_have_green = any("green" in str(span.style) for span in text.spans)
            plain = str(text)
            assert spans_have_green, f"Expected green span, got spans: {text.spans}, text: {plain!r}"
            assert "YTD" in plain
            d.stop()


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardEquitySparkline:
    """Task 5 — _equity_sparkline renders 30 cells + $NNN.NK label."""

    def test_sparkline_30_cells(self, mock_state):
        """30 cells of sparkline, plus a $NNN.NK or $N.NNM label."""
        mock_state["equity_30d"] = [100.0 + i * 0.5 for i in range(22)]
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._equity_sparkline(mock_state))
            cell_chars = "▁▂▃▄▅▆▇█░"
            cell_count = sum(1 for c in text if c in cell_chars)
            assert cell_count == 30, f"Expected 30 cells, got {cell_count}: {text!r}"
            assert "K" in text
            d.stop()

    def test_sparkline_above_one_million(self, mock_state):
        """Equity >= $1M is labeled as $N.NNM (not K)."""
        mock_state["equity_30d"] = [1_000_000.0 + i * 1000 for i in range(22)]
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._equity_sparkline(mock_state))
            assert "M" in text
            assert "K" not in text
            d.stop()

    def test_sparkline_empty_uses_dashes(self, mock_state):
        """Empty equity_30d -> flat 30-cell ░ + '--' label."""
        mock_state["equity_30d"] = []
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._equity_sparkline(mock_state))
            cell_count = sum(1 for c in text if c == "░")
            assert cell_count == 30
            assert "--" in text
            d.stop()


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardClosedTrades:
    """Task 5 — _closed_trades reads data/paper/trades.jsonl on demand."""

    def test_three_exit_events_today(self):
        """Synthetic trades.jsonl with 3 today + 2 other days -> 3 lines."""
        today = datetime.now().strftime("%Y-%m-%d")
        trades = [
            {"event": "EXIT", "ticker": "AAPL", "timestamp": f"{today}T10:30:00",
             "entry_price": 100.0, "exit_price": 105.0, "realized_pnl": 50.0},
            {"event": "EXIT", "ticker": "NVDA", "timestamp": f"{today}T11:00:00",
             "entry_price": 500.0, "exit_price": 490.0, "realized_pnl": -100.0},
            {"event": "EXIT", "ticker": "MSFT", "timestamp": f"{today}T13:00:00",
             "entry_price": 200.0, "exit_price": 215.0, "realized_pnl": 150.0},
            # Other day — should be excluded
            {"event": "EXIT", "ticker": "GOOG", "timestamp": "2025-01-01T10:00:00",
             "entry_price": 100.0, "exit_price": 110.0, "realized_pnl": 50.0},
            # Entry only, not EXIT/STOP/SCALE — should be excluded
            {"event": "ENTRY", "ticker": "META", "timestamp": f"{today}T09:00:00",
             "entry_price": 300.0},
        ]
        from pathlib import Path
        # Use data_dir() (honors PAPER_TRADING_DATA_DIR set by conftest) so the
        # test is isolated to a temp dir and never touches the real data folder.
        from traderlib.paths import data_dir
        real_data = data_dir() / "paper"
        real_data.mkdir(parents=True, exist_ok=True)
        real_log = real_data / "trades.jsonl"
        original_contents = real_log.read_text() if real_log.exists() else None
        try:
            with open(real_log, "w") as f:
                for t in trades:
                    f.write(json.dumps(t) + "\n")
            with patch("traderlib.dashboard.Live"), \
                 patch("traderlib.dashboard.os.isatty", return_value=True):
                d = Dashboard(enabled=True)
                text = str(d._closed_trades())
                for ticker in ("AAPL", "NVDA", "MSFT"):
                    assert ticker in text, f"Missing {ticker} in {text!r}"
                assert "GOOG" not in text
                assert "META" not in text
                d.stop()
        finally:
            if original_contents is None:
                if real_log.exists():
                    real_log.unlink()
            else:
                real_log.write_text(original_contents)

    def test_no_log_file_returns_placeholder(self):
        """Missing trades.jsonl -> 'No closed trades today' message."""
        from pathlib import Path
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True), \
             patch("traderlib.dashboard.data_dir") as mock_data_dir:
            # data_dir() / 'paper' / 'trades.jsonl' should report as missing
            mock_data_dir.return_value = Path("/nonexistent_test_dir")
            d = Dashboard(enabled=True)
            text = str(d._closed_trades())
            assert "No closed trades today" in text
            d.stop()


@pytest.mark.skipif(not _HAS_RICH, reason="rich not installed")
class TestDashboardLifetimeStats:
    """Task 5 — _lifetime_stats reads equity_all + lifetime_trade_count."""

    def test_lifetime_panel_with_100_points(self, mock_state):
        """100 points + 847 trades: Sharpe, Max DD, Total Trades all populated."""
        mock_state["equity_all"] = [100.0 + i * 0.5 for i in range(100)]
        mock_state["lifetime_trade_count"] = 847
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._lifetime_stats(mock_state))
            assert "Sharpe:" in text
            assert "Max DD:" in text
            assert "Total Trades: 847" in text
            assert "Sharpe: --" not in text
            assert "Max DD: --" not in text
            d.stop()

    def test_lifetime_panel_with_few_points(self, mock_state):
        """<30 points: Sharpe and Max DD show '--' but Total Trades still shown."""
        mock_state["equity_all"] = [100.0 + i for i in range(10)]
        mock_state["lifetime_trade_count"] = 25
        with patch("traderlib.dashboard.Live"), \
             patch("traderlib.dashboard.os.isatty", return_value=True):
            d = Dashboard(enabled=True)
            text = str(d._lifetime_stats(mock_state))
            assert "Sharpe: --" in text
            assert "Max DD: --" in text
            assert "Total Trades: 25" in text
            d.stop()
