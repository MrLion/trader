#!/usr/bin/env python3
"""TUI Dashboard for paper engine using rich."""

import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from traderlib.paths import data_dir

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
        self._last_update_time: Optional[datetime] = None
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
        self._last_update_time = datetime.now()
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
        """Build the full dashboard renderable.

        Reads self.console.height and gates optional sections by tier:
          - < 24 rows: header, stats, footer (minimum)
          - 24-34 rows: header, stats, today, positions capped at 6, footer
          - 35-49 rows: header, stats, today, positions capped at 10, activity capped at 5,
                        sparkline, footer
          - >= 50 rows: header, stats, today, all positions, all activity, sparkline,
                        sectors, footer; post-market adds closed-trades + lifetime panel

        The market-state conditional is applied per tier: post-market replaces
        activity with closed trades and adds the lifetime panel.
        """
        if not _HAS_RICH:
            return ""

        state = state or self._last_state or {}
        width = getattr(self.console, "width", 80) if self.console else 80
        height = getattr(self.console, "height", 24) if self.console else 24
        rule = Text("─" * width, style="dim")
        positions_rule = Text("─" * width, style="dim")
        is_post = state.get("market_status") == "POST"

        if height < 24:
            # Minimum view: header, stats, footer only
            return Group(
                rule,
                self._header(state),
                rule,
                self._stats(state),
                rule,
                self._footer(state),
                rule,
            )

        # Tier 24+ always has: header, stats, today, positions (capped or full)
        parts: list = [
            rule,
            self._header(state),
            rule,
            self._stats(state),
            rule,
            self._today_summary(state),
            positions_rule,
        ]

        if height < 35:
            # 24-34: positions capped at 6, no activity / sparkline / sectors
            parts.append(self._positions(state, max_rows=6))
        elif height < 50:
            # 35-49: positions capped at 10, activity capped at 5, sparkline,
            # but no sectors, no closed trades, no lifetime panel
            parts.append(self._positions(state, max_rows=10))
            parts.append(positions_rule)
            if is_post:
                parts.append(self._closed_trades(max_events=5))
            else:
                parts.append(self._activity(max_events=5))
            parts.append(rule)
            parts.append(self._equity_sparkline(state))
        else:
            # 50+: full layout — all positions, all activity/closed-trades,
            # sparkline, sectors, lifetime panel (post-market only)
            parts.append(self._positions(state))
            parts.append(positions_rule)
            if is_post:
                parts.append(self._closed_trades())
                parts.append(rule)
                parts.append(self._lifetime_stats(state))
            else:
                parts.append(self._activity())
            parts.append(rule)
            parts.append(self._equity_sparkline(state))
            parts.append(rule)
            parts.append(self._sector_exposure(state))

        parts.append(rule)
        parts.append(self._footer(state))
        parts.append(rule)
        return Group(*parts)

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

        if market == "POST":
            market_color = "yellow"
            market_label = "POST-MARKET SUMMARY"
        else:
            market_color = "green" if market == "OPEN" else "red"
            market_label = f"MARKET {market}"
        vix_val = state.get("vix")
        vix_color = "white"
        if vix_val is not None:
            if vix_val > 30:
                vix_color = "red"
            elif vix_val > 20:
                vix_color = "yellow"
        ws_color = "green" if state.get("ws_connected") else "red"

        mode = state.get("mode", "PAPER")
        mode_color = "green" if mode.upper() == "LIVE" else "cornflower_blue"
        regime = state.get("regime", "UNKNOWN")
        regime_color = {"BULL": "green", "BEAR": "red", "NEUTRAL": "yellow"}.get(regime, "dim")

        parts = [
            (f"  {mode.upper()} ENGINE", f"bold {mode_color}"),
            "    ",
            (now, "bold white"), " ET    ",
            (market_label, f"bold {market_color}"), "    ",
            (regime, f"bold {regime_color}"), "    ",
            "VIX ", (f"{vix}", vix_color), "    ",
            "WS: ", (ws, ws_color), "    ",
            "API: ", (api, api_color),
        ]

        if market != "OPEN" and self._last_update_time:
            frozen_time = self._last_update_time.strftime("%H:%M:%S")
            parts.extend([
                "  |  ",
                (f"Data frozen since {frozen_time}", "bold red"),
            ])

        return Text.assemble(*parts)

    def _stats(self, state: Dict[str, Any]) -> Text:
        # Account value = cash + equity (market value of open positions).
        # The engine sends "equity" meaning position market value, and "cash"
        # meaning cash on hand. Account value is their sum.
        cash = float(state.get("cash") or 0.0)
        equity = float(state.get("equity") or 0.0)
        account_value = cash + equity
        day_pnl = float(state.get("day_pnl") or 0.0)
        unreal = float(state.get("unrealized_pnl") or 0.0)
        open_pos = state.get("open_positions", 0)
        pending = state.get("pending_orders", 0)
        ytd_pnl = float(state.get("ytd_pnl", 0.0) or 0.0)
        ytd_pnl_pct = float(state.get("ytd_pnl_pct", 0.0) or 0.0)

        day_color = "green" if day_pnl >= 0 else "red"
        unreal_color = "green" if unreal >= 0 else "red"
        ytd_color = "green" if ytd_pnl >= 0 else "red"

        # Portfolio heat calculation
        heat_pct, heat_bar = self._heat_gauge(state)
        heat_color = "green" if heat_pct < 3.0 else "yellow" if heat_pct < 5.0 else "red"

        # Visual hierarchy: ACCOUNT VALUE + DAY P&L bold and large; YTD next to DAY P&L
        # (semantic pairing: both are "how much did the account move" quantities).
        # YTD percent is dimmed; the YTD value itself is colored green/red.
        arrow = "▲" if day_pnl >= 0 else "▼"
        ytd_fragment = (
            f"  [bold {ytd_color}]YTD ${ytd_pnl:>+10,.0f}[/] [dim]({ytd_pnl_pct:+.1f}%)[/]"
            if ytd_pnl != 0.0
            else ""
        )
        lines = [
            f"  [bold white]ACCOUNT VALUE[/] [bold white]${account_value:>12,.2f}[/]  "
            f"[bold {day_color}]DAY P&L {arrow} ${day_pnl:>+10,.2f}[/]{ytd_fragment}",
            f"  [dim]CASH          ${cash:>12,.2f}           UNREALIZED    ${unreal:>+10,.2f}          OPEN      {open_pos}[/]",
            f"  [dim]PENDING       {pending:>12}          HEAT        [{heat_color}]{heat_bar}[/{heat_color}]   {heat_pct:.1f}%[/]",
        ]
        return Text.from_markup("\n".join(lines))

    def _heat_gauge(self, state: Dict[str, Any]) -> tuple[float, str]:
        """Calculate portfolio heat: total at-risk dollars / equity."""
        equity = state.get("equity", 0.0)
        if equity <= 0:
            return 100.0, "██████████"

        positions = state.get("positions", {})
        total_risk = 0.0
        for pos in positions.values():
            entry = float(pos.get("entry_price") or 0)
            initial_stop = float(pos.get("initial_stop_price") or pos.get("stop_price") or 0)
            shares = int(pos.get("shares") or 0)
            if entry > initial_stop > 0 and shares > 0:
                total_risk += (entry - initial_stop) * shares

        heat_pct = (total_risk / equity) * 100 if equity else 0.0
        # 10-char bar, max 6% = full bar
        max_heat = 6.0
        filled = int(min(heat_pct / max_heat, 1.0) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        return heat_pct, bar

    def _today_summary(self, state: Dict[str, Any]) -> Text:
        """One-line summary of today's closed trades."""
        today_stats = state.get("today_stats", {})
        if not today_stats:
            return Text.from_markup("  [dim]TODAY:  --  no closed trades yet[/]")

        wins = today_stats.get("wins", 0)
        losses = today_stats.get("losses", 0)
        total_pnl = today_stats.get("total_pnl", 0.0)
        avg_r = max(-10.0, min(10.0, today_stats.get("avg_r", 0.0)))
        total = wins + losses

        if total == 0:
            return Text.from_markup("  [dim]TODAY:  --  no closed trades yet[/]")

        pnl_color = "green" if total_pnl >= 0 else "red"
        win_rate = (wins / total * 100) if total > 0 else 0

        line = (
            f"  [white]TODAY:[/]  {wins}W / {losses}L  |  "
            f"[{pnl_color}]${total_pnl:>+,.0f}[/{pnl_color}]  |  "
            f"avg {avg_r:+.2f}R  |  {win_rate:.0f}% WR"
        )
        return Text.from_markup(line)

    def _positions(self, state: Dict[str, Any], max_rows: Optional[int] = None) -> Table:
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
        tbl.add_column("ENTRY", justify="right", style="white")
        tbl.add_column("CURRENT", justify="right")
        tbl.add_column("STOP", justify="right", style="white")
        tbl.add_column("TYPE", style="yellow")
        tbl.add_column("UNREAL", justify="right")
        tbl.add_column("R", justify="right")

        # Separator between header and data rows
        sep = Text("─" * 14, style="dim")
        tbl.add_row(sep, sep, sep, sep, sep, sep, sep)

        # Build per-ticker records so we can sort by |unreal| desc when truncating
        records = []
        for ticker, pos in positions.items():
            entry = float(pos.get("entry_price") or 0)
            current_price = pos.get("current_price")
            current = float(current_price) if current_price is not None else entry
            stop = float(pos.get("stop_price") or 0)
            initial_stop = float(pos.get("initial_stop_price") or 0)
            shares = int(pos.get("shares") or 0)
            ptype_raw = pos.get("current_stop_type", "HARD")
            ptype = {
                "HARD": "H", "TRAILING": "T", "BREAKEVEN": "B",
                "EMA10": "0", "EMA21": "2", "EMA50": "5",
                "SCALE_OUT": "S", "UNSYNCED": "!",
            }.get(ptype_raw, ptype_raw[:1])
            unreal = (current - entry) * shares if entry else 0.0

            # R-multiple calculation uses initial stop (fallback to current stop)
            effective_stop = initial_stop if initial_stop > 0 else stop
            risk_per_share = entry - effective_stop if entry > effective_stop > 0 else 0
            r_mult = unreal / (risk_per_share * shares) if risk_per_share > 0 and shares > 0 else 0.0

            records.append({
                "ticker": ticker,
                "entry": entry,
                "current": current,
                "stop": stop,
                "ptype": ptype,
                "unreal": unreal,
                "r_mult": r_mult,
                "abs_unreal": abs(unreal),
            })

        # When max_rows is set and we have more positions than that, sort by
        # |unreal| desc and take the top N (most informative when truncating).
        truncated = max_rows is not None and len(records) > max_rows
        if truncated:
            records = sorted(records, key=lambda r: r["abs_unreal"], reverse=True)[:max_rows]

        for rec in records:
            r_mult = rec["r_mult"]
            # Row color based on R-level
            if r_mult < 0:
                row_style = "red"
            elif r_mult < 1:
                row_style = "yellow"
            elif r_mult < 2:
                row_style = "green"
            else:
                row_style = "bold green"

            cur_color = "green" if rec["current"] >= rec["entry"] else "red"
            unreal_color = "green" if rec["unreal"] >= 0 else "red"

            tbl.add_row(
                Text(rec["ticker"], style=row_style),
                Text(f"{rec['entry']:.2f}", style=row_style),
                Text(f"{rec['current']:.2f}", style=cur_color),
                Text(f"{rec['stop']:.2f}", style=row_style),
                Text(rec["ptype"], style=row_style),
                Text(f"{rec['unreal']:+.2f}", style=unreal_color),
                Text(f"{r_mult:+.1f}R", style=row_style),
            )

        if truncated:
            hidden = len(positions) - max_rows
            more_text = Text(f"+{hidden} more positions", style="dim italic")
            tbl.add_row(more_text, "", "", "", "", "", "")

        if not positions:
            tbl.add_row("--", "--", "--", "--", "--", "--", "--")

        return tbl

    def _activity(self, max_events: Optional[int] = None) -> Text:
        if not self.events:
            return Text("  No events yet", style="dim")

        icons = {
            "ENTRY": "+",
            "EXIT":  "x",
            "STOP":  "*",
            "SKIP":  "-",
            "ERROR": "!",
            "WARN":  "?",
        }
        colors = {
            "ENTRY": "cyan",
            "STOP": "yellow",
            "SKIP": "dim",
            "ERROR": "red",
            "WARN":  "yellow",
        }

        # Default cap is 10 when caller doesn't specify (preserves existing behavior)
        cap = max_events if max_events is not None else 10
        event_list = list(self.events)[:cap]
        truncated = max_events is not None and len(self.events) > cap

        lines = []
        for evt in event_list:
            etype = evt.get("type", "UNKNOWN")
            icon = icons.get(etype, " ")
            color = "green" if etype == "EXIT" and evt.get("pnl", 0) >= 0 else                     "red" if etype == "EXIT" and evt.get("pnl", 0) < 0 else                     colors.get(etype, "white")
            ts = evt.get("timestamp", "--:--:--")
            ticker = evt.get("ticker", "")
            detail = evt.get("detail", "")
            pnl = evt.get("pnl")
            r_mult = evt.get("r_multiple")
            pnl_str = f"  [{color}]{pnl:+.0f}[/{color}]" if pnl is not None else ""
            # Append R-multiple suffix to exit/stop/scale lines when present
            r_suffix = ""
            if etype in ("EXIT", "STOP", "SCALE") and r_mult is not None:
                r_color = "red" if r_mult < 0 else "yellow" if r_mult < 1 else "green"
                r_suffix = f" ([{r_color}]{r_mult:+.1f}R[/{r_color}])"
            lines.append(f"  [{color}]{icon}[/{color}] {ts}  [{color}]{etype:<6}[/{color}]  {ticker:<6}  {detail}{pnl_str}{r_suffix}")

        if truncated:
            hidden = len(self.events) - cap
            lines.append(f"  [dim italic]+{hidden} more events[/dim italic]")

        return Text.from_markup("\n".join(lines))

    def _sector_exposure(self, state: Dict[str, Any]) -> Text:
        """Horizontal bar chart of sector exposure as % of equity."""
        equity = float(state.get("equity") or 0.0)
        positions = state.get("positions", {})
        if not positions or equity <= 0:
            return Text("")

        from traderlib.sector_resolver import SectorResolver
        resolver = SectorResolver()

        # Aggregate by sector
        sector_values: Dict[str, float] = {}
        resolved_sectors: Dict[str, str] = {}
        for ticker, pos in positions.items():
            sector = pos.get("sector", "Unknown")
            if sector == "Unknown":
                sector = resolver.resolve(ticker)
            resolved_sectors[ticker] = sector
            current = float(pos.get("current_price") or pos.get("entry_price", 0))
            shares = int(pos.get("shares") or 0)
            sector_values[sector] = sector_values.get(sector, 0.0) + current * shares

        # Sort by value descending
        sorted_sectors = sorted(sector_values.items(), key=lambda x: x[1], reverse=True)

        lines = ["  [bold white]SECTOR EXPOSURE[/]          % of Equity"]
        for sector, value in sorted_sectors:
            pct = (value / equity) * 100
            filled = int(min(pct / 3.0, 1.0) * 10)  # 3% = full bar
            bar = "█" * filled + "░" * (10 - filled)
            pos_count = sum(1 for s in resolved_sectors.values() if s == sector)
            lines.append(f"  {sector:<14} [{bar}]  {pct:>5.1f}% ({pos_count} pos)")

        return Text.from_markup("\n".join(lines))

    def _equity_sparkline(self, state: Dict[str, Any]) -> Text:
        """30-cell Unicode block sparkline of equity_30d with a $NNN.NK label.

        Scaled to the min/max of the equity series. Pads on the left with
        ░ when fewer than 30 points are available. Empty series -> a flat
        30-cell ░ line with '--' as the value.
        """
        cells = 30
        equity = list(state.get("equity_30d") or [])

        if not equity or len(equity) < 2:
            line = "  [dim]" + "░" * cells + "[/dim]  [dim]--[/dim]"
            return Text.from_markup(line)

        # Scale to min/max using 8 block levels (▁▂▃▄▅▆▇█)
        blocks = "▁▂▃▄▅▆▇█"
        lo, hi = min(equity), max(equity)
        if hi == lo:
            scaled = "▅" * len(equity)  # flat -> middle block
        else:
            scaled = "".join(
                blocks[min(len(blocks) - 1, int((v - lo) / (hi - lo) * (len(blocks) - 1)))]
                for v in equity
            )

        # Pad on the left if fewer than 30 points
        if len(scaled) < cells:
            scaled = "░" * (cells - len(scaled)) + scaled

        # Value label: $NNN.NK for < $1M, $N.NNM for >= $1M
        current = equity[-1]
        if current >= 1_000_000:
            label = f"${current/1_000_000:.1f}M"
        else:
            label = f"${current/1_000:.1f}K"
        label = f"  [white]EQUITY (30D)[/]  {scaled}  [bold white]{label}[/]"
        return Text.from_markup(label)

    def _closed_trades(self, max_events: Optional[int] = None) -> Text:
        """Post-market: today's closed trades from the on-disk trade log.

        Reads data/paper/trades.jsonl on demand (live data, not pre-fetched).
        Filters to today's EXIT / STOP / SCALE events with an exit_price set,
        sorts by timestamp descending, and renders as
        `icon HH:MM  TYPE  TICKER  entry->exit  pnl`.

        Caps at max_events and appends '+N more closed trades' when truncated.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        # Mode-scoped via data_dir() so PAPER_TRADING_DATA_DIR and per-mode
        # subdirectories are honored (paper/ vs live/).
        log_path = data_dir() / 'paper' / 'trades.jsonl'
        if not log_path.exists():
            return Text("  [dim]No closed trades today[/]")

        rows = []
        try:
            with open(log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trade = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if trade.get("event") not in ("EXIT", "STOP", "SCALE"):
                        continue
                    ts = trade.get("timestamp", "")
                    if not ts.startswith(today):
                        continue
                    if not trade.get("exit_price"):
                        continue
                    rows.append(trade)
        except Exception:
            return Text("  [dim]No closed trades today[/]")

        if not rows:
            return Text("  [dim]No closed trades today[/]")

        # Most recent first
        rows.sort(key=lambda t: t.get("timestamp", ""), reverse=True)

        cap = max_events if max_events is not None else len(rows)
        visible = rows[:cap]
        truncated = max_events is not None and len(rows) > cap

        icons = {"EXIT": "x", "STOP": "*", "SCALE": ">"}
        lines = ["  [bold white]CLOSED TRADES[/]"]
        for trade in visible:
            etype = trade.get("event", "EXIT")
            icon = icons.get(etype, " ")
            ts = trade.get("timestamp", "")[11:16]  # HH:MM
            ticker = trade.get("ticker", "")
            entry = float(trade.get("entry_price", 0) or 0)
            exit_price = float(trade.get("exit_price", 0) or 0)
            pnl = float(trade.get("realized_pnl", 0) or 0)
            pnl_color = "green" if pnl >= 0 else "red"
            price_str = f"${entry:.2f}->${exit_price:.2f}"
            lines.append(
                f"  [{pnl_color}]{icon}[/{pnl_color}] {ts}  "
                f"[{pnl_color}]{etype:<6}[/{pnl_color}]  {ticker:<6}  {price_str}  "
                f"[{pnl_color}]{pnl:+.0f}[/{pnl_color}]"
            )

        if truncated:
            hidden = len(rows) - cap
            lines.append(f"  [dim italic]+{hidden} more closed trades[/dim italic]")

        return Text.from_markup("\n".join(lines))

    def _lifetime_stats(self, state: Dict[str, Any]) -> Text:
        """Post-market 50-row only: Sharpe / Max DD / Total Trades.

        Computes Sharpe + Max DD via StatsCalculator.lifetime_stats(equity_all).
        Total Trades is read directly from state. Below the 30-point threshold,
        Sharpe and Max DD are shown as '--'. Total Trades is always shown.
        """
        equity_all = list(state.get("equity_all") or [])
        lifetime_count = int(state.get("lifetime_trade_count", 0) or 0)

        try:
            from traderlib.stats_calculator import lifetime_stats
            stats = lifetime_stats(equity_all)
        except Exception:
            stats = {"sharpe": None, "max_dd": None}

        sharpe = stats.get("sharpe")
        max_dd = stats.get("max_dd")

        if sharpe is None:
            sharpe_str = "--"
        else:
            # Clamp to a sensible display range — extreme values come from
            # tiny sample sizes or volatile periods and are noise, not signal.
            sharpe_clamped = max(-9.99, min(9.99, sharpe))
            sharpe_str = f"{sharpe_clamped:.2f}"
        if max_dd is None:
            max_dd_str = "--"
        else:
            # Max DD is bounded [0, 1] in fractional form; clamp anyway to
            # defend against NaN/inf in pathological edge cases.
            max_dd_clamped = max(0.0, min(1.0, max_dd))
            max_dd_str = f"{max_dd_clamped * 100:.1f}%"

        line = (
            f"  [bold white]LIFETIME[/]  "
            f"Sharpe: [white]{sharpe_str}[/]  "
            f"Max DD: [white]{max_dd_str}[/]  "
            f"Total Trades: [white]{lifetime_count}[/]"
        )
        return Text.from_markup(line)

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
