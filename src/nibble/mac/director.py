"""Runs the show: one timer drives the world scans and every pet.

Talking to the window server is the expensive part, so it's rationed:
- A full window scan runs every 0.5 s (0.25 s while busy), right after an app,
  Space or display change, and right after any mouse click, since clicks are
  how focus usually moves between windows of the same app.
- Windows a pet stands on are polled on their own (~0.1 ms). Windows only get
  dragged while a mouse button is down, so that's when we poll every tick;
  otherwise 4×/s catches keyboard tiling and scripted moves.
- The timer runs at 60 Hz while anything moves and 15 Hz otherwise.

NSEvent.pressedMouseButtons() reads the button state without any permission.

The director also owns the things pets share: what the user is doing (idle
time, which kind of app is in front, whether a call is on) and the cheer
scheduler, so several pets never pile on with encouragement at once.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSApplicationDidChangeScreenParametersNotification,
    NSEvent,
    NSWorkspace,
    NSWorkspaceActiveSpaceDidChangeNotification,
    NSWorkspaceDidActivateApplicationNotification,
)
from Foundation import NSNotificationCenter, NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer

from ..core import energy as energy_profiles
from ..core import settings as settings_store
from ..core.apps import Category, categorize
from ..core.cheers import CheerScheduler, CheerTuning, Moment
from ..core.context import Context
from ..core import size as sizes
from ..core.energy import Energy
from ..core.settings import Settings
from ..core.size import Size
from ..core.spec import PetSpec
from ..core.world import Snapshot
from .calls import CameraWatcher
from .pet_controller import PetController
from .world import WorldWatcher

log = logging.getLogger(__name__)

TICK_BUSY = 1 / 60
TICK_CALM = 1 / 15
CALM_AFTER = 0.5  # seconds of stillness before slowing down
SCAN_INTERVAL_BUSY = 0.25
SCAN_INTERVAL_CALM = 0.5
SCAN_AFTER_CLICK = 0.05  # give the window server a moment to reorder windows
POLL_INTERVAL_STILL = 0.25
MOVING_GRACE = 0.6  # keep polling every tick this long after a window last moved

# --demo speeds up the slow timers so everything can be recorded in one take:
# 15 minutes between cheers becomes 30 s. Movement uses the lively demo profile
# from energy.py regardless of the Energy setting.
DEMO_FACTOR = 30.0


class Callback(NSObject):
    """Lets a Python callable be an Objective-C target/observer."""

    def initWithCallable_(self, fn: Callable[[], None]):
        self = objc.super(Callback, self).init()
        if self is not None:
            self.fn = fn
        return self

    def fire_(self, _sender) -> None:
        # An exception escaping into AppKit would pop PyObjC's "unexpected
        # error" alert; log it instead.
        try:
            self.fn()
        except Exception:
            log.exception("callback failed")


@dataclass
class _Poll:
    moved_at: float = -1e9
    next_at: float = 0.0


class Director:
    def __init__(self, demo: bool = False, settings_path: Path | None = None):
        self.demo = demo
        self.settings_path = settings_path
        self.settings = settings_store.load(settings_path) if settings_path else Settings()
        self.energy = energy_profiles.parse(self.settings.energy)
        self.size = sizes.parse(self.settings.size)
        self.tuning, self.peek_tuning = energy_profiles.profiles(self.energy, demo)
        self.cheers = CheerScheduler(CheerTuning().scaled(DEMO_FACTOR if demo else 1.0))
        self.camera = CameraWatcher()
        self.category = Category.OTHER
        self.watcher = WorldWatcher()
        self.snapshot: Snapshot = self.watcher.scan()
        self.pets: list[PetController] = []
        self.on_tick: list[Callable[[Snapshot], None]] = []
        self._polls: dict[int, _Poll] = {}
        self._next_scan = 0.0
        self._last = time.monotonic()
        self._timer = None
        self._interval = 0.0
        self._busy_until = 0.0
        self._mouse_down = False
        self._errors = 0
        self._tick_cb = Callback.alloc().initWithCallable_(self._tick)
        self._rescan_cb = Callback.alloc().initWithCallable_(self.rescan)

    def start(self) -> None:
        self._set_interval(TICK_BUSY)
        self.camera.start()

        ws = NSWorkspace.sharedWorkspace().notificationCenter()
        for name in (NSWorkspaceDidActivateApplicationNotification, NSWorkspaceActiveSpaceDidChangeNotification):
            ws.addObserver_selector_name_object_(self._rescan_cb, "fire:", name, None)
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self._rescan_cb, "fire:", NSApplicationDidChangeScreenParametersNotification, None
        )

    def stop(self) -> None:
        self.camera.stop()
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        for pet in self.pets:
            pet.close()
        self.pets.clear()

    def _set_interval(self, interval: float) -> None:
        if interval == self._interval:
            return
        self._interval = interval
        if self._timer is not None:
            self._timer.invalidate()
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            interval, self._tick_cb, "fire:", None, True
        )
        # Common modes keep pets moving while a menu is open or the mouse is held.
        NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    def rescan(self) -> None:
        self._next_scan = 0.0

    def update_settings(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self.settings, key, value)
        if self.settings_path:
            settings_store.save(self.settings_path, self.settings)

    def set_energy(self, energy: Energy) -> None:
        self.energy = energy
        self.update_settings(energy=energy.value)
        if self.demo:
            return  # demo mode keeps its own lively profile
        self.tuning, self.peek_tuning = energy_profiles.profiles(energy)
        for pet in self.pets:
            pet.set_tuning(self.tuning, self.peek_tuning)

    def set_size(self, size: Size) -> None:
        self.size = size
        self.update_settings(size=size.value)
        for pet in self.pets:
            pet.set_size(size.scale)

    def spawn(self, spec: PetSpec, worn: frozenset[str] | None = None) -> PetController:
        """Drop a pet in. worn: its accessories (default: the pet's own defaults)."""
        if worn is None and spec.id in self.settings.wardrobe:
            worn = frozenset(self.settings.wardrobe[spec.id])
        pet = PetController(
            spec,
            size=self.size.scale,
            rng=random.Random(),
            tuning=self.tuning,
            peek_tuning=self.peek_tuning,
            worn=worn,
        )
        self.snapshot = self.watcher.scan()
        pet.drop_in(self.snapshot)
        self.pets.append(pet)
        self._save_lineup()
        return pet

    def swap(self, spec: PetSpec, worn: frozenset[str] | None = None) -> PetController:
        """Send every pet home and drop this one in instead."""
        for pet in self.pets:
            pet.close()
        self.pets.clear()
        return self.spawn(spec, worn)

    def set_worn(self, pet_id: str, worn: frozenset[str]) -> None:
        """Accessories for a kind of pet: remembered, and applied to any that are out."""
        self.settings.wardrobe[pet_id] = sorted(worn)
        for pet in self.pets:
            if pet.spec.id == pet_id:
                pet.set_worn(worn)
        self._save_lineup()

    def running_names(self) -> list[str]:
        return [pet.spec.name for pet in self.pets]

    def _save_lineup(self) -> None:
        self.update_settings(pets=[{"id": p.spec.id, "worn": sorted(p.worn)} for p in self.pets])

    def respawn_all(self) -> None:
        self.snapshot = self.watcher.scan()
        for pet in self.pets:
            pet.drop_in(self.snapshot)

    # ---- loop -----------------------------------------------------------

    def _tick(self) -> None:
        try:
            self._step()
            self._errors = 0
        except Exception:
            # Never let one bad tick kill the app; log the first few in a row.
            self._errors += 1
            if self._errors <= 3:
                log.exception("tick failed")

    def _step(self) -> None:
        now = time.monotonic()
        dt = min(max(now - self._last, 0.0), 0.1)
        self._last = now

        mouse_down = NSEvent.pressedMouseButtons() != 0
        if self._mouse_down and not mouse_down:
            self._next_scan = min(self._next_scan, now + SCAN_AFTER_CLICK)
        self._mouse_down = mouse_down

        busy = now < self._busy_until
        if now >= self._next_scan:
            self.snapshot = self.watcher.scan()
            self._next_scan = now + (SCAN_INTERVAL_BUSY if busy else SCAN_INTERVAL_CALM)
        else:
            self._poll_tracked(now, eager=mouse_down)

        ctx = self._context(mouse_down)
        self._maybe_cheer(now, ctx)
        for pet in self.pets:
            pet.tick(now, dt, self.snapshot, ctx)
        for fn in self.on_tick:
            fn(self.snapshot)

        windows_moving = any(now - poll.moved_at < MOVING_GRACE for poll in self._polls.values())
        if mouse_down or windows_moving or any(pet.busy for pet in self.pets):
            self._busy_until = now + CALM_AFTER
        self._set_interval(TICK_BUSY if now < self._busy_until else TICK_CALM)

    def _context(self, mouse_down: bool) -> Context:
        p = NSEvent.mouseLocation()
        self.category = categorize(self.snapshot.frontmost_bundle, self.snapshot.frontmost_name)
        in_call = self.category is Category.CALL or self.camera.in_use
        return Context(
            cursor=(p.x, p.y),
            mouse_down=mouse_down,
            user_idle=self.watcher.user_idle(),
            in_call=in_call,
            can_speak=not (self.settings.quiet or in_call),
        )

    def _maybe_cheer(self, now: float, ctx: Context) -> None:
        if not self.pets:
            return
        reason = self.cheers.update(
            Moment(
                now=now,
                category=self.category,
                user_idle=ctx.user_idle,
                in_call=ctx.in_call,
                quiet=self.settings.quiet,
                enabled=self.settings.cheer_me_on,
                pet_asleep=all(pet.brain.asleep for pet in self.pets),
            )
        )
        if reason is None:
            return
        # A pet that's mid-hop still gets it: the brain holds a cheer for a few seconds.
        awake = [pet for pet in self.pets if reason == "welcome" or not pet.brain.asleep]
        if awake:
            pet = random.choice(awake)
            log.info("%s cheers you on (%s)", pet.spec.name, reason)
            pet.cheer(now)

    def _poll_tracked(self, now: float, eager: bool) -> None:
        wanted: set[int] = set()
        for pet in self.pets:
            wanted |= pet.tracked_windows()
        for wid in list(self._polls):
            if wid not in wanted:
                del self._polls[wid]

        current = {w.id: w.bounds for w in self.snapshot.windows if w.id in wanted}
        for wid in wanted:
            poll = self._polls.setdefault(wid, _Poll())
            if now < poll.next_at and not eager:
                continue
            bounds = self.watcher.bounds_of(wid)
            if bounds != current.get(wid):
                poll.moved_at = now
                self.snapshot = self.snapshot.with_window_bounds(wid, bounds)
            moving = now - poll.moved_at < MOVING_GRACE
            poll.next_at = now if moving else now + POLL_INTERVAL_STILL
