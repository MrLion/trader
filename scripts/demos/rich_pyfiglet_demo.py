#!/usr/bin/env python3
"""Demo: animated ASCII art banner using pyfiglet + ANSI escape codes.
Zero Rich dependency for the animation loop — clean Ctrl+C exit."""

import sys
import time
import signal
from pyfiglet import Figlet

TEXT = "TRADER"
FONT = "slant"
COLORS = [
    (0, 255, 0),    # green
    (255, 215, 0),  # gold
    (0, 255, 255),  # cyan
    (255, 0, 255),  # magenta
    (255, 60, 60),  # red
    (255, 255, 0),  # yellow
]

running = True

def on_exit(sig=None, frame=None):
    global running
    running = False

signal.signal(signal.SIGINT, on_exit)

# Generate figlet lines once
f = Figlet(font=FONT)
lines = f.renderText(TEXT).rstrip("\n").split("\n")

# Hide cursor, clear screen
sys.stdout.write("\033[?25l\033[2J")
sys.stdout.flush()

frame = 0
try:
    while running:
        offset = frame % len(COLORS)
        out = []
        for i, line in enumerate(lines):
            c1 = COLORS[(i + offset) % len(COLORS)]
            c2 = COLORS[(i + offset + 1) % len(COLORS)]
            r = int(c1[0] + (c2[0] - c1[0]) * 0.5)
            g = int(c1[1] + (c2[1] - c1[1]) * 0.5)
            b = int(c1[2] + (c2[2] - c1[2]) * 0.5)
            out.append(f"\033[38;2;{r};{g};{b}m{line}\033[0m")
        sys.stdout.write("\033[H" + "\n".join(out))
        sys.stdout.flush()
        frame += 1
        time.sleep(0.08)
except Exception:
    pass
finally:
    sys.stdout.write("\033[?25h\033[0m\033[2J\033[H")
    sys.stdout.flush()
    print("Demo complete.")
