#!/usr/bin/env python3
"""TUI Dashboard for paper engine using rich."""

import os
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


class Dashboard:
    """TUI dashboard for paper engine. Falls back to no-op if rich unavailable."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and _HAS_RICH and os.isatty(1)
        self.console: Optional[Any] = None
        self.live: Optional[Any] = None
        self.events: deque = deque(maxlen=20)

        if self.enabled:
            self.console = Console()
            self.live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=2,
                screen=True,
            )
            self.live.start()

    def stop(self):
        """Stop the live display."""
        if self.enabled and self.live:
            self.live.stop()
            self.enabled = False

    def update(self, state: Dict[str, Any]) -> None:
        """Refresh dashboard with new state."""
        if not self.enabled:
            return
        self.live.update(self._render(state))

    def log_event(self, event: Dict[str, Any]) -> None:
        """Add an event to the activity log."""
        self.events.appendleft(event)
        if self.enabled:
            self.live.update(self._render())

    def _render(self, state: Optional[Dict[str, Any]] = None) -> Any:
        """Build the full dashboard renderable."""
        if not _HAS_RICH:
            return ""

        state = state or {}
        return Group(
            self._header(state),
            self._stats(state),
            self._positions(state),
            self._activity(),
            self._footer(state),
        )

    def _header(self, state: Dict[str, Any]) -> Text:
        now = datetime.now().strftime("%H:%M:%S")
        market = state.get("market_status", "UNKNOWN")
        vix = state.get("vix", "--")
        ws = "connected" if state.get("ws_connected") else "disconnected"
        api = f"{state.get('api_requests', 0)}/{state.get('api_max', 0)}"
        line = f"  PAPER ENGINE    {now} ET    MARKET {market}    VIX {vix}    WS: {ws}    API: {api}"
        return Text(line, style="bold white")

    def _stats(self, state: Dict[str, Any]) -> Text:
        equity = state.get("equity", 0.0)
        cash = state.get("cash", 0.0)
        day_pnl = state.get("day_pnl", 0.0)
        unreal = state.get("unrealized_pnl", 0.0)
        open_pos = state.get("open_positions", 0)
        pending = state.get("pending_orders", 0)

        day_color = "green" if day_pnl >= 0 else "red"
        unreal_color = "green" if unreal >= 0 else "red"

        lines = [
            f"  EQUITY        ${equity:,.2f}          [bold {day_color}]DAY P&L       ${day_pnl:+.2f}[/]          OPEN POS      {open_pos}",
            f"  CASH          ${cash:,.2f}           [bold {unreal_color}]UNREALIZED    ${unreal:+.2f}[/]          PENDING       {pending}",
        ]
        return Text.from_markup("\n".join(lines))

    def _positions(self, state: Dict[str, Any]) -> Table:
        positions = state.get("positions", {})
        tbl = Table(
            box=None,
            show_header=True,
            show_edge=False,
            show_lines=False,
            header_style="bold white",
            padding=(0, 2),
            expand=True,
        )
        tbl.add_column("TICKER", style="white")
        tbl.add_column("PHASE", style="cyan")
        tbl.add_column("ENTRY", justify="right", style="white")
        tbl.add_column("CURRENT", justify="right")
        tbl.add_column("STOP", justify="right", style="white")
        tbl.add_column("TYPE", style="yellow")
        tbl.add_column("UNREAL", justify="right")
        tbl.add_column("R", justify="right")

        for ticker, pos in positions.items():
            entry = float(pos.get("entry_price", 0))
            current = float(pos.get("current_price", entry))
            stop = float(pos.get("stop_price", 0))
            shares = int(pos.get("shares", 0))
            ptype = pos.get("current_stop_type", "HARD")
            phase = pos.get("exit_phase", "phase1")
            phase_label = "P1" if phase == "phase1" else "P2"

            unreal = (current - entry) * shares if entry else 0.0
            risk = (entry - stop) * shares if entry != stop else 1
            r_mult = unreal / risk if risk else 0.0

            cur_color = "green" if current >= entry else "red"
            unreal_color = "green" if unreal >= 0 else "red"
            r_color = "green" if r_mult >= 0 else "red"

            tbl.add_row(
                ticker,
                phase_label,
                f"{entry:.2f}",
                Text(f"{current:.2f}", style=cur_color),
                f"{stop:.2f}",
                ptype,
                Text(f"{unreal:+.2f}", style=unreal_color),
                Text(f"{r_mult:+.1f}", style=r_color),
            )

        if not positions:
            tbl.add_row("--", "--", "--", "--", "--", "--", "--", "--")

        return tbl

    def _activity(self) -> Text:
        if not self.events:
            return Text("  No events yet", style="dim")

        colors = {
            "ENTRY": "cyan",
            "EXIT": "green",
            "STOP": "yellow",
            "SKIP": "dim",
            "ERROR": "red",
            "WARN": "yellow",
        }

        lines = []
        # Show last 8 events in 2 columns
        event_list = list(self.events)[:8]
        for i in range(0, len(event_list), 2):
            left = event_list[i]
            right = event_list[i + 1] if i + 1 < len(event_list) else None

            ts = left.get("timestamp", "--:--:--")
            evt_type = left.get("type", "UNKNOWN")
            ticker = left.get("ticker", "")
            detail = left.get("detail", "")
            color = colors.get(evt_type, "white")
            left_str = f"[{ts}] [{color}]{evt_type}  {ticker} {detail}[/]"

            if right:
                ts2 = right.get("timestamp", "--:--:--")
                evt2 = right.get("type", "UNKNOWN")
                tkr2 = right.get("ticker", "")
                det2 = right.get("detail", "")
                col2 = colors.get(evt2, "white")
                right_str = f"[{ts2}] [{col2}]{evt2}  {tkr2} {det2}[/]"
            else:
                right_str = ""

            lines.append(f"  {left_str:<52}  {right_str}")

        return Text.from_markup("\n".join(lines))

    def _footer(self, state: Dict[str, Any]) -> Text:
        next_scan = state.get("next_scan_seconds", 30)
        market_close = state.get("market_close_seconds")
        ws = "connected" if state.get("ws_connected") else "disconnected"
        req = state.get("api_requests", 0)
        max_req = state.get("api_max", 500)

        close_str = f"{market_close//3600}h {(market_close%3600)//60}m" if market_close else "--"
        line = f"  Next scan: {next_scan}s    Market closes in: {close_str}    WebSocket: {ws}    Rate limit: {req}/{max_req}"
        return Text(line, style="dim")
