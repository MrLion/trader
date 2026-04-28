#!/usr/bin/env python3
"""TUI Dashboard for paper engine using rich."""

import os
from collections import deque
from datetime import datetime
from typing import Any, Dict, Optional

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
        self._last_state: Dict[str, Any] = {}

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
        self._last_state = state
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

        state = state or self._last_state or {}
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
        req = state.get("api_requests", 0)
        max_req = state.get("api_max", 500)
        api = f"{req}/{max_req}"

        market_color = "green" if market == "OPEN" else "red"
        vix_val = state.get("vix")
        vix_color = "white"
        if vix_val is not None:
            if vix_val > 30:
                vix_color = "red"
            elif vix_val > 20:
                vix_color = "yellow"
        ws_color = "green" if state.get("ws_connected") else "red"
        api_pct = (req / max_req) if max_req else 0
        api_color = "yellow" if api_pct > 0.8 else "white"

        return Text.assemble(
            "  PAPER ENGINE    ",
            (now, "bold white"), " ET    ",
            (f"MARKET {market}", f"bold {market_color}"), "    ",
            "VIX ", (str(vix), f"bold {vix_color}"), "    ",
            "WS: ", (ws, f"bold {ws_color}"), "    ",
            "API: ", (api, f"bold {api_color}"),
        )

    def _stats(self, state: Dict[str, Any]) -> Text:
        equity = float(state.get("equity") or 0.0)
        cash = float(state.get("cash") or 0.0)
        day_pnl = float(state.get("day_pnl") or 0.0)
        unreal = float(state.get("unrealized_pnl") or 0.0)
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
            entry = float(pos.get("entry_price") or 0)
            current_price = pos.get("current_price")
            current = float(current_price) if current_price is not None else entry
            stop = float(pos.get("stop_price") or 0)
            shares = int(pos.get("shares") or 0)
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

            def _color(evt):
                etype = evt.get("type", "UNKNOWN")
                if etype == "EXIT":
                    return "green" if evt.get("pnl", 0) >= 0 else "red"
                return colors.get(etype, "white")

            ts = left.get("timestamp", "--:--:--")
            evt_type = left.get("type", "UNKNOWN")
            ticker = left.get("ticker", "")
            detail = left.get("detail", "")
            color = _color(left)
            left_str = f"[{ts}] [{color}]{evt_type}  {ticker} {detail}[/]"

            if right:
                ts2 = right.get("timestamp", "--:--:--")
                evt2 = right.get("type", "UNKNOWN")
                tkr2 = right.get("ticker", "")
                det2 = right.get("detail", "")
                col2 = _color(right)
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

        close_str = f"{market_close//3600}h {(market_close%3600)//60}m" if market_close is not None else "--"
        close_color = "white"
        if market_close is not None:
            if market_close < 300:
                close_color = "red"
            elif market_close < 1800:
                close_color = "yellow"

        ws_color = "green" if state.get("ws_connected") else "red"
        api_pct = (req / max_req) if max_req else 0
        rate_color = "white"
        if api_pct >= 1.0:
            rate_color = "red"
        elif api_pct > 0.8:
            rate_color = "yellow"

        return Text.assemble(
            "  Next scan: ", (f"{next_scan}s", "white"), "    ",
            "Market closes in: ", (close_str, close_color), "    ",
            "WebSocket: ", (ws, ws_color), "    ",
            "Rate limit: ", (f"{req}/{max_req}", rate_color),
        )
