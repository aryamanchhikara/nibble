"""How a pet's body moves: standing (and riding along), hopping, falling,
held, and peeking in from the side of the screen.

Positions are the pet's feet: x is the horizontal centre, y the bottom, in
Cocoa global coordinates. While standing, the pet stores its offset from the
surface's left edge, so when a window moves the pet moves with it. While
peeking, x is the tip of whatever pokes in and y its vertical centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .geometry import SurfaceKey, SurfaceMap

GRAVITY = 2600.0  # pt/s²
TERMINAL_VELOCITY = 2400.0
AIR_DRAG = 1.2  # fraction of horizontal speed lost per second
WALL_BOUNCE = 0.45
MAX_THROW = 2500.0

LANDED = "landed"
LOST_SUPPORT = "lost_support"
COVERED = "covered"
ARRIVED = "arrived"


def _hop_time(dist: float) -> float:
    return min(0.9, max(0.3, 0.3 + dist / 2000))


class Mode(Enum):
    STANDING = "standing"
    HOPPING = "hopping"
    FALLING = "falling"
    HELD = "held"
    PEEKING = "peeking"


@dataclass
class Peek:
    """Poking in from a screen edge. side is +1 for the right edge, -1 for the left."""

    display_id: int
    side: int
    edge_x: float
    y: float  # vertical centre of the pet
    depth: float = 0.0  # points showing on screen
    target: float = 0.0
    speed: float = 120.0  # points per second toward target
    upright: bool = False  # sliding in/out standing up, before/after lying sideways
    look: int = 1  # lying sideways: +1 faces up the screen, -1 down
    window_id: int | None = None  # the window it's peeking around (None: bare screen edge)

    @property
    def settled(self) -> bool:
        return abs(self.depth - self.target) < 0.5


@dataclass
class Hop:
    target: SurfaceKey | None  # None: hop to a fixed point, then start peeking
    target_rel_x: float
    start_x: float
    start_y: float
    duration: float
    height: float
    t: float = 0.0
    point_y: float = 0.0
    then_peek: Peek | None = None


@dataclass
class Body:
    pet_w: float
    pet_h: float
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    mode: Mode = Mode.FALLING
    support: SurfaceKey | None = None
    rel_x: float = 0.0
    facing: int = 1
    walk_target: float | None = None  # offset from the support's anchor
    walk_speed: float = 48.0
    distance_walked: float = 0.0
    hop: Hop | None = None
    peek: Peek | None = None
    last_impact: float = 0.0
    events: list[str] = field(default_factory=list)

    @property
    def edge_inset(self) -> float:
        """How close the pet's centre may get to the end of a ledge."""
        return self.pet_w * 0.3

    @property
    def grounded(self) -> bool:
        return self.mode is Mode.STANDING

    # ---- commands -------------------------------------------------------

    def drop_in(self, x: float, y: float) -> None:
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self._start_falling()

    def walk_to(self, x: float, surfaces: SurfaceMap, speed: float | None = None) -> None:
        if self.mode is not Mode.STANDING or self.support is None:
            return
        anchor = surfaces.anchor_x(self.support)
        if anchor is None:
            return
        self.walk_target = x - anchor
        if speed is not None:
            self.walk_speed = speed

    def stop_walking(self) -> None:
        self.walk_target = None

    def hop_to(self, key: SurfaceKey, x: float, surfaces: SurfaceMap, pace: float = 1.0) -> bool:
        """Hop onto a surface. pace > 1 makes it a slower, calmer hop."""
        ty = surfaces.y(key)
        anchor = surfaces.anchor_x(key)
        if ty is None or anchor is None:
            return False
        dist = math.hypot(x - self.x, ty - self.y)
        rise = ty - self.y
        self.hop = Hop(
            target=key,
            target_rel_x=x - anchor,
            start_x=self.x,
            start_y=self.y,
            duration=_hop_time(dist) * pace,
            height=self._hop_height(dist, rise),
        )
        self.mode = Mode.HOPPING
        self.support = None
        self.walk_target = None
        if abs(x - self.x) > 1:
            self.facing = 1 if x > self.x else -1
        return True

    def hop_to_point(self, x: float, y: float, then_peek: Peek, pace: float = 1.0) -> None:
        """Hop to a spot that isn't a surface (a window's side) and start peeking there."""
        dist = math.hypot(x - self.x, y - self.y)
        self.hop = Hop(
            target=None,
            target_rel_x=x,
            start_x=self.x,
            start_y=self.y,
            duration=_hop_time(dist) * pace,
            height=self._hop_height(dist, y - self.y),
            point_y=y,
            then_peek=then_peek,
        )
        self.mode = Mode.HOPPING
        self.support = None
        self.walk_target = None
        if abs(x - self.x) > 1:
            self.facing = 1 if x > self.x else -1

    def _hop_height(self, dist: float, rise: float) -> float:
        # A little hop scales with the pet; it also has to clear targets above us.
        return max(self.pet_h * 0.55, 0.25 * dist, rise / 4 + self.pet_h * 0.4)

    def start_peeking(self, peek: Peek) -> None:
        self.mode = Mode.PEEKING
        self.peek = peek
        self.support = None
        self.hop = None
        self.walk_target = None
        self.vx = self.vy = 0.0
        self._place_peek()

    def stop_peeking(self) -> None:
        """Stand the pet up at the edge (fully on screen) so it can hop somewhere."""
        p = self.peek
        if p is not None:
            self.x = p.edge_x - p.side * self.pet_w / 2
            self.y = p.y - self.pet_h / 2
            self.facing = -p.side
        self.peek = None
        self._start_falling()

    def grab(self) -> None:
        self.mode = Mode.HELD
        self.support = None
        self.hop = None
        self.peek = None
        self.walk_target = None
        self.vx = self.vy = 0.0

    def hold_at(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def release(self, vx: float = 0.0, vy: float = 0.0) -> None:
        speed = math.hypot(vx, vy)
        if speed > MAX_THROW:
            vx, vy = vx * MAX_THROW / speed, vy * MAX_THROW / speed
        self.vx, self.vy = vx, vy
        self._start_falling()

    # ---- simulation -----------------------------------------------------

    def step(self, dt: float, surfaces: SurfaceMap) -> list[str]:
        self.events = []
        if self.mode is Mode.STANDING:
            self._step_standing(dt, surfaces)
        elif self.mode is Mode.HOPPING:
            self._step_hopping(dt, surfaces)
        elif self.mode is Mode.FALLING:
            self._step_falling(dt, surfaces)
        elif self.mode is Mode.PEEKING:
            self._step_peeking(dt)
        return self.events

    def _start_falling(self) -> None:
        self.mode = Mode.FALLING
        self.support = None
        self.hop = None
        self.peek = None
        self.walk_target = None

    def _land(self, key: SurfaceKey, x: float, y: float, surfaces: SurfaceMap) -> None:
        self.last_impact = abs(self.vy)
        self.mode = Mode.STANDING
        self.support = key
        self.hop = None
        self.x, self.y = x, y
        self.rel_x = x - (surfaces.anchor_x(key) or 0.0)
        self.vx = self.vy = 0.0
        self.events.append(LANDED)

    def _step_standing(self, dt: float, surfaces: SurfaceMap) -> None:
        key = self.support
        y = surfaces.y(key) if key else None
        anchor = surfaces.anchor_x(key) if key else None
        if y is None or anchor is None:
            # The window closed (or minimized) under us.
            self._start_falling()
            self.vx = self.vy = 0.0
            self.events.append(LOST_SUPPORT)
            return
        seg = surfaces.segment_at(key, anchor + self.rel_x)
        if seg is None:
            # The window's still there but another one now covers its whole top
            # edge. Hold still; the brain will move us somewhere better.
            self.x, self.y = anchor + self.rel_x, y
            self.walk_target = None
            self.events.append(COVERED)
            return

        x = anchor + self.rel_x
        if seg.distance(x) > self.pet_w:
            # A window slid over the spot we were standing on: hop to what's left.
            self.hop_to(key, seg.clamp(x, self.edge_inset), surfaces)
            return
        x = seg.clamp(x, self.edge_inset)

        if self.walk_target is not None:
            target = seg.clamp(anchor + self.walk_target, self.edge_inset)
            dx = target - x
            stride = self.walk_speed * dt
            if abs(dx) <= stride:
                x = target
                self.walk_target = None
                self.events.append(ARRIVED)
            else:
                x += math.copysign(stride, dx)
                self.facing = 1 if dx > 0 else -1
            self.distance_walked += min(stride, abs(dx))

        self.rel_x = x - anchor
        self.x, self.y = x, y

    def _step_hopping(self, dt: float, surfaces: SurfaceMap) -> None:
        hop = self.hop
        assert hop is not None
        if hop.target is None:
            ty, anchor = hop.point_y, 0.0
        else:
            ty = surfaces.y(hop.target)
            anchor = surfaces.anchor_x(hop.target)
        if ty is None or anchor is None or (hop.target is not None and not surfaces.standable(hop.target)):
            # Destination vanished mid-air: keep our momentum and fall.
            self._start_falling()
            self._step_falling(dt, surfaces)
            return

        tx = anchor + hop.target_rel_x
        hop.t = min(1.0, hop.t + dt / hop.duration)
        p = hop.t
        nx = hop.start_x + (tx - hop.start_x) * p
        ny = hop.start_y + (ty - hop.start_y) * p + hop.height * 4 * p * (1 - p)
        if dt > 0:
            self.vx, self.vy = (nx - self.x) / dt, (ny - self.y) / dt
        self.x, self.y = nx, ny
        if p >= 1.0:
            if hop.target is None:
                assert hop.then_peek is not None
                self.start_peeking(hop.then_peek)
            else:
                self._land(hop.target, tx, ty, surfaces)

    def _step_peeking(self, dt: float) -> None:
        p = self.peek
        assert p is not None
        gap = p.target - p.depth
        step = p.speed * dt
        p.depth = p.target if abs(gap) <= step else p.depth + math.copysign(step, gap)
        self._place_peek()

    def _place_peek(self) -> None:
        p = self.peek
        if p is not None:
            self.x = p.edge_x - p.side * p.depth
            self.y = p.y

    def _step_falling(self, dt: float, surfaces: SurfaceMap) -> None:
        self.vy = max(self.vy - GRAVITY * dt, -TERMINAL_VELOCITY)
        self.vx *= max(0.0, 1.0 - AIR_DRAG * dt)
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt

        # Bounce off the outer edges of the desktop, not the seams between displays.
        if not surfaces.inside_any_display(nx, self.y) and surfaces.inside_any_display(self.x, self.y):
            nx = self.x
            self.vx = -self.vx * WALL_BOUNCE
            self.facing = 1 if self.vx > 0 else -1
        if self.vy > 0 and not surfaces.inside_any_display(nx, ny + self.pet_h) and surfaces.inside_any_display(nx, ny):
            ny = self.y
            self.vy = 0.0

        if self.vy <= 0:
            hit = surfaces.landing(nx, self.y, ny)
            if hit is not None:
                self._land(hit[0], nx, hit[1], surfaces)
                return
            if not surfaces.inside_any_display(nx, ny):
                # Fell through a gap between displays: put it on the nearest floor.
                rescue = surfaces.nearest_floor(nx, ny)
                if rescue is not None:
                    self._land(rescue[0], rescue[1], rescue[2], surfaces)
                    return

        self.x, self.y = nx, ny
