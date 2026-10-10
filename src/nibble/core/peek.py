"""Peeking in from the side of a window that has no room above it.

Split View, tiled, maximized and fullscreen windows leave nowhere to stand,
so the pet hides just past the window's outer side (see world.peek_edges)
and pokes its head in, lying sideways with its head pointing into the window.
It reuses the idle, happy and walk frames, rotated and clipped, so every pet
can do it without new art.

Life at the edge:
- resting with a little showing; every so often it slides further in, looks
  around (turning its head) and maybe says something, then settles back;
- hover the cursor in front of its face and it pops all the way in; it
  retreats once the cursor leaves (or after a few seconds, so it never camps);
- press the mouse near it (say, on a scrollbar) and it ducks out of the way;
- if the window moves it rides along; if focus moves to a window whose outer
  side is elsewhere (the other half of a split), it ducks out and reappears there.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

from .context import Context
from .physics import Body, Mode, Peek
from .size import scale_fields
from .sprites import GRID, TRANSPARENT, BBox, Frame, bbox, mirror
from .world import Edge

# ---- frames ---------------------------------------------------------------


def rotate_cw(frame: Sequence[str]) -> Frame:
    """Rotate a square frame 90° clockwise (its top ends up on the right)."""
    n = len(frame)
    return tuple("".join(frame[n - 1 - c][r] for c in range(n)) for r in range(n))


def rotate_ccw(frame: Sequence[str]) -> Frame:
    """Rotate a square frame 90° counter-clockwise (its top ends up on the left)."""
    n = len(frame)
    return tuple("".join(frame[c][n - 1 - r] for c in range(n)) for r in range(n))


def orient(frame: Sequence[str], side: int, upright: bool, look: int) -> Frame:
    """A right-facing frame turned to poke in from an edge on the given side.

    Upright, it simply faces inward. Lying sideways, the top of its head points
    inward and look picks whether its face turns up (+1) or down (-1).
    """
    if upright:
        return mirror(frame) if side > 0 else tuple(frame)
    if side > 0:  # hiding on the right: head points left
        return rotate_ccw(frame if look > 0 else mirror(frame))
    return rotate_cw(mirror(frame) if look > 0 else frame)


def clip(frame: Sequence[str], side: int, ref: BBox, depth_px: int) -> tuple[Frame, int]:
    """Keep only the depth_px columns that poke out from behind the edge.

    Returns the clipped frame and the grid column boundary that sits exactly
    on the edge (everything past it is transparent).
    """
    depth_px = max(0, min(depth_px, ref.width))
    if side > 0:
        lo, hi = ref.left, ref.left + depth_px - 1
        anchor = ref.left + depth_px
    else:
        lo, hi = ref.right - depth_px + 1, ref.right
        anchor = ref.right - depth_px + 1
    rows = tuple(
        "".join(ch if lo <= c <= hi else TRANSPARENT for c, ch in enumerate(row)) for row in frame
    )
    return rows, anchor


@dataclass(frozen=True)
class PeekLayout:
    """Where to put the pet's window so the right slice shows at the edge."""

    ref: BBox  # bounding box of the oriented standing frames
    scale: float

    @property
    def full(self) -> float:
        """Points showing when it's all the way in."""
        return self.ref.width * self.scale

    def depth_px(self, depth: float) -> int:
        return max(0, min(self.ref.width, round(depth / self.scale)))

    def origin(self, peek: Peek, anchor: int) -> tuple[float, float]:
        center_row = (self.ref.top + self.ref.bottom + 1) / 2
        return (peek.edge_x - anchor * self.scale, peek.y - (GRID - center_row) * self.scale)


def layout(standing: Sequence[Sequence[str]], side: int, upright: bool, look: int, scale: float) -> PeekLayout:
    ref = bbox(orient(f, side, upright, look) for f in standing)
    assert ref is not None
    return PeekLayout(ref, scale)


# ---- behaviour ------------------------------------------------------------


@dataclass(frozen=True)
class PeekTuning:
    rest: float = 0.6  # fraction of the pet showing while it waits (enough for the eyes)
    look: float = 0.8  # ...while it slides in to look around
    slide_speed: float = 80.0  # pt/s
    pop_speed: float = 380.0
    look_every: tuple[float, float] = (45.0, 100.0)
    look_for: tuple[float, float] = (2.5, 4.5)
    turn_every: float = 1.1  # head turns while looking around
    quip_chance: float = 0.2
    move_chance: float = 0.15  # after looking around, sometimes reappear elsewhere
    cheer_for: float = 3.5
    pop_hover: float = 0.7  # cursor must linger in front of its face this long
    pop_radius: float = 120.0
    leave_radius: float = 190.0
    pop_max: float = 6.0  # never camp in view longer than this
    pop_cooldown: float = 3.0
    edge_strip: float = 24.0  # cursor this close to the edge is after a scrollbar, not us
    duck_radius: float = 170.0
    duck_for: float = 2.0
    left_bias: float = 0.6  # when both sides work, prefer the left: scrollbars live on the right

    def for_size(self, factor: float) -> PeekTuning:
        """Speeds and cursor distances for a pet this much smaller or bigger than Large.

        edge_strip stays put: it's about where scrollbars are, not the pet.
        """
        return scale_fields(self, ("slide_speed", "pop_speed", "pop_radius", "leave_radius", "duck_radius"), factor)


REST, ENTER, LOOK, POP, DUCK, MOVE, CHEER, LEAVE = "rest", "enter", "look", "pop", "duck", "move", "cheer", "leave"

Say = Callable[[str, "str | None"], None]  # (kind, text); text None = pick a line of that kind


class PeekBrain:
    def __init__(self, rng: random.Random, tuning: PeekTuning | None = None):
        self.rng = rng
        self.tuning = tuning or PeekTuning()
        self.phase = REST
        self.until = 0.0
        self.next_look = 0.0
        self.next_turn = 0.0
        self.cooldown_until = 0.0
        self.duck_until = 0.0
        self.front_since: float | None = None
        self.pending_text: str | None = None
        self._next_edges: tuple[Edge, ...] = ()

    # ---- getting there and away -----------------------------------------

    def enter(self, now: float, body: Body, edges: Sequence[Edge], pace: float = 1.0) -> None:
        """Hop over to one of the edges, then slide out of sight and peek back in."""
        edge, y = self._spot(edges)
        peek = Peek(
            display_id=edge.display_id,
            side=edge.side,
            edge_x=edge.x,
            y=y,
            depth=body.pet_w,
            target=0.0,
            speed=self.tuning.slide_speed * 3,
            upright=True,
            window_id=edge.window_id,
        )
        body.hop_to_point(edge.x - edge.side * body.pet_w / 2, y - body.pet_h / 2, peek, pace)
        self.phase = ENTER
        self._next_edges = tuple(edges)
        self.next_look = now + self.rng.uniform(*self.tuning.look_every)

    def relocate(self, edges: Sequence[Edge], body: Body) -> None:
        """Duck out of sight, then reappear at one of these edges."""
        self._next_edges = tuple(edges)
        if body.peek is not None:
            self._go(MOVE, body.peek, 0.0, self.tuning.pop_speed)

    def leave(self, body: Body) -> bool:
        """Slide out, stand up, slide back in. True once ready to hop elsewhere."""
        p = body.peek
        if p is None:
            return True
        self.phase = LEAVE
        if not p.upright:
            p.target, p.speed = 0.0, self.tuning.pop_speed
            if p.settled:
                p.upright, p.depth = True, 0.0
                p.target, p.speed = body.pet_w, self.tuning.slide_speed * 3
            return False
        p.target = body.pet_w
        return p.settled

    def cheer(self, text: str) -> None:
        """Slide in and say something encouraging, as soon as it's not busy."""
        self.pending_text = text

    def _spot(self, edges: Sequence[Edge]) -> tuple[Edge, float]:
        edge = edges[0]
        left = [e for e in edges if e.side < 0]
        right = [e for e in edges if e.side > 0]
        if left and right:
            edge = left[0] if self.rng.random() < self.tuning.left_bias else right[0]
        return edge, self.rng.uniform(edge.y_lo, edge.y_hi)

    # ---- life at the edge ------------------------------------------------

    def update(self, now: float, body: Body, edges: Sequence[Edge] | None, ctx: Context, say: Say) -> None:
        """One tick of peeking. edges: where it may be now (None: stay put)."""
        p = body.peek
        if body.mode is not Mode.PEEKING or p is None:
            return
        if edges and self.phase not in (MOVE, LEAVE):
            match = next((e for e in edges if e.side == p.side and e.window_id == p.window_id), None)
            if match is None:
                self.relocate(edges, body)
            else:
                # Ride along with the window as it moves or resizes.
                p.edge_x, p.display_id = match.x, match.display_id
                p.y = min(max(p.y, match.y_lo), match.y_hi)
                self._next_edges = tuple(edges)
        self._step(now, body, p, ctx, say)

    def _go(self, phase: str, p: Peek, target: float, speed: float) -> None:
        self.phase = phase
        p.target, p.speed = target, speed

    def _step(self, now: float, body: Body, p: Peek, ctx: Context, say: Say) -> None:
        t = self.tuning
        length = body.pet_h
        rest = length * t.rest

        if self.phase == ENTER:
            if p.upright and p.settled:
                p.upright = False
                self._go(REST, p, rest, t.slide_speed)
            return
        if self.phase == MOVE:
            if p.settled and self._next_edges:
                edge, y = self._spot(self._next_edges)
                p.display_id, p.side, p.edge_x, p.y, p.window_id = edge.display_id, edge.side, edge.x, y, edge.window_id
                p.upright = False
                self._go(REST, p, rest, t.slide_speed)
            return
        if self.phase == LEAVE:
            return

        head_dist = math.hypot(ctx.cursor[0] - body.x, ctx.cursor[1] - body.y)

        # A press near us is probably aimed at a scrollbar: get out of the way.
        if ctx.mouse_down and not ctx.pressing_pet and head_dist < t.duck_radius:
            self._go(DUCK, p, 0.0, t.pop_speed)
            self.duck_until = now + t.duck_for
            return
        if self.phase == DUCK:
            if now >= self.duck_until and not ctx.mouse_down:
                self._go(REST, p, rest, t.slide_speed)
            return

        if self.pending_text is not None:
            say("cheer", self.pending_text)
            self.pending_text = None
            self._go(CHEER, p, length * t.look, t.slide_speed * 2)
            self.until = now + t.cheer_for
            return

        in_front = (
            (p.edge_x - ctx.cursor[0]) * p.side > t.edge_strip
            and head_dist < t.pop_radius
            and not ctx.mouse_down
            and not ctx.in_call
        )
        self.front_since = (self.front_since if self.front_since is not None else now) if in_front else None
        if (
            self.phase not in (POP, CHEER)
            and now >= self.cooldown_until
            and self.front_since is not None
            and now - self.front_since >= t.pop_hover
        ):
            self._go(POP, p, length, t.pop_speed)
            self.until = now + t.pop_max
            return

        if self.phase == POP:
            if head_dist > t.leave_radius or now >= self.until:
                self._go(REST, p, rest, t.slide_speed * 1.5)
                self.cooldown_until = now + t.pop_cooldown
            return

        if self.phase == CHEER:
            if now >= self.until:
                self._go(REST, p, rest, t.slide_speed)
            return

        if self.phase == LOOK:
            if now >= self.next_turn:
                p.look = -p.look
                self.next_turn = now + t.turn_every
            if now >= self.until:
                if self._next_edges and self.rng.random() < t.move_chance:
                    self._go(MOVE, p, 0.0, t.slide_speed * 1.5)
                else:
                    self._go(REST, p, rest, t.slide_speed)
                self.next_look = now + self.rng.uniform(*t.look_every)
            return

        # Resting.
        self.phase = REST
        if p.target != rest and p.settled:
            p.target = rest
        if now >= self.next_look and not ctx.in_call:
            self._go(LOOK, p, length * t.look, t.slide_speed)
            self.until = now + self.rng.uniform(*t.look_for)
            self.next_turn = now + t.turn_every
            if ctx.can_speak and self.rng.random() < t.quip_chance:
                say("quip", None)

    def pose(self, now: float, body: Body, blink: bool) -> tuple[str, int]:
        p = body.peek
        if p is not None and p.upright:
            return ("walk", int(now * 8))
        if self.phase in (POP, CHEER):
            return ("happy", int(now * 4))
        return ("idle", 1 if blink else 0)
