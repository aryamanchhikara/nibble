"""Render a pet JSON as a PNG contact sheet (one row per animation).

Usage: uv run python scripts/preview_pet.py path/to/pet.json [out.png] [--scale 8]
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

from nibble.core.sprites import GRID, TRANSPARENT, parse_hex

GAP = 2  # grid pixels between frames
BG = (238, 236, 244)
CHECK = (226, 223, 236)


def write_png(path: Path, width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> None:
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in pixels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def render(pet: dict, scale: int) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    palette = {k: parse_hex(v) for k, v in pet["palette"].items()}
    anims = list(pet["frames"].items())
    cols = max(len(f) for _, f in anims)
    w = (cols * (GRID + GAP) + GAP) * scale
    h = (len(anims) * (GRID + GAP) + GAP) * scale
    img = [[BG] * w for _ in range(h)]
    for r, (_, frames) in enumerate(anims):
        for c, frame in enumerate(frames):
            ox = (GAP + c * (GRID + GAP)) * scale
            oy = (GAP + r * (GRID + GAP)) * scale
            for y, row in enumerate(frame):
                for x, ch in enumerate(row):
                    color = palette.get(ch) if ch != TRANSPARENT else None
                    if color is None:
                        color = CHECK if (x // 4 + y // 4) % 2 else BG
                    for sy in range(scale):
                        line = img[oy + y * scale + sy]
                        for sx in range(scale):
                            line[ox + x * scale + sx] = color
    return w, h, img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pet")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--scale", type=int, default=8)
    args = ap.parse_args()
    pet = json.loads(Path(args.pet).read_text())
    out = Path(args.out or Path(args.pet).with_suffix(".png"))
    write_png(out, *render(pet, args.scale))
    print(f"wrote {out}  rows: {', '.join(pet['frames'])}")


if __name__ == "__main__":
    main()
