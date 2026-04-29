#!/usr/bin/env python3
"""asciimatics demo: starfield, rainbow banners, and particle fireworks."""

import time
import threading
from asciimatics.screen import Screen
from asciimatics.scene import Scene
from asciimatics.effects import Stars, Print, Cycle
from asciimatics.renderers import FigletText, Rainbow, StaticRenderer
from asciimatics.particles import RingFirework, StarFirework, PalmFirework


def demo(screen: Screen):
    cx = screen.width // 2
    cy = screen.height // 2
    scenes = []

    # -- Scene 1: Starfield + Rainbow "ASCIIMATICS" banner --
    effects_1 = [
        Stars(screen, count=40, pattern="........++++________--------~~~~~~~~"),
        Stars(screen, count=25, pattern="........++++________--------"),
        Stars(screen, count=15, pattern="........++++"),
        Cycle(
            screen,
            Rainbow(screen, FigletText("ASCIIMATICS", font="big")),
            y=1,
        ),
        Print(
            screen,
            StaticRenderer(["Starfield + Rainbow Banner  |  Press Q to quit  |  Auto-exits in 6s"]),
            y=screen.height - 1,
            x=0,
            colour=Screen.COLOUR_WHITE,
            bg=Screen.COLOUR_BLACK,
        ),
    ]
    scenes.append(Scene(effects_1, duration=120, name="banner"))

    # -- Scene 2: Fireworks + "256 COLORS" banner --
    effects_2 = [
        Stars(screen, count=50, pattern="........++++________--------~~~~~~~~********"),
        Stars(screen, count=20, pattern="........++++"),
        Cycle(
            screen,
            Rainbow(screen, FigletText("256 COLORS", font="standard")),
            y=1,
        ),
        Print(
            screen,
            StaticRenderer(["Fireworks + Particles  |  %dx%d  |  Auto-exits" % (screen.width, screen.height)]),
            y=screen.height - 1,
            x=0,
            colour=Screen.COLOUR_WHITE,
            bg=Screen.COLOUR_BLACK,
        ),
        RingFirework(screen, x=cx // 2, y=cy + 2, life_time=45),
        RingFirework(screen, x=cx, y=cy + 2, life_time=55),
        RingFirework(screen, x=3 * cx // 2, y=cy + 2, life_time=65),
        StarFirework(screen, x=cx // 2, y=cy + 3, life_time=40),
        StarFirework(screen, x=3 * cx // 2, y=cy + 3, life_time=50),
        PalmFirework(screen, x=cx, y=cy + 4, life_time=80),
        PalmFirework(screen, x=cx // 2, y=cy + 4, life_time=90),
    ]
    scenes.append(Scene(effects_2, duration=120, name="fireworks"))

    # -- Scene 3: Particle burst finale --
    effects_3 = [
        Stars(screen, count=60, pattern="........++++________--------~~~~~~~~********####"),
        Stars(screen, count=30, pattern="........++++"),
        Cycle(
            screen,
            Rainbow(screen, FigletText("PARTICLES", font="big")),
            y=1,
        ),
        Print(
            screen,
            StaticRenderer(["Particle burst  |  %dx%d  |  Shutting down..." % (screen.width, screen.height)]),
            y=screen.height - 1,
            x=0,
            colour=Screen.COLOUR_WHITE,
            bg=Screen.COLOUR_BLACK,
        ),
        *[RingFirework(screen, x=cx, y=cy, life_time=30, start_frame=i * 10) for i in range(6)],
    ]
    scenes.append(Scene(effects_3, duration=120, name="particles"))

    # Auto-exit after 6s
    def auto_stop():
        time.sleep(6)
        screen.close()

    threading.Thread(target=auto_stop, daemon=True).start()
    screen.play(scenes, stop_on_resize=False, repeat=False)


if __name__ == "__main__":
    Screen.wrapper(demo, catch_interrupt=True, unicode_aware=True)
    print("\nDemo complete -- explore asciimatics for terminal UIs!")
