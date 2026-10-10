"""Palette-indexed pixel frames: decoding, mirroring, hit-testing, metrics.

A frame is GRID strings of GRID characters, top row first. "." is transparent;
every other character indexes the pet's palette. Frames are drawn facing right
and mirrored for walking left.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

GRID = 32
TRANSPARENT = "."

Frame = tuple[str, ...]


def parse_hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mirror(frame: Sequence[str]) -> Frame:
    return tuple(row[::-1] for row in frame)


def to_rgba(frame: Sequence[str], palette: Mapping[str, str]) -> bytes:
    """Premultiplied RGBA bytes, top row first (what CGImage expects)."""
    colors = {k: parse_hex(v) for k, v in palette.items()}
    out = bytearray(len(frame) * len(frame[0]) * 4)
    i = 0
    for row in frame:
        for ch in row:
            if ch != TRANSPARENT and ch in colors:
                r, g, b = colors[ch]
                out[i : i + 4] = bytes((r, g, b, 255))
            i += 4
    return bytes(out)


def overlay(frame: Sequence[str], sprite: Sequence[str], x: int, y: int) -> Frame:
    """Paste a sprite's opaque pixels onto a frame with its top-left at (x, y), clipped to the frame."""
    rows = [list(r) for r in frame]
    for dy, srow in enumerate(sprite):
        ry = y + dy
        if not 0 <= ry < len(rows):
            continue
        for dx, ch in enumerate(srow):
            rx = x + dx
            if ch != TRANSPARENT and 0 <= rx < len(rows[ry]):
                rows[ry][rx] = ch
    return tuple("".join(r) for r in rows)


def is_opaque(frame: Sequence[str], col: int, row: int) -> bool:
    if 0 <= row < len(frame) and 0 <= col < len(frame[row]):
        return frame[row][col] != TRANSPARENT
    return False


def hit_test(frame: Sequence[str], local_x: float, local_y: float, scale: float) -> bool:
    """Is the point (view coordinates, origin bottom-left) on an opaque pixel?"""
    if local_x < 0 or local_y < 0:
        return False
    col = int(local_x // scale)
    row = len(frame) - 1 - int(local_y // scale)
    return is_opaque(frame, col, row)


def bottom_row(frame: Sequence[str]) -> int | None:
    for r in range(len(frame) - 1, -1, -1):
        if frame[r].strip(TRANSPARENT):
            return r
    return None


def top_row(frame: Sequence[str]) -> int | None:
    for r, row in enumerate(frame):
        if row.strip(TRANSPARENT):
            return r
    return None


def shift_down(frame: Sequence[str], rows: int) -> Frame:
    """Move a frame's pixels down by rows (up if negative), never cropping any."""
    if rows > 0:
        bottom = bottom_row(frame)
        rows = min(rows, len(frame) - 1 - bottom) if bottom is not None else 0
    elif rows < 0:
        top = top_row(frame)
        rows = -min(-rows, top) if top is not None else 0
    if rows == 0:
        return tuple(frame)
    empty = TRANSPARENT * len(frame[0])
    if rows > 0:
        return tuple([empty] * rows + list(frame[: len(frame) - rows]))
    return tuple(list(frame[-rows:]) + [empty] * -rows)


@dataclass(frozen=True)
class BBox:
    left: int
    top: int
    right: int  # inclusive
    bottom: int  # inclusive

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


def bbox(frames: Iterable[Sequence[str]]) -> BBox | None:
    """Bounding box of the opaque pixels across one or more frames."""
    left = top = 10**9
    right = bottom = -1
    for frame in frames:
        for r, row in enumerate(frame):
            for c, ch in enumerate(row):
                if ch != TRANSPARENT:
                    left, right = min(left, c), max(right, c)
                    top, bottom = min(top, r), max(bottom, r)
    if right < 0:
        return None
    return BBox(left, top, right, bottom)


@dataclass(frozen=True)
class SpriteMetrics:
    """How a pet's frames sit inside its square window, in grid pixels."""

    feet_row: int  # lowest opaque row while standing
    body: BBox  # opaque area while standing

    def size(self, scale: float) -> tuple[float, float]:
        """Width and height of the visible pet, in points."""
        return self.body.width * scale, self.body.height * scale

    def baseline(self, scale: float) -> float:
        """Points between the bottom of the window and the pet's feet."""
        return (GRID - 1 - self.feet_row) * scale


def metrics(standing_frames: Sequence[Sequence[str]]) -> SpriteMetrics:
    box = bbox(standing_frames)
    if box is None:
        raise ValueError("pet has no visible pixels")
    return SpriteMetrics(feet_row=box.bottom, body=box)
