"""Render the cast standing on light- and dark-mode window title bars.

Each pet at Medium size (one sprite pixel = 4 device pixels on Retina) in a
few poses, plus a peek from the window edge. Usage:
    uv run python scripts/cast_showcase.py docs/screenshots/cast.png
"""

from __future__ import annotations

import sys

from nibble.core.canvas import Canvas, hex_rgb
from nibble.core.peek import clip, layout, orient
from nibble.core.spec import STANDING, load_builtin

CAST = ("pearl", "archie", "dewey", "kernel")
POSES = (("idle", 0), ("walk", 1), ("happy", 1), ("sideeye", 0), ("sleep", 0))
SLOT = 40
THEMES = (
    # (title bar, window body, desktop)
    ("#e8e6ea", "#ffffff", "#c9c4d8"),
    ("#2c2a33", "#1e1d24", "#3b3650"),
)


def main(out: str) -> None:
    rows = len(CAST)
    w = 16 + SLOT * (len(POSES) + 1) + 24
    band = 56
    c = Canvas(w * 2 + 8, rows * band + 8, hex_rgb("#15122b"))
    for t, (bar, body, desk) in enumerate(THEMES):
        ox = 4 + t * (w + 0)
        for r, pid in enumerate(CAST):
            pet = load_builtin(pid).feet_on_ground()
            worn = pet.default_worn
            pal = {k: hex_rgb(v) for k, v in pet.palette.items()}
            oy = 4 + r * band
            c.rect(ox, oy, w - 4, band - 4, hex_rgb(desk))  # desktop
            top = oy + 34
            c.rect(ox + 6, top, w - 16, 6, hex_rgb(bar))  # a window's title bar...
            c.rect(ox + 6, top + 6, w - 16, band - 4 - 40, hex_rgb(body))  # ...and body
            for i, (anim, idx) in enumerate(POSES):
                c.sprite(pet.frame(anim, idx, worn), pal, ox + 10 + i * SLOT, top - 32)
            # Peeking in from the window's right side.
            standing = [f for n in STANDING for f in pet.frames[n]]
            lay = layout(standing, 1, upright=False, look=1, scale=1)
            edge = ox + 6 + w - 16
            frame, anchor = clip(orient(pet.frame("idle", 0, worn), 1, False, 1), 1, lay.ref, round(lay.ref.width * 0.6))
            px, py = edge - anchor, top + 14 - (32 - (lay.ref.top + lay.ref.bottom + 1) // 2)
            c.sprite(frame, pal, px, py)
    c.save_png(out, scale=4)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots/cast.png")
