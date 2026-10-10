"""Where a speech bubble goes: above a standing pet, or beside a peeking one.

Bubbles are kept inside the display's usable area, with the tail still
pointing at the pet's head.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Rect

TAIL = 9.0  # length of the tail
GAP = 4.0  # between the tail tip and the pet
MARGIN = 6.0  # from the edges of the screen
TAIL_INSET = 14.0  # keep the tail away from the bubble's rounded corners


@dataclass(frozen=True)
class BubbleLayout:
    box: Rect  # the bubble itself, global Cocoa coordinates
    tip: tuple[float, float]  # where the tail points
    tail_side: str  # side of the box the tail comes out of: "bottom", "left" or "right"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi)) if lo <= hi else (lo + hi) / 2


def above(head_x: float, head_top: float, w: float, h: float, visible: Rect) -> BubbleLayout:
    """Centred over the pet's head, nudged sideways to stay on screen."""
    x = _clamp(head_x - w / 2, visible.left + MARGIN, visible.right - MARGIN - w)
    y = min(head_top + GAP + TAIL, visible.top - MARGIN - h)
    tip_x = _clamp(head_x, x + TAIL_INSET, x + w - TAIL_INSET)
    return BubbleLayout(Rect(x, y, w, h), (tip_x, y - TAIL), "bottom")


def beside(tip_x: float, center_y: float, side: int, w: float, h: float, visible: Rect) -> BubbleLayout:
    """Next to a head poking in from a screen edge (side +1 = right edge)."""
    if side > 0:
        x = tip_x - GAP - TAIL - w
    else:
        x = tip_x + GAP + TAIL
    x = _clamp(x, visible.left + MARGIN, visible.right - MARGIN - w)
    y = _clamp(center_y - h / 2, visible.bottom + MARGIN, visible.top - MARGIN - h)
    tip_y = _clamp(center_y, y + TAIL_INSET, y + h - TAIL_INSET)
    tip = (x + w + TAIL, tip_y) if side > 0 else (x - TAIL, tip_y)
    return BubbleLayout(Rect(x, y, w, h), tip, "right" if side > 0 else "left")
