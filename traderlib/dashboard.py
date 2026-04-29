#!/usr/bin/env python3
"""TUI Dashboard for paper engine using rich."""

import os
import threading
import time
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
        self._next_scan_target: Optional[float] = None
        self._timer_thread: Optional[threading.Thread] = None
        self._timer_stop = threading.Event()

        if self.enabled:
            self.console = Console()
            self.live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=2,
                screen=True,
            )
            self.live.start()
            self._start_timer()

    def _start_timer(self):
        """Start background thread that re-renders every second."""
        self._timer_stop.clear()
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def _timer_loop(self):
        """Re-render dashboard every second for live clock/countdown."""
        while not self._timer_stop.is_set():
            time.sleep(1.0)
            if self.enabled and self.live:
                self.live.update(self._render())

    def stop(self):
        """Stop the live display and timer thread."""
        if self.enabled and self.live:
            self._timer_stop.set()
            if self._timer_thread:
                self._timer_thread.join(timeout=2.0)
            self.live.stop()
            self.enabled = False

    def stop_now(self):
        """Immediate stop without waiting for timer thread.

        Safe to call from signal handlers. Restores the normal terminal screen
        immediately so subsequent print() output is visible.
        """
        if self.enabled and self.live:
            self._timer_stop.set()
            self.live.stop()
            self.enabled = False

    def update(self, state: Dict[str, Any]) -> None:
        """Refresh dashboard with new state and compute countdown target."""
        if not self.enabled:
            return
        self._last_state = state
        # Compute countdown target from monotonic clock
        next_scan = state.get("next_scan_seconds", 30)
        self._next_scan_target = time.monotonic() + next_scan
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
        width = getattr(self.console, "width", 80) if self.console else 80
        rule = Text("─" * width, style="dim")
        positions_rule = Text("─" * width, style="dim")
        return Group(
            rule,
            self._header(state),
            rule,
            self._stats(state),
            rule,
            self._at_risk_banner(state),
            self._today_summary(state),
            positions_rule,
            self._positions(state),
            positions_rule,
            self._activity(),
            rule,
            self._footer(state),
            rule,
        )

    def _header(self, state: Dict[str, Any]) -> Text:
        now = datetime.now().strftime("%H:%M:%S")
        market = state.get("market_status", "UNKNOWN")
        vix = state.get("vix", "--")
        ws = "connected" if state.get("ws_connected") else "disconnected"
        req = state.get("api_requests")
        max_req = state.get("api_max")
        if req is None or max_req is None:
            api = "--"
            api_color = "dim"
        else:
            api = f"{req}/{max_req}"
            api_pct = (req / max_req) if max_req else 0
            api_color = "yellow" if api_pct > 0.8 else "white"

        market_color = "green" if market == "OPEN" else "red"
        vix_val = state.get("vix")
        vix_color = "white"
        if vix_val is not None:
            if vix_val > 30:
                vix_color = "red"
            elif vix_val > 20:
                vix_color = "yellow"
        ws_color = "green" if state.get("ws_connected") else "red"

        return Text.assemble(
            "  PAPER ENGINE    ",
            (now, "bold white"), " ET    ",
            (f"MARKET {market}", f"bold {market_color}"), "    ",
            "VIX ", (f"{vix}", vix_color), "    ",
            "WS: ", (ws, ws_color), "    ",
            "API: ", (api, api_color),
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

        # Portfolio heat calculation
        heat_pct, heat_bar = self._heat_gauge(state)
        heat_color = "green" if heat_pct < 3.0 else "yellow" if heat_pct < 5.0 else "red"

        lines = [
            f"  EQUITY        ${equity:,.2f}          [bold {day_color}]DAY P&L       ${day_pnl:+.2f}[/]          OPEN POS      {open_pos}",
            f"  CASH          ${cash:,.2f}           [bold {unreal_color}]UNREALIZED    ${unreal:+.2f}[/]          PENDING       {pending}",
            f"  HEAT          [{heat_color}]{heat_bar}[/{heat_color}]   {heat_pct:.1f}%",
        ]
        return Text.from_markup("\n".join(lines))

    def _heat_gauge(self, state: Dict[str, Any]) -> tuple[float, str]:
        """Calculate portfolio heat: total at-risk dollars / equity."""
        equity = state.get("equity", 0.0)
        if equity <= 0:
            return 0.0, "░░░░░░░░░░"

        positions = state.get("positions", {})
        total_risk = 0.0
        for pos in positions.values():
            entry = float(pos.get("entry_price") or 0)
            stop = float(pos.get("stop_price") or 0)
            shares = int(pos.get("shares") or 0)
            if entry > stop > 0 and shares > 0:
                total_risk += (entry - stop) * shares

        heat_pct = (total_risk / equity) * 100 if equity else 0.0
        # 10-char bar, max 6% = full bar
        max_heat = 6.0
        filled = int(min(heat_pct / max_heat, 1.0) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        return heat_pct, bar

    def _at_risk_banner(self, state: Dict[str, Any]) -> Text:
        """Banner showing positions close to their stop or losing money."""
        positions = state.get("positions", {})
        if not positions:
            return Text("")

        at_risk = []
        for ticker, pos in positions.items():
            entry = float(pos.get("entry_price") or 0)
            current = float(pos.get("current_price") or entry)
            stop = float(pos.get("stop_price") or 0)
            shares = int(pos.get("shares") or 0)

            if entry <= 0 or stop <= 0 or shares <= 0:
                continue

            risk_per_share = entry - stop
            unreal = (current - entry) * shares
            r_mult = unreal / (risk_per_share * shares) if risk_per_share > 0 else 0

            # Flag if within 0.5R of stop OR below entry
            if r_mult < 0 or (risk_per_share > 0 and (current - stop) / risk_per_share < 0.5):
                dist_pct = ((current - stop) / risk_per_share * 100) if risk_per_share > 0 else 0
                at_risk.append((ticker, r_mult, dist_pct))

        if not at_risk:
            return Text("")

        parts = []
        for ticker, r_mult, dist_pct in at_risk:
            color = "red" if r_mult < 0 else "yellow"
            parts.append(f"[{color}]{ticker} ({r_mult:+.1f}R, {dist_pct:.0f}% to stop)[/{color}]")

        banner = "  [!] AT RISK:  " + "  |  ".join(parts)
        return Text.from_markup(banner)

    def _today_summary(self, state: Dict[str, Any]) -> Text:
        """One-line summary of today's closed trades."""
        today_stats = state.get("today_stats", {})
        if not today_stats:
            return Text("")

        wins = today_stats.get("wins", 0)
        losses = today_stats.get("losses", 0)
        total_pnl = today_stats.get("total_pnl", 0.0)
        avg_r = today_stats.get("avg_r", 0.0)
        total = wins + losses

        if total == 0:
            return Text("")

        pnl_color = "green" if total_pnl >= 0 else "red"
        win_rate = (wins / total * 100) if total > 0 else 0

        line = (
            f"  [white]TODAY:[/]  {wins}W / {losses}L  |  "
            f"[{pnl_color}]${total_pnl:>+,.0f}[/{pnl_color}]  |  "
            f"avg {avg_r:+.1f}R  |  {win_rate:.0f}% WR"
        )
        return Text.from_markup(line)

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

        # Separator between header and data rows
        sep = Text("─" * 14, style="dim")
        tbl.add_row(sep, sep, sep, sep, sep, sep, sep, sep)

        for ticker, pos in positions.items():
            entry = float(pos.get("entry_price") or 0)
            current_price = pos.get("current_price")
            current = float(current_price) if current_price is not None else entry
            stop = float(pos.get("stop_price") or 0)
            shares = int(pos.get("shares") or 0)
            ptype = pos.get("current_stop_type", "HARD")
            phase = pos.get("exit_phase", "P1")
            unreal = (current - entry) * shares if entry else 0.0

            # R-multiple calculation
            risk_per_share = entry - stop if entry > stop > 0 else 0
            r_mult = unreal / (risk_per_share * shares) if risk_per_share > 0 and shares > 0 else 0.0

            # Row color based on R-level
            if r_mult < 0:
                row_style = "red"
            elif r_mult < 1:
                row_style = "yellow"
            elif r_mult < 2:
                row_style = "green"
            else:
                row_style = "bold green"

            cur_color = "green" if current >= entry else "red"
            unreal_color = "green" if unreal >= 0 else "red"
            r_color = "green" if r_mult >= 0 else "red"

            tbl.add_row(
                Text(ticker, style=row_style),
                Text(phase, style=row_style),
                Text(f"{entry:.2f}", style=row_style),
                Text(f"{current:.2f}", style=cur_color),
                Text(f"{stop:.2f}", style=row_style),
                Text(ptype, style=row_style),
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
        # Live countdown from target time
        if self._next_scan_target is not None:
            remaining = int(self._next_scan_target - time.monotonic())
            next_scan = max(0, remaining)
        else:
            next_scan = state.get("next_scan_seconds", 30)

        market_close = state.get("market_close_seconds")
        ws = "connected" if state.get("ws_connected") else "disconnected"
        req = state.get("api_requests")
        max_req = state.get("api_max")

        close_str = f"{market_close//3600}h {(market_close%3600)//60}m" if market_close is not None else "--"
        close_color = "white"
        if market_close is not None:
            if market_close < 300:
                close_color = "red"
            elif market_close < 1800:
                close_color = "yellow"

        ws_color = "green" if state.get("ws_connected") else "red"

        if req is None or max_req is None:
            rate_str = "--"
            rate_color = "dim"
        else:
            rate_str = f"{req}/{max_req}"
            api_pct = (req / max_req) if max_req else 0
            rate_color = "white"
            if api_pct >= 1.0:
                rate_color = "red"
            elif api_pct > 0.8:
                rate_color = "yellow"

        # Cooldowns
        cooldowns = state.get("cooldowns", {})
        if cooldowns:
            cd_parts = [f"{t}({int(m)}m)" for t, m in sorted(cooldowns.items())]
            cd_str = "  COOLDOWNS: " + "  |  ".join(cd_parts)
        else:
            cd_str = ""

        return Text.assemble(
            "  Next scan: ", (f"{next_scan}s", "white"), "    ",
            "Market closes in: ", (close_str, close_color), "    ",
            "WebSocket: ", (ws, ws_color), "    ",
            "Rate limit: ", (rate_str, rate_color),
            (cd_str, "dim") if cd_str else "",
        )
