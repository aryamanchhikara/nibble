"""Screen geometry: coordinate flipping, displays, and where a pet can stand.

AppKit (Cocoa) global coordinates put the origin at the bottom-left of the
primary display, y growing up. Quartz window bounds from
CGWindowListCopyWindowInfo put it at the primary display's *top*-left, y
growing down. Both systems are anchored to the primary display, so a single
flip using the primary display's height converts every display.

Everything in here works in Cocoa coordinates and is free of AppKit imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# Windows at or above the Dock level are system chrome (Dock, menu bar, menu
# extras, notifications). They never host a pet and never hide an edge.
DOCK_LAYER = 20

IGNORED_OWNERS = frozenset(
    {
        "Window Server",
        "Dock",
        "Control Center",
        "Notification Center",
        "SystemUIServer",
        "Spotlight",
        "WindowManager",
        "Screenshot",
        "screencaptureui",
        "loginwindow",
    }
)

MIN_WINDOW_W = 120
MIN_WINDOW_H = 60


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y

    @property
    def top(self) -> float:
        return self.y + self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def contains(self, px: float, py: float) -> bool:
        return self.left <= px <= self.right and self.bottom <= py <= self.top

    def overlap_area(self, other: Rect) -> float:
        w = min(self.right, other.right) - max(self.left, other.left)
        h = min(self.top, other.top) - max(self.bottom, other.bottom)
        return w * h if w > 0 and h > 0 else 0.0

    def approx_equal(self, other: Rect, tol: float = 2.0) -> bool:
        return (
            abs(self.x - other.x) <= tol
            and abs(self.y - other.y) <= tol
            and abs(self.w - other.w) <= tol
            and abs(self.h - other.h) <= tol
        )


def flip_rect(rect: Rect, primary_height: float) -> Rect:
    """Convert between Quartz (top-left origin) and Cocoa (bottom-left origin).

    The flip is its own inverse, so this converts in either direction.
    """
    return Rect(rect.x, primary_height - rect.y - rect.h, rect.w, rect.h)


@dataclass(frozen=True, slots=True)
class Display:
    id: int
    frame: Rect
    visible: Rect  # excludes the menu bar and Dock
    backing: float = 2.0  # device pixels per point (2 on Retina, 1 otherwise)


@dataclass(frozen=True, slots=True)
class WindowInfo:
    id: int
    pid: int
    owner: str
    layer: int
    bounds: Rect  # Cocoa coordinates
    alpha: float = 1.0


# A pet stands on a window's top edge or on a display's floor.
SurfaceKey = tuple[str, int]


def window_key(window_id: int) -> SurfaceKey:
    return ("window", window_id)


def floor_key(display_id: int) -> SurfaceKey:
    return ("floor", display_id)


@dataclass(frozen=True, slots=True)
class Segment:
    x0: float
    x1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def contains(self, x: float) -> bool:
        return self.x0 <= x <= self.x1

    def clamp(self, x: float, inset: float = 0.0) -> float:
        inset = min(inset, self.width / 2)
        return min(max(x, self.x0 + inset), self.x1 - inset)

    def distance(self, x: float) -> float:
        if x < self.x0:
            return self.x0 - x
        if x > self.x1:
            return x - self.x1
        return 0.0


def merge_intervals(spans: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def subtract_intervals(
    spans: Iterable[tuple[float, float]], cuts: Iterable[tuple[float, float]]
) -> list[tuple[float, float]]:
    result = merge_intervals(spans)
    for c0, c1 in cuts:
        nxt: list[tuple[float, float]] = []
        for a, b in result:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        result = nxt
    return result


def is_regular_window(w: WindowInfo, own_pid: int) -> bool:
    """A normal app window that could be focused and stood on."""
    return (
        w.layer == 0
        and w.pid != own_pid
        and w.alpha > 0.05
        and w.bounds.w >= MIN_WINDOW_W
        and w.bounds.h >= MIN_WINDOW_H
        and w.owner not in IGNORED_OWNERS
    )


def is_occluder(w: WindowInfo, own_pid: int) -> bool:
    """A window that can hide part of another window's top edge."""
    return 0 <= w.layer < DOCK_LAYER and w.pid != own_pid and w.alpha > 0.05 and w.owner not in IGNORED_OWNERS


def pick_active_window(
    windows: Sequence[WindowInfo], frontmost_pid: int | None, own_pid: int
) -> WindowInfo | None:
    """The frontmost regular window of the frontmost app (windows are front-to-back)."""
    if frontmost_pid is None:
        return None
    for w in windows:
        if w.pid == frontmost_pid and is_regular_window(w, own_pid):
            return w
    return None


def display_for_rect(rect: Rect, displays: Sequence[Display]) -> Display | None:
    if not displays:
        return None
    best = max(displays, key=lambda d: d.frame.overlap_area(rect))
    if best.frame.overlap_area(rect) > 0:
        return best
    cx, cy = rect.center
    return display_for_point(cx, cy, displays)


def display_for_point(x: float, y: float, displays: Sequence[Display]) -> Display | None:
    if not displays:
        return None
    for d in displays:
        if d.frame.contains(x, y):
            return d

    def dist(d: Display) -> float:
        dx = max(d.frame.left - x, 0, x - d.frame.right)
        dy = max(d.frame.bottom - y, 0, y - d.frame.top)
        return dx * dx + dy * dy

    return min(displays, key=dist)


def is_fullscreen(w: WindowInfo, displays: Sequence[Display], tol: float = 2.0) -> bool:
    return any(w.bounds.approx_equal(d.frame, tol) for d in displays)


def top_edge_segments(
    window: WindowInfo,
    in_front: Iterable[WindowInfo],
    displays: Sequence[Display],
    pet_w: float,
    pet_h: float,
    own_pid: int,
) -> list[Segment]:
    """The parts of a window's top edge a pet of the given size can stand on.

    The edge has to lie on a display with room for the pet above it (below the
    menu bar), and any part covered by a window in front of it is cut out.
    """
    y = window.bounds.top
    spans = [
        (max(window.bounds.left, d.frame.left), min(window.bounds.right, d.frame.right))
        for d in displays
        if d.frame.bottom <= y and y + pet_h <= d.visible.top
    ]
    cuts = [
        (o.bounds.left, o.bounds.right)
        for o in in_front
        if is_occluder(o, own_pid) and o.bounds.bottom < y < o.bounds.top
    ]
    min_width = pet_w * 0.6
    return [Segment(a, b) for a, b in subtract_intervals(spans, cuts) if b - a >= min_width]


def floor_segment(display: Display) -> Segment:
    return Segment(display.frame.left, display.frame.right)


class SurfaceMap:
    """Every surface a pet of one size can stand on, for one world snapshot.

    Window segments are computed lazily since most ticks only ask about the one
    window the pet is standing on.
    """

    def __init__(
        self,
        displays: Sequence[Display],
        windows: Sequence[WindowInfo],
        own_pid: int,
        pet_w: float,
        pet_h: float,
    ):
        self.displays = list(displays)
        self.windows = list(windows)  # front-to-back
        self.own_pid = own_pid
        self.pet_w = pet_w
        self.pet_h = pet_h
        self._index = {w.id: i for i, w in enumerate(self.windows)}
        self._displays = {d.id: d for d in self.displays}
        self._cache: dict[SurfaceKey, list[Segment]] = {}

    def window(self, window_id: int) -> WindowInfo | None:
        i = self._index.get(window_id)
        return self.windows[i] if i is not None else None

    def segments(self, key: SurfaceKey) -> list[Segment]:
        if key in self._cache:
            return self._cache[key]
        kind, ident = key
        segs: list[Segment] = []
        if kind == "floor":
            d = self._displays.get(ident)
            if d is not None:
                segs = [floor_segment(d)]
        else:
            i = self._index.get(ident)
            if i is not None and is_regular_window(self.windows[i], self.own_pid):
                segs = top_edge_segments(
                    self.windows[i], self.windows[:i], self.displays, self.pet_w, self.pet_h, self.own_pid
                )
        self._cache[key] = segs
        return segs

    def y(self, key: SurfaceKey) -> float | None:
        kind, ident = key
        if kind == "floor":
            d = self._displays.get(ident)
            return d.visible.bottom if d else None
        w = self.window(ident)
        return w.bounds.top if w else None

    def anchor_x(self, key: SurfaceKey) -> float | None:
        """The x a standing pet's offset is measured from, so it rides along."""
        kind, ident = key
        if kind == "floor":
            d = self._displays.get(ident)
            return d.frame.left if d else None
        w = self.window(ident)
        return w.bounds.left if w else None

    def standable(self, key: SurfaceKey) -> bool:
        return bool(self.segments(key))

    def nearest_point(self, key: SurfaceKey, x: float, inset: float = 0.0) -> float | None:
        segs = self.segments(key)
        if not segs:
            return None
        seg = min(segs, key=lambda s: s.distance(x))
        return seg.clamp(x, inset)

    def segment_at(self, key: SurfaceKey, x: float) -> Segment | None:
        segs = self.segments(key)
        if not segs:
            return None
        return min(segs, key=lambda s: s.distance(x))

    def all_keys(self) -> list[SurfaceKey]:
        keys = [window_key(w.id) for w in self.windows if is_regular_window(w, self.own_pid)]
        keys += [floor_key(d.id) for d in self.displays]
        return keys

    def landing(self, x: float, y_from: float, y_to: float) -> tuple[SurfaceKey, float] | None:
        """The highest surface a pet falling from y_from to y_to at x would hit."""
        best: tuple[SurfaceKey, float] | None = None
        for key in self.all_keys():
            y = self.y(key)
            if y is None or not (y_to <= y <= y_from):
                continue
            if best is not None and y <= best[1]:
                continue
            if any(s.contains(x) for s in self.segments(key)):
                best = (key, y)
        return best

    def nearest_floor(self, x: float, y: float) -> tuple[SurfaceKey, float, float] | None:
        """Closest floor point at or below y (any floor if none is below).

        Used to rescue a pet that fell past every surface, e.g. through a gap
        between displays of different sizes.
        """
        candidates = []
        for d in self.displays:
            fx = floor_segment(d).clamp(x, self.pet_w / 2)
            fy = d.visible.bottom
            candidates.append(((fx - x) ** 2 + (fy - y) ** 2, fy > y, floor_key(d.id), fx, fy))
        if not candidates:
            return None
        _, _, key, fx, fy = min(candidates, key=lambda c: (c[1], c[0]))
        return key, fx, fy

    def inside_any_display(self, x: float, y: float) -> bool:
        return any(d.frame.contains(x, y) for d in self.displays)
