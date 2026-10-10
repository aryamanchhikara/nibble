"""One pet on screen: wires its brain and body to its windows and the mouse."""

from __future__ import annotations

import logging
import math
import random
import time
from collections import deque
from dataclasses import replace

from ..core import bubble
from ..core.brain import Brain, Tuning
from ..core.context import Context
from ..core.geometry import Display, display_for_point
from ..core.lines import LinePicker
from ..core.peek import PeekLayout, PeekTuning, clip, layout, orient
from ..core.physics import Body, Mode
from ..core.size import crisp_scale, size_factor
from ..core.spec import STANDING, PetSpec
from ..core.sprites import GRID, Frame, hit_test, mirror, parse_hex, top_row
from ..core.world import Snapshot, WorldView
from .fx_window import BubbleWindow, ZzzWindow
from .pet_panel import PetWindow, make_image

DRAG_THRESHOLD = 4.0  # points the mouse must move before a press becomes a drag
THROW_WINDOW = 0.08  # seconds of drag history used to measure a throw
SCRUFF_EASE = 12.0  # how fast a picked-up pet swings to hang below the cursor
MAX_CACHED_IMAGES = 600
_LINES_FOR = {"quip": "quips", "cheer": "cheers", "bored": "bored"}

log = logging.getLogger("nibble.pet")


def _darkest(palette: dict[str, str]) -> str:
    def luminance(hex_color: str) -> float:
        r, g, b = parse_hex(hex_color)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    return min(palette.values(), key=luminance)


class PetController:
    def __init__(
        self,
        spec: PetSpec,
        size: float = 2.0,
        rng: random.Random | None = None,
        tuning: Tuning | None = None,
        peek_tuning: PeekTuning | None = None,
        backing: float = 2.0,
        worn: frozenset[str] | None = None,
    ):
        """size: requested points per sprite pixel (1.5, 2 or 3). worn: accessories on."""
        self.spec = spec.feet_on_ground()
        self.worn = frozenset(worn) if worn is not None else self.spec.default_worn
        rng = rng or random.Random()
        self.metrics = self.spec.metrics()
        m = self.metrics
        # Centre of the visible body inside the window, in grid pixels, facing right.
        self._body_cx = (m.body.left + m.body.right + 1) / 2
        self.requested = size
        self._base_tuning = tuning or Tuning()
        self._base_peek = peek_tuning or PeekTuning()
        self.scale = 0.0  # set by _apply_scale
        self.backing = backing
        self.body = Body(pet_w=0.0, pet_h=0.0)
        self.brain = Brain(rng)
        self.lines = LinePicker(self.spec, rng)
        self.window = PetWindow(GRID * size, self)
        ink = _darkest(self.spec.palette)
        self.bubble = BubbleWindow(ink)
        self.zzz = ZzzWindow(ink)

        self._standing = [f for name in STANDING for f in self.spec.frames.get(name, ())]
        self._peek_layouts: dict[tuple[int, bool, int], PeekLayout] = {}
        self._cache: dict[tuple, tuple[Frame, object, int]] = {}
        self._frame: Frame | None = None
        self._origin = (0.0, 0.0)
        self._world: WorldView | None = None

        self._press: tuple[float, float] | None = None
        self._dragging = False
        self._grab_offset = (0.0, 0.0)
        self._drag_samples: deque[tuple[float, float, float]] = deque(maxlen=12)
        self._last_state: tuple | None = None
        self._apply_scale(crisp_scale(size, backing), backing)

    # ---- size -----------------------------------------------------------

    def set_size(self, size: float) -> None:
        """Change the requested size live (Small/Medium/Large)."""
        self.requested = size
        self._apply_scale(crisp_scale(size, self.backing), self.backing)

    def set_worn(self, worn: frozenset[str]) -> None:
        """Put accessories on or take them off (e.g. Pearl's glasses)."""
        self.worn = frozenset(worn)
        self._cache.clear()

    def set_tuning(self, tuning: Tuning, peek_tuning: PeekTuning) -> None:
        """New behaviour (Energy), still scaled to this pet's size."""
        self._base_tuning, self._base_peek = tuning, peek_tuning
        k = size_factor(self.scale)
        self.brain.set_tuning(tuning.for_size(k), peek_tuning.for_size(k))

    def _follow_display(self, display: Display | None) -> None:
        """Re-snap to whole device pixels when moving to a display with a different backing scale."""
        if display is None or display.backing == self.backing:
            return
        self._apply_scale(crisp_scale(self.requested, display.backing), display.backing)

    def _apply_scale(self, scale: float, backing: float) -> None:
        self.backing = backing
        self.window.backing = backing
        if scale == self.scale:
            return
        ratio = scale / self.scale if self.scale else 1.0
        self.scale = scale
        m = self.metrics
        self.body.pet_w, self.body.pet_h = m.size(scale)
        p = self.body.peek
        if p is not None:  # keep showing the same share of the pet
            p.depth, p.target, p.speed = p.depth * ratio, p.target * ratio, p.speed * ratio
        self.baseline = m.baseline(scale)
        self.window.resize(GRID * scale)
        self.zzz.scale = size_factor(scale)
        self._cache.clear()
        self._peek_layouts.clear()
        self._world = None  # surfaces depend on the pet's size
        self.set_tuning(self._base_tuning, self._base_peek)
        log.debug("%s drawn at %g pt per pixel (%g device px)", self.spec.name, scale, scale * backing)

    # ---- lifecycle ------------------------------------------------------

    def drop_in(self, snapshot: Snapshot) -> None:
        """Fall from the top of the screen onto (ideally) the focused window."""
        world = self.world(snapshot)
        if world.active is not None:
            x = world.active.bounds.center[0]
            d = world.active_display
        else:
            d = display_for_point(0, 0, world.displays)
            x = d.frame.center[0] if d else 0.0
        self._follow_display(d)
        top = (d.visible.top if d else 800.0) - self.body.pet_h - 4
        self.body.drop_in(x, top)
        self.window.show()

    def close(self) -> None:
        self.window.close()
        self.bubble.close()
        self.zzz.close()

    def world(self, snapshot: Snapshot) -> WorldView:
        if self._world is None or self._world.snapshot is not snapshot:
            self._world = WorldView(snapshot, self.body.pet_w, self.body.pet_h)
        return self._world

    @property
    def busy(self) -> bool:
        """Moving, being handled, or animating, so it needs the fast tick rate."""
        b = self.body
        if self._press is not None or self.bubble.animating(time.monotonic()):
            return True
        if b.mode is Mode.PEEKING:
            return b.peek is not None and not b.peek.settled
        return b.mode is not Mode.STANDING or b.walk_target is not None

    @property
    def available(self) -> bool:
        """Free to deliver a cheer (not mid-air or in someone's hand)."""
        return self.body.mode in (Mode.STANDING, Mode.PEEKING)

    def tracked_windows(self) -> set[int]:
        """Windows whose movement we must follow closely (standing on / hopping to)."""
        keys = [self.body.support, self.body.hop.target if self.body.hop else None]
        return {k[1] for k in keys if k and k[0] == "window"}

    def cheer(self, now: float) -> None:
        text = self.lines.pick("cheers")
        if text:
            self.brain.cheer(now, text)

    # ---- per tick -------------------------------------------------------

    def tick(self, now: float, dt: float, snapshot: Snapshot, ctx: Context) -> None:
        self._follow_display(self._display(self.world(snapshot)))
        world = self.world(snapshot)
        ctx = replace(ctx, pressing_pet=self._press is not None)
        if self.body.mode is Mode.HELD:
            self._follow_cursor(dt, ctx.cursor)
        self.brain.update(now, self.body, world, ctx)
        self.body.step(dt, world.surfaces)
        self._render(now, world)
        self._speak(now, ctx)
        self._update_fx(now, world)
        self._update_click_through(ctx.cursor)
        if log.isEnabledFor(logging.DEBUG):
            self._log_state(world)

    def _speak(self, now: float, ctx: Context) -> None:
        for speech in self.brain.drain_speech():
            if not ctx.can_speak:
                continue
            text = speech.text or self.lines.pick(_LINES_FOR.get(speech.kind, "quips"))
            if text:
                self.bubble.say(text, speech.kind, now)
                log.debug("%s says (%s): %s", self.spec.name, speech.kind, text)

    def _display(self, world: WorldView) -> Display | None:
        p = self.body.peek
        if p is not None:
            for d in world.displays:
                if d.id == p.display_id:
                    return d
        return display_for_point(self.body.x, self.body.y + self.body.pet_h / 2, world.displays)

    def _update_fx(self, now: float, world: WorldView) -> None:
        d = self._display(world)
        if d is None:
            return
        b, p = self.body, self.body.peek
        head_top = self._origin[1] + (GRID - (top_row(self._frame) or 0)) * self.scale if self._frame else b.y
        if p is not None and not p.upright:
            self.bubble.update(now, lambda w, h: bubble.beside(b.x, p.y, p.side, w, h, d.visible))
        else:
            self.bubble.update(now, lambda w, h: bubble.above(b.x, head_top, w, h, d.visible))
        self.zzz.update(now, self.brain.asleep and b.mode is Mode.STANDING, b.x + b.pet_w * 0.15, head_top, self.backing)

    # ---- drawing --------------------------------------------------------

    def _remember(self, key: tuple, frame: Frame, anchor: int = 0) -> tuple[Frame, object, int]:
        if len(self._cache) > MAX_CACHED_IMAGES:
            self._cache.clear()
        entry = (frame, make_image(frame, self.spec.palette), anchor)
        self._cache[key] = entry
        return entry

    def _render(self, now: float, world: WorldView) -> None:
        anim, index = self.brain.pose(now, self.body)
        index %= len(self.spec.frames.get(anim) or self.spec.frames["idle"])
        if self.body.mode is Mode.PEEKING and self.body.peek is not None:
            self._render_peek(anim, index)
            return

        facing = self.body.facing
        key = ("stand", anim, index, facing)
        entry = self._cache.get(key)
        if entry is None:
            frame = self.spec.frame(anim, index, self.worn)
            entry = self._remember(key, mirror(frame) if facing < 0 else frame)
        self._frame, image, _ = entry
        self.window.set_image(image)

        cx = self._body_cx if facing > 0 else GRID - self._body_cx
        x = self.body.x
        if self.body.mode is Mode.STANDING:
            # Step along the ledge in whole art pixels: crisper, and a third as
            # many window moves. The ledge's own position stays exact so the
            # pet doesn't jitter while riding a window.
            anchor = x - self.body.rel_x
            x = anchor + round(self.body.rel_x / self.scale) * self.scale
        self._origin = (x - cx * self.scale, self.body.y - self.baseline)
        self.window.move_to(*self._origin)

    def _render_peek(self, anim: str, index: int) -> None:
        p = self.body.peek
        assert p is not None
        look = 1 if p.upright else p.look
        lay = self._peek_layouts.get((p.side, p.upright, look))
        if lay is None:
            lay = layout(self._standing, p.side, p.upright, look, self.scale)
            self._peek_layouts[(p.side, p.upright, look)] = lay
        depth_px = lay.depth_px(p.depth)
        key = ("peek", anim, index, p.side, p.upright, look, depth_px)
        entry = self._cache.get(key)
        if entry is None:
            turned = orient(self.spec.frame(anim, index, self.worn), p.side, p.upright, look)
            entry = self._remember(key, *clip(turned, p.side, lay.ref, depth_px))
        self._frame, image, edge_col = entry
        self.window.set_image(image)
        self._origin = lay.origin(p, edge_col)
        self.window.move_to(*self._origin)

    def _update_click_through(self, cursor: tuple[float, float]) -> None:
        if self.body.mode is Mode.HELD or self._press is not None:
            self.window.set_click_through(False)
            return
        over = self._frame is not None and hit_test(
            self._frame, cursor[0] - self._origin[0], cursor[1] - self._origin[1], self.scale
        )
        self.window.set_click_through(not over)

    def _log_state(self, world: WorldView) -> None:
        b = self.body
        state = (b.mode, b.support, self.brain.activity, self.brain.peek.phase if b.mode is Mode.PEEKING else None)
        if state == self._last_state:
            return
        self._last_state = state
        where = ""
        if b.support and b.support[0] == "window":
            w = world.surfaces.window(b.support[1])
            where = f" on {w.owner}" if w else ""
        elif b.support:
            where = " on the floor"
        elif b.peek:
            where = f" at the {'right' if b.peek.side > 0 else 'left'} edge ({self.brain.peek.phase})"
        log.debug(
            "%s %s%s, %s, at (%.0f, %.0f); focused: %s",
            self.spec.name, b.mode.value, where, self.brain.activity.value, b.x, b.y, world.snapshot.frontmost_name,
        )

    # ---- mouse ----------------------------------------------------------

    def on_mouse_down(self, x: float, y: float, clicks: int) -> None:
        self._press = (x, y)
        self._dragging = False

    def on_mouse_dragged(self, x: float, y: float) -> None:
        if self._press is None:
            return
        if not self._dragging:
            if math.hypot(x - self._press[0], y - self._press[1]) < DRAG_THRESHOLD:
                return
            self._dragging = True
            if self.body.mode is Mode.PEEKING and self.body.peek is not None:
                # Pull it out from the edge by its head.
                p = self.body.peek
                self.body.x, self.body.y = x + p.side * self.body.pet_w / 2, y - self.body.pet_h * 0.85
            self.body.grab()
            self._grab_offset = (self.body.x - x, self.body.y - y)
            self._drag_samples.clear()
        self._drag_samples.append((time.monotonic(), x, y))

    def on_mouse_up(self, x: float, y: float, clicks: int) -> None:
        was_dragging = self._dragging
        self._press = None
        self._dragging = False
        now = time.monotonic()
        if not was_dragging:
            self.brain.on_clicked(now)
            return
        vx = vy = 0.0
        recent = [s for s in self._drag_samples if now - s[0] <= THROW_WINDOW]
        if len(recent) >= 2 and recent[-1][0] > recent[0][0]:
            span = recent[-1][0] - recent[0][0]
            vx = (recent[-1][1] - recent[0][1]) / span
            vy = (recent[-1][2] - recent[0][2]) / span
        self.body.release(vx, vy)
        if self._world is not None:
            self.brain.on_dropped(self._world, now)

    def _follow_cursor(self, dt: float, cursor: tuple[float, float]) -> None:
        # Ease from wherever we were grabbed to hanging by the scruff.
        ox, oy = self._grab_offset
        k = min(1.0, SCRUFF_EASE * dt)
        tx, ty = 0.0, -self.body.pet_h * 0.85
        self._grab_offset = (ox + (tx - ox) * k, oy + (ty - oy) * k)
        self.body.hold_at(cursor[0] + self._grab_offset[0], cursor[1] + self._grab_offset[1])
