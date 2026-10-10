"""Render sprite sheets for built-in pets using the app's own drawing code.

One row per animation (idle, walk, sit, sleep, happy, eat, dangle, fall,
sideeye), then the peek poses (resting and popped out, from the left and right
edges), then, for pets with accessories, the idle frames without them.

Usage: uv run python scripts/cast_sheets.py [pet ...] [--out DIR] [--scale N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from preview_pet import write_png

from nibble.core.peek import clip, layout, orient
from nibble.core.spec import ANIMATIONS, STANDING, PetSpec, load_builtin
from nibble.core.sprites import GRID, TRANSPARENT, parse_hex

GAP = 3
BG = (34, 30, 58)  # dark, so white outfits and outlines both show
CHECK = (42, 37, 70)


def peek_frames(pet: PetSpec, worn: frozenset[str]) -> list[tuple]:
    standing = [f for n in STANDING for f in pet.frames[n]]
    out = []
    for side in (-1, 1):
        lay = layout(standing, side, upright=False, look=1, scale=1)
        rest = round(lay.ref.width * 0.6)
        for anim, depth in (("idle", rest), ("happy", lay.ref.width)):
            frame, _ = clip(orient(pet.frame(anim, 0, worn), side, False, 1), side, lay.ref, depth)
            out.append(frame)
    return out


def sheet_rows(pet: PetSpec) -> list[list[tuple]]:
    worn = pet.default_worn
    rows = [[pet.frame(anim, i, worn) for i in range(count)] for anim, count in ANIMATIONS.items()]
    rows.append(peek_frames(pet, worn))
    if pet.accessories:
        rows.append([pet.frame("idle", i) for i in range(ANIMATIONS["idle"])] + [pet.frame("happy", 0), pet.frame("sleep", 0)])
    return rows


def render(rows: list[list[tuple]], palette: dict[str, str], scale: int):
    colors = {k: parse_hex(v) for k, v in palette.items()}
    cols = max(len(r) for r in rows)
    w = (cols * (GRID + GAP) + GAP) * scale
    h = (len(rows) * (GRID + GAP) + GAP) * scale
    img = [[BG] * w for _ in range(h)]
    for r, frames in enumerate(rows):
        for c, frame in enumerate(frames):
            ox, oy = (GAP + c * (GRID + GAP)) * scale, (GAP + r * (GRID + GAP)) * scale
            for y, line in enumerate(frame):
                for x, ch in enumerate(line):
                    color = colors[ch] if ch != TRANSPARENT else (CHECK if (x // 4 + y // 4) % 2 else BG)
                    for sy in range(scale):
                        row = img[oy + y * scale + sy]
                        for sx in range(scale):
                            row[ox + x * scale + sx] = color
    return w, h, img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pets", nargs="*", default=["pearl", "archie", "dewey", "kernel"])
    ap.add_argument("--out", default="docs/sprites")
    ap.add_argument("--scale", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for pid in args.pets:
        pet = load_builtin(pid)
        path = out / f"{pid}.png"
        write_png(path, *render(sheet_rows(pet), pet.palette, args.scale))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
