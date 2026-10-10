"""A small software pixel canvas for the 16-bit home page.

Everything on the home page is drawn here at its true low resolution, then
shown scaled up by a whole number with nearest-neighbour filtering, so it's
pixel-perfect on every display (and a screenshot is exactly what's on screen).
No alpha blending, as on real 16-bit hardware: soft edges and gradients are
ordered (Bayer) dithering between palette colours.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

RGB = tuple[int, int, int]

# 4×4 Bayer matrix, thresholds 0..15.
BAYER = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def hex_rgb(color: str) -> RGB:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@dataclass(frozen=True)
class Mask:
    """A 1-bit image (e.g. rendered text). bits is row-major, True = ink."""

    w: int
    h: int
    bits: tuple[bool, ...]

    def at(self, x: int, y: int) -> bool:
        return self.bits[y * self.w + x]


class Canvas:
    def __init__(self, w: int, h: int, fill: RGB = (0, 0, 0)):
        self.w, self.h = w, h
        self.px = bytearray(bytes((*fill, 255)) * (w * h))

    def copy(self) -> Canvas:
        other = Canvas.__new__(Canvas)
        other.w, other.h, other.px = self.w, self.h, bytearray(self.px)
        return other

    def restore(self, other: Canvas) -> None:
        """Overwrite this canvas with another of the same size (fast)."""
        self.px[:] = other.px

    # ---- pixels -------------------------------------------------------

    def set(self, x: int, y: int, c: RGB) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i : i + 3] = bytes(c)

    def get(self, x: int, y: int) -> RGB:
        i = (y * self.w + x) * 4
        return self.px[i], self.px[i + 1], self.px[i + 2]

    def rect(self, x: int, y: int, w: int, h: int, c: RGB) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes((*c, 255)) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 4
            self.px[i : i + len(row)] = row

    def frame(self, x: int, y: int, w: int, h: int, c: RGB, thickness: int = 1) -> None:
        """A rectangle outline."""
        for t in range(thickness):
            self.rect(x + t, y + t, w - 2 * t, 1, c)
            self.rect(x + t, y + h - 1 - t, w - 2 * t, 1, c)
            self.rect(x + t, y + t, 1, h - 2 * t, c)
            self.rect(x + w - 1 - t, y + t, 1, h - 2 * t, c)

    def dither(self, x: int, y: int, w: int, h: int, a: RGB, b: RGB, level: float) -> None:
        """Mix two colours with ordered dithering: level 0 = all a, 1 = all b."""
        threshold = level * 16
        for yy in range(max(0, y), min(self.h, y + h)):
            row = BAYER[yy % 4]
            for xx in range(max(0, x), min(self.w, x + w)):
                self.set(xx, yy, b if row[xx % 4] < threshold else a)

    def vgradient(self, x: int, y: int, w: int, h: int, stops: Sequence[RGB]) -> None:
        """Top-to-bottom gradient through palette stops, dithered between neighbours."""
        bands = len(stops) - 1
        for yy in range(h):
            pos = yy / max(1, h - 1) * bands
            i = min(int(pos), bands - 1)
            self.dither(x, y + yy, w, 1, stops[i], stops[i + 1], pos - i)

    def glow(self, cx: int, cy: int, rx: int, ry: int, base_of, light: RGB, strength: float = 1.0) -> None:
        """A dithered pool of light: denser toward the centre. base_of(x, y) gives the colour underneath."""
        for yy in range(cy - ry, cy + ry + 1):
            for xx in range(cx - rx, cx + rx + 1):
                d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
                if d > 1 or not (0 <= xx < self.w and 0 <= yy < self.h):
                    continue
                level = (1 - d) * strength
                if BAYER[yy % 4][xx % 4] < level * 16:
                    self.set(xx, yy, light)

    # ---- images -------------------------------------------------------

    def sprite(self, rows: Sequence[str], palette: Mapping[str, RGB], x: int, y: int) -> None:
        """Draw a palette-indexed frame; "." is transparent."""
        for dy, row in enumerate(rows):
            yy = y + dy
            if not 0 <= yy < self.h:
                continue
            for dx, ch in enumerate(row):
                if ch != "." and ch in palette:
                    self.set(x + dx, yy, palette[ch])

    def mask(self, m: Mask, x: int, y: int, c: RGB, shadow: RGB | None = None) -> None:
        """Draw a 1-bit mask (text), optionally with a 1px drop shadow."""
        if shadow is not None:
            self.mask(m, x + 1, y + 1, shadow)
        for yy in range(m.h):
            base = yy * m.w
            for xx in range(m.w):
                if m.bits[base + xx]:
                    self.set(x + xx, y + yy, c)

    # ---- output -------------------------------------------------------

    def rgba(self) -> bytes:
        return bytes(self.px)

    def save_png(self, path: Path | str, scale: int = 1) -> None:
        raw = bytearray()
        for y in range(self.h):
            line = bytearray()
            base = y * self.w * 4
            for x in range(self.w):
                i = base + x * 4
                line += bytes(self.px[i : i + 3]) * scale
            for _ in range(scale):
                raw += b"\x00" + line

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w * scale, self.h * scale, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
        Path(path).write_bytes(png)
