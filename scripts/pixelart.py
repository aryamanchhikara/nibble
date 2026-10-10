"""Tiny raster toolkit for drawing pets as palette-indexed 32×32 grids."""

from __future__ import annotations

from typing import Callable, Iterable

N = 32
EMPTY = "."


class Grid:
    def __init__(self, size: int = N):
        self.n = size
        self.g = [[EMPTY] * size for _ in range(size)]

    def copy(self) -> Grid:
        other = Grid(self.n)
        other.g = [row[:] for row in self.g]
        return other

    def get(self, x: int, y: int) -> str:
        return self.g[y][x] if 0 <= x < self.n and 0 <= y < self.n else EMPTY

    def put(self, x: int, y: int, c: str) -> None:
        if 0 <= x < self.n and 0 <= y < self.n:
            self.g[y][x] = c

    def put_all(self, pts: Iterable[tuple[int, int]], c: str) -> None:
        for x, y in pts:
            self.put(x, y, c)

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: str, only: set[str] | None = None) -> None:
        """Fill an inclusive rectangle."""
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                if only is None or self.get(x, y) in only:
                    self.put(x, y, c)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: str, only: set[str] | None = None) -> None:
        for y in range(self.n):
            for x in range(self.n):
                if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0:
                    if only is None or self.g[y][x] in only:
                        self.g[y][x] = c

    def poly(self, pts: list[tuple[float, float]], c: str, only: set[str] | None = None) -> None:
        """Fill a polygon (pixel centres inside, even-odd rule)."""
        for y in range(self.n):
            py = y + 0.5
            for x in range(self.n):
                px = x + 0.5
                inside = False
                j = len(pts) - 1
                for i in range(len(pts)):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
                if inside and (only is None or self.g[y][x] in only):
                    self.g[y][x] = c

    def where(self, pred: Callable[[int, int, str], bool], c: str) -> None:
        hits = [(x, y) for y in range(self.n) for x in range(self.n) if pred(x, y, self.g[y][x])]
        for x, y in hits:
            self.g[y][x] = c

    def rim(self, region: set[str], color: str, shade: str, dx: int = 1, dy: int = 1) -> None:
        """Shade pixels of color whose neighbour toward (dx, dy) is outside region."""
        hits = []
        for y in range(self.n):
            for x in range(self.n):
                if self.g[y][x] != color:
                    continue
                if (dx and self.get(x + dx, y) not in region) or (dy and self.get(x, y + dy) not in region):
                    hits.append((x, y))
        for x, y in hits:
            self.g[y][x] = shade

    def outline(self, c: str) -> None:
        src = [row[:] for row in self.g]
        for y in range(self.n):
            for x in range(self.n):
                if src[y][x] != EMPTY:
                    continue
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + ddx, y + ddy
                    if 0 <= nx < self.n and 0 <= ny < self.n and src[ny][nx] != EMPTY:
                        self.g[y][x] = c
                        break

    def shifted(self, dx: int, dy: int) -> Grid:
        other = Grid(self.n)
        for y in range(self.n):
            for x in range(self.n):
                if self.g[y][x] != EMPTY:
                    other.put(x + dx, y + dy, self.g[y][x])
        return other

    def rows(self) -> list[str]:
        return ["".join(r) for r in self.g]
