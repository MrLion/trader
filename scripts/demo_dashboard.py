#!/usr/bin/env python3
"""Demo script for the paper engine TUI dashboard mockup.
   No vertical dividers. No emojis. Color-coded text only.
"""

import random
import time
from datetime import datetime, timedelta

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

console = Console()

# ── Demo Data ──────────────────────────────────────────────────────────

positions = [
    {"ticker": "AAPL", "phase": "P1", "entry": 185.00, "current": 187.45, "stop": 180.00, "type": "HARD", "shares": 100},
    {"ticker": "MSFT", "phase": "P2", "entry": 405.00, "current": 412.30, "stop": 400.00, "type": "TRAIL", "shares": 50},
    {"ticker": "NVDA", "phase": "P1", "entry": 895.00, "current": 892.10, "stop": 850.00, "type": "HARD", "shares": 25},
]

events = [
    ("10:32:01", "ENTRY", "AAPL", "$187.45", "x100"),
    ("10:28:45", "EXIT", "TSLA", "", "+$450"),
    ("10:15:22", "STOP", "MSFT", "→ $400.00", "TRAIL"),
    ("10:05:00", "SKIP", "FLY", "cooldown", ""),
]


# ── Helpers ────────────────────────────────────────────────────────────

def hline(char: str = "─") -> Text:
    """Return a full-width horizontal rule."""
    return Text(char * console.width, style="dim")


def colored(val: float, prefix: str = "", suffix: str = "") -> Text:
    """Format a number with green/red color."""
    s = f"{prefix}{val:+.2f}{suffix}" if isinstance(val, float) else f"{prefix}{val}{suffix}"
    color = "green" if val >= 0 else "red"
    return Text(s, style=color if val != 0 else "white")


# ── Dashboard Sections ─────────────────────────────────────────────────

def header_band() -> Text:
    now = datetime.now().strftime("%H:%M:%S")
    txt = (
        f"  PAPER ENGINE    {now} ET    MARKET OPEN    "
        f"VIX 16.4    WS: connected    API: 12/500 2%"
    )
    return Text(txt, style="bold white")


def stats_block() -> Text:
    """Two rows of stats, space-separated columns. No tables, no vertical lines."""
    lines = []
    # Row 1
    lines.append(
        f"  EQUITY        $103,420.50          "
        f"DAY P&L       {colored(420.50, prefix='$').markup}          "
        f"OPEN POS      3"
    )
    # Row 2
    lines.append(
        f"  CASH          $45,200.00           "
        f"UNREALIZED    {colored(1150.00, prefix='$').markup}          "
        f"PENDING       0"
    )
    return Text.from_markup("\n".join(lines))


def positions_table() -> Table:
    """Positions table with NO vertical lines at all."""
    tbl = Table(
        box=None,           # <── no box drawing characters
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

    for pos in positions:
        unreal = (pos["current"] - pos["entry"]) * pos["shares"]
        risk = (pos["entry"] - pos["stop"]) * pos["shares"] if pos["entry"] != pos["stop"] else 1
        r_mult = unreal / risk if risk else 0

        cur_style = "green" if pos["current"] >= pos["entry"] else "red"
        unreal_style = "green" if unreal >= 0 else "red"
        r_style = "green" if r_mult >= 0 else "red"

        tbl.add_row(
            pos["ticker"],
            pos["phase"],
            f"{pos['entry']:.2f}",
            Text(f"{pos['current']:.2f}", style=cur_style),
            f"{pos['stop']:.2f}",
            pos["type"],
            Text(f"{unreal:+.2f}", style=unreal_style),
            Text(f"{r_mult:+.1f}", style=r_style),
        )
    return tbl


def activity_block() -> Text:
    """Activity log — plain text, two events per row. No tables, no vertical bars."""
    colors = {"ENTRY": "cyan", "EXIT": "green", "STOP": "yellow", "SKIP": "dim"}
    lines = []

    for i in range(0, len(events), 2):
        # Left event
        ts1, evt1, tkr1, det1, ex1 = events[i]
        c1 = colors.get(evt1, "white")
        left = f"[{ts1}] [{c1}]{evt1}  {tkr1} {det1} {ex1}[/]"

        # Right event (if exists)
        if i + 1 < len(events):
            ts2, evt2, tkr2, det2, ex2 = events[i + 1]
            c2 = colors.get(evt2, "white")
            right = f"[{ts2}] [{c2}]{evt2}  {tkr2} {det2} {ex2}[/]"
        else:
            right = ""

        lines.append(f"  {left:<52}  {right}")

    return Text.from_markup("\n".join(lines))


def footer_band(seconds_left: int) -> Text:
    txt = (
        f"  Next scan: {seconds_left}s    "
        f"Market closes in: 3h 28m    "
        f"WebSocket: connected    "
        f"Rate limit: 12/500"
    )
    return Text(txt, style="dim")


# ── Assembly ───────────────────────────────────────────────────────────

def build_dashboard(seconds_left: int = 28) -> Text:
    """Assemble the full dashboard as a single Text blob."""
    parts = [
        hline(),
        header_band(),
        hline(),
        "",
        stats_block(),
        "",
        hline(),
        Text("  OPEN POSITIONS", style="bold white"),
        hline(),
        positions_table(),
        "",
        hline(),
        Text("  RECENT ACTIVITY", style="bold white"),
        hline(),
        activity_block(),
        "",
        hline(),
        footer_band(seconds_left),
        hline(),
    ]
    # Render each part to lines and join
    out = Text()
    for p in parts:
        if isinstance(p, Text):
            out.append(p)
        elif isinstance(p, Table):
            # Rich Tables need a console to render; append their string representation
            # This is a workaround for mixing Table and Text in a Group-like way
            # We'll just let Live handle it by returning a Group from main()
            pass
        else:
            out.append(str(p))
        out.append("\n")
    return out


def build_group(seconds_left: int = 28):
    """Build a proper Group for Live rendering."""
    from rich.console import Group as RichGroup

    return RichGroup(
        hline(),
        header_band(),
        hline(),
        Text(""),
        stats_block(),
        Text(""),
        hline(),
        Text("  OPEN POSITIONS", style="bold white"),
        hline(),
        positions_table(),
        Text(""),
        hline(),
        Text("  RECENT ACTIVITY", style="bold white"),
        hline(),
        activity_block(),
        Text(""),
        hline(),
        footer_band(seconds_left),
        hline(),
    )


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("Paper Engine Dashboard Demo")
    print("Press Ctrl+C to exit\n")

    seconds_left = 28
    live = Live(build_group(seconds_left), console=console, refresh_per_second=2, screen=True)
    with live:
        while True:
            time.sleep(0.5)
            seconds_left -= 1
            if seconds_left < 0:
                seconds_left = 30

            for pos in positions:
                pos["current"] += random.uniform(-0.05, 0.05)

            live.update(build_group(seconds_left))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.clear()
        console.print("Demo stopped.")
