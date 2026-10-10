"""Draw Nibble.app's icon (a placeholder for v0.1) and write packaging/macos/Nibble.icns.

Pearl on a little night-rooftop tile in the home page's colours. It's drawn on
a 64×64 pixel grid and scaled up with no smoothing, like the rest of nibble;
only the two smallest sizes (16 and 32 px) are averaged down. Needs macOS
(iconutil).

Usage: uv run python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

from nibble.core.canvas import Canvas
from nibble.core.home_scene import C, SKY, palette_rgb
from nibble.core.spec import load_builtin
from nibble.core.sprites import TRANSPARENT

OUT = Path(__file__).resolve().parents[1] / "packaging" / "macos" / "Nibble.icns"

N = 64  # the icon's pixel grid: at 1024 px, each icon pixel is 16×16
TILE, INSET, RADIUS = 52, 6, 12  # a rounded square on Apple's icon grid (824 of 1024, centred)
FLOOR = INSET + TILE - 10  # the rooftop line Pearl stands on
STARS = ((15, 13), (46, 11), (51, 22), (12, 26), (31, 10), (40, 17))

PX = tuple[int, int, int, int]

# iconset file name -> size in pixels
SIZES = {
    "16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64,
    "128x128": 128, "128x128@2x": 256, "256x256": 256, "256x256@2x": 512,
    "512x512": 512, "512x512@2x": 1024,
}


def in_tile(x: int, y: int) -> bool:
    """The rounded square, judged at each pixel's centre (so the corners step like pixel art)."""
    lo, hi = INSET, INSET + TILE
    if not (lo <= x < hi and lo <= y < hi):
        return False
    cx = min(max(x + 0.5, lo + RADIUS), hi - RADIUS)
    cy = min(max(y + 0.5, lo + RADIUS), hi - RADIUS)
    return (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= RADIUS**2


def draw() -> Canvas:
    c = Canvas(N, N)
    c.vgradient(INSET, INSET, TILE, FLOOR - INSET, SKY)
    for x, y in STARS:
        c.set(x, y, C["text"])
    c.rect(INSET, FLOOR, TILE, INSET + TILE - FLOOR, C["card"])
    c.dither(INSET, FLOOR + 3, TILE, INSET + TILE - FLOOR - 3, C["card"], C["ink"], 0.5)
    c.rect(INSET, FLOOR, TILE, 1, C["card_edge"])

    pearl = load_builtin("pearl")
    frame = pearl.frame("idle", 0, pearl.default_worn)
    cols = [x for row in frame for x, ch in enumerate(row) if ch != TRANSPARENT]
    rows = [y for y, row in enumerate(frame) if row.strip(TRANSPARENT)]
    x = N // 2 - (min(cols) + max(cols) + 1) // 2
    y = FLOOR - max(rows)  # her lowest pixel sits on the rooftop line
    c.glow(N // 2, y + (min(rows) + max(rows)) // 2, 20, 18, None, C["spot"], strength=0.9)
    c.dither(x + min(cols) + 3, FLOOR + 1, max(cols) - min(cols) - 5, 2, C["card"], C["shadow"], 0.75)
    c.sprite(frame, palette_rgb(pearl), x, y)
    return c


def pixels(c: Canvas) -> list[PX]:
    return [(*c.get(x, y), 255 if in_tile(x, y) else 0) for y in range(N) for x in range(N)]


def resize(px: list[PX], size: int) -> list[PX]:
    if size >= N:  # whole-number nearest-neighbour scaling
        k = size // N
        return [px[(y // k) * N + x // k] for y in range(size) for x in range(size)]
    k = N // size  # average k×k blocks, weighting colour by alpha so the edges don't go dark
    out = []
    for y in range(size):
        for x in range(size):
            block = [px[(y * k + j) * N + x * k + i] for j in range(k) for i in range(k)]
            a = sum(p[3] for p in block)
            rgb = tuple(round(sum(p[ch] * p[3] for p in block) / a) if a else 0 for ch in range(3))
            out.append((*rgb, round(a / len(block))))
    return out


def write_png(path: Path, size: int, px: list[PX]) -> None:
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in px[y * size:(y + 1) * size]) for y in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))  # 8-bit RGBA
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> None:
    px = pixels(draw())
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Nibble.iconset"
        iconset.mkdir()
        for name, size in SIZES.items():
            write_png(iconset / f"icon_{name}.png", size, resize(px, size))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT)], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
