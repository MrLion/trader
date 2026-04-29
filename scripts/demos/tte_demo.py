#!/usr/bin/env python3
"""Demo of the terminaltexteffects library: Matrix rain, Slide, Fireworks."""

from terminaltexteffects.effects.effect_matrix import Matrix, MatrixConfig
from terminaltexteffects.effects.effect_slide import Slide, SlideConfig
from terminaltexteffects.effects.effect_fireworks import Fireworks, FireworksConfig


def run_effect(effect):
    """Run a single effect to completion, printing each frame."""
    try:
        with effect.terminal_output() as terminal:
            for frame in effect:
                terminal.print(frame)
    except KeyboardInterrupt:
        pass


def main():
    text = "TERMINAL TEXT EFFECTS DEMO"

    # ── Effect 1: Matrix digital rain ──────────────────────────────
    print("\n  [1/3] Matrix Rain -- digital rain resolves into your text")
    cfg = MatrixConfig._build_config()
    cfg.rain_time = 3
    run_effect(Matrix(input_data=text, effect_config=cfg))

    # ── Effect 2: Slide ────────────────────────────────────────────
    print("\n  [2/3] Slide -- text slides in from the edges")
    cfg = SlideConfig._build_config()
    cfg.grouping = "column"
    cfg.gap = 2
    cfg.movement_speed = 0.5
    cfg.merge = True
    run_effect(Slide(input_data=text, effect_config=cfg))

    # ── Effect 3: Fireworks ────────────────────────────────────────
    print("\n  [3/3] Fireworks -- text explodes onto the screen")
    cfg = FireworksConfig._build_config()
    cfg.firework_volume = 15
    cfg.launch_delay = 8
    cfg.explode_anywhere = False
    run_effect(Fireworks(input_data=text, effect_config=cfg))

    print("\n  Demo complete.")


if __name__ == "__main__":
    main()
