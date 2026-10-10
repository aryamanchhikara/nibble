"""A frozen picture of the desktop, and where a pet belongs in it.

Where can the pet be? One rule, applied to the focused window:
- if there's room above its top edge, stand on that edge;
- otherwise (Split View, tiled, maximized, fullscreen) peek in from the
  window's outer side: the side touching the screen edge, never the divider
  between two windows. A window touching both sides (maximized, fullscreen)
  offers both; one touching neither offers the side nearest a screen edge.
The screen floor is only ever a place it lands, or where you put it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace

from .geometry import (
    Display,
    Rect,
    SurfaceKey,
    SurfaceMap,
    WindowInfo,
    display_for_rect,
    pick_active_window,
    window_key,
)

_versions = itertools.count(1)

# A window side within this many points of the screen edge counts as touching
# it, which covers macOS tiling margins and Split View.
TOUCHING = 32.0
# Peek somewhere in the middle of the window's height: away from title bars,
# tabs and toolbars at the top and status bars or the Dock at the bottom.
PEEK_BAND = (0.25, 0.75)


@dataclass(frozen=True)
class Snapshot:
    displays: tuple[Display, ...]
    windows: tuple[WindowInfo, ...]  # on screen, front-to-back
    own_pid: int
    frontmost_pid: int | None
    frontmost_name: str | None = None
    frontmost_bundle: str | None = None
    version: int = field(default_factory=lambda: next(_versions))

    def with_window_bounds(self, window_id: int, bounds: Rect | None) -> Snapshot:
        """Patch one window from a fast single-window poll (None = it's gone)."""
        windows = []
        for w in self.windows:
            if w.id != window_id:
                windows.append(w)
            elif bounds is not None:
                windows.append(replace(w, bounds=bounds))
        return replace(self, windows=tuple(windows), version=next(_versions))


@dataclass(frozen=True)
class Edge:
    """A vertical line a pet can hide behind and peek in from.

    side +1: the pet hides to the right of x and pokes in leftward (a window's
    right side); side -1: hides to the left and pokes rightward.
    """

    side: int
    x: float
    y_lo: float  # range for the vertical centre of the pet
    y_hi: float
    display_id: int
    window_id: int | None  # None for a bare screen edge


@dataclass(frozen=True)
class Home:
    """Where a pet wants to be: on an edge it can stand on, or peeking."""

    stand: SurfaceKey | None = None
    peek: tuple[Edge, ...] = ()  # allowed edges, preferred first

    @property
    def ident(self) -> tuple:
        """Same ident = same place (peek spots on one window count as one place)."""
        if self.stand is not None:
            return ("stand", self.stand)
        e = self.peek[0]
        return ("peek", e.window_id if e.window_id is not None else ("screen", e.display_id))


def peek_edges(window: WindowInfo | None, display: Display) -> tuple[Edge, ...]:
    """The outer sides of a window (or of the bare screen) to peek in from."""
    v, f = display.visible, display.frame
    if window is None:
        lo, hi = v.bottom, v.top
        sides = [(-1, f.left), (1, f.right)]
        wid = None
    else:
        b = window.bounds
        lo, hi = max(b.bottom, v.bottom), min(b.top, v.top)
        gap_left, gap_right = b.left - v.left, v.right - b.right
        left = (-1, max(b.left, f.left))
        right = (1, min(b.right, f.right))
        if gap_left <= TOUCHING and gap_right <= TOUCHING:
            sides = [left, right]  # maximized or fullscreen: either side
        elif gap_left <= TOUCHING:
            sides = [left]
        elif gap_right <= TOUCHING:
            sides = [right]
        else:
            sides = [left if gap_left <= gap_right else right]
        wid = window.id
    if hi <= lo:
        lo, hi = v.bottom, v.top
    y_lo = lo + (hi - lo) * PEEK_BAND[0]
    y_hi = lo + (hi - lo) * PEEK_BAND[1]
    return tuple(Edge(side, x, y_lo, y_hi, display.id, wid) for side, x in sides)


class WorldView:
    """A snapshot seen by a pet of a particular size."""

    def __init__(self, snapshot: Snapshot, pet_w: float, pet_h: float):
        self.snapshot = snapshot
        self.surfaces = SurfaceMap(snapshot.displays, snapshot.windows, snapshot.own_pid, pet_w, pet_h)
        self.active: WindowInfo | None = pick_active_window(
            snapshot.windows, snapshot.frontmost_pid, snapshot.own_pid
        )

    @property
    def displays(self) -> tuple[Display, ...]:
        return self.snapshot.displays

    @property
    def active_id(self) -> int | None:
        return self.active.id if self.active else None

    @property
    def active_display(self) -> Display | None:
        return display_for_rect(self.active.bounds, self.displays) if self.active else None

    def home(self) -> Home | None:
        """Where the pet belongs given the focused window (None: nothing focused)."""
        if self.active is None:
            return None
        key = window_key(self.active.id)
        if self.surfaces.standable(key):
            return Home(stand=key)
        d = self.active_display
        return Home(peek=peek_edges(self.active, d)) if d else None

    def screen_home(self, display: Display) -> Home:
        """Peeking from the bare screen edges, for when nothing is focused."""
        return Home(peek=peek_edges(None, display))
