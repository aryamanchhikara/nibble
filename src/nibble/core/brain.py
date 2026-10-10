"""What a pet decides to do from moment to moment.

The brain only issues intents to the body (walk here, hop there, peek), queues
things to say, and picks which animation frame to show. It takes the clock
and RNG from outside, so tests can drive it deterministically.

Where it goes comes from WorldView.home(): stand on the focused window, or
peek from its outer side. It waits a beat before moving (so flicking between
windows doesn't send it bouncing around), stays wherever you drop it until
focus changes, and never settles on the screen floor by itself.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from .context import Context
from .geometry import display_for_point
from .peek import LEAVE, PeekBrain, PeekTuning
from .physics import LANDED, Body, Mode
from .size import scale_fields
from .world import Home, WorldView


# Pause before moving when where we stand is no good (covered, or on the floor).
STRANDED_DELAY = 0.35


class Activity(Enum):
    IDLE = "idle"
    WALK = "walk"
    SIT = "sit"
    LAND = "land"
    SLEEP = "sleep"
    WAKE = "wake"
    CHEER = "cheer"
    CHASE = "chase"


class Speech(NamedTuple):
    kind: str  # "quip", "cheer" or "bored"
    text: str | None  # None: pick a line of that kind


@dataclass(frozen=True)
class Tuning:
    """How the pet behaves. The defaults are the calm "Chill" energy (see energy.py).

    Distances and speeds are in points for a Large pet; for_size() scales them
    to the pet's actual size.
    """

    # Following you around
    reaction_delay: tuple[float, float] = (1.2, 2.2)  # pause before moving to a newly focused window
    hop_pace: float = 1.8  # >1 = slower, calmer hops

    # Hanging out
    idle_time: tuple[float, float] = (8.0, 20.0)
    sit_time: tuple[float, float] = (40.0, 120.0)
    walk_every: tuple[float, float] = (150.0, 300.0)  # at least this long between walks
    walk_chance: float = 0.35  # chance an idle spell ends in a walk, when one's allowed
    walk_distance: tuple[float, float] = (30.0, 110.0)
    walk_speed: float = 26.0
    nap_chance: float = 0.3  # chance a sit drifts off into a nap
    nap_time: tuple[float, float] = (60.0, 240.0)

    # Cursor chasing: only after a deliberate hover, and it gives up quickly
    chase_hover: float = 1.5
    chase_radius: float = 90.0
    chase_for: float = 2.5
    chase_speed: float = 50.0
    bored_for: float = 90.0  # ignores the cursor after giving up

    # Sleeping while you're away
    sleep_after: float = 120.0
    wake_radius: float = 120.0  # cursor this close wakes it
    wake_after_active: float = 90.0  # or you've been back at it this long
    wake_for: float = 0.8

    # Animation
    land_pause: float = 0.4
    blink_every: tuple[float, float] = (2.5, 6.0)
    blink_length: float = 0.14
    stride: float = 6.0  # points walked per walk frame, so feet don't slide
    dangle_fps: float = 4.0
    happy_fps: float = 5.0
    sleep_fps: float = 0.7
    cheer_for: float = 1.4
    cheer_patience: float = 10.0  # drop a cheer that couldn't be delivered by then

    def for_size(self, factor: float) -> Tuning:
        return scale_fields(self, _SPATIAL, factor)


_SPATIAL = ("walk_distance", "walk_speed", "chase_radius", "chase_speed", "wake_radius", "stride")


class Brain:
    def __init__(
        self,
        rng: random.Random | None = None,
        tuning: Tuning | None = None,
        peek_tuning: PeekTuning | None = None,
    ):
        self.rng = rng or random.Random()
        self.tuning = tuning or Tuning()
        self.peek = PeekBrain(self.rng, peek_tuning)
        self.activity = Activity.IDLE
        self.until = 0.0
        self.pending_home: tuple[tuple, float] | None = None
        # Set when the user drops the pet somewhere by hand: it stays put until
        # the focused window changes.
        self.pinned = False
        self.pinned_active: int | None = None
        self.next_blink = 0.0
        self.blink_until = 0.0
        self.next_walk = 0.0
        self.nap_until: float | None = None  # set while napping (vs asleep because you're away)
        self.hover_since: float | None = None
        self.bored_until = 0.0
        self.speech: list[Speech] = []
        self.pending_cheer: tuple[str, float] | None = None
        self._active_since: float | None = None
        self._holding_still = False  # sitting tight through a call

    @property
    def asleep(self) -> bool:
        return self.activity is Activity.SLEEP

    def set_tuning(self, tuning: Tuning, peek_tuning: PeekTuning) -> None:
        self.tuning = tuning
        self.peek.tuning = peek_tuning

    # ---- events from the controller -------------------------------------

    def on_dropped(self, world: WorldView, now: float = 0.0) -> None:
        self.pinned = True
        self.pinned_active = world.active_id
        self.pending_home = None

    def on_clicked(self, now: float) -> None:
        if self.asleep:
            self._wake(now)
        else:
            self._say("quip")

    def cheer(self, now: float, text: str) -> None:
        """Cheer the user on as soon as the pet is free to."""
        self.pending_cheer = (text, now + self.tuning.cheer_patience)

    # ---- per tick -------------------------------------------------------

    def update(self, now: float, body: Body, world: WorldView, ctx: Context | None = None) -> None:
        ctx = ctx or Context()
        self._schedule_blinks(now)
        self._track_user(now, ctx)
        if self.pending_cheer and now > self.pending_cheer[1]:
            self.pending_cheer = None
        if body.mode in (Mode.HELD, Mode.FALLING, Mode.HOPPING):
            return

        home = self._resolve_home(world, body)
        if body.mode is Mode.PEEKING and self.peek.phase == LEAVE:
            self._keep_leaving(body, world, home)
            return

        want = home.ident if home else None
        here = self._here(body)
        stranded = self._stranded(body, world)
        if stranded and home is None:
            body.drop_in(body.x, body.y)  # covered with nowhere better to be: just fall
            return
        if want is not None and want != here:
            if self.pending_home is None or self.pending_home[0] != want:
                delay = STRANDED_DELAY if stranded else self.rng.uniform(*self.tuning.reaction_delay)
                self.pending_home = (want, now + delay)
            elif stranded and self.pending_home[1] > now + STRANDED_DELAY:
                self.pending_home = (want, now + STRANDED_DELAY)
            elif now >= self.pending_home[1]:
                self.pending_home = None
                self._move_home(now, body, world, home)
                return
        else:
            self.pending_home = None

        if body.mode is Mode.PEEKING:
            if self.asleep:
                self.activity = Activity.IDLE  # no napping at the edge
            edges = home.peek if home is not None and want == here else None
            self.peek.update(now, body, edges, ctx, self._say)
            if self.pending_cheer:
                self.peek.cheer(self.pending_cheer[0])
                self.pending_cheer = None
            return

        # Standing.
        if LANDED in body.events and self.activity is not Activity.CHEER:
            self._set(Activity.LAND, now, self.tuning.land_pause)
        if self.pending_cheer:
            self._do_cheer(now, body, world, self.pending_cheer[0])
            self.pending_cheer = None
            return
        if self._sleep(now, body, ctx):
            return
        if self.pending_home is not None:
            return  # about to move somewhere: don't wander off first
        if ctx.in_call:
            # Stay still and quiet on calls.
            body.stop_walking()
            if not self._holding_still:
                self._holding_still = True
                self._set(Activity.SIT, now, 0.0)
            return
        if self._holding_still:
            self._holding_still = False
            self._set(Activity.IDLE, now, self.tuning.idle_time)
        if self._chase(now, body, world, ctx):
            return
        self._wander(now, body, world)

    def drain_speech(self) -> list[Speech]:
        speech, self.speech = self.speech, []
        return speech

    def pose(self, now: float, body: Body) -> tuple[str, int]:
        """(animation, frame index) to show right now."""
        t = self.tuning
        blink = now < self.blink_until
        if body.mode is Mode.HELD:
            return ("dangle", int(now * t.dangle_fps))
        if body.mode is Mode.PEEKING:
            return self.peek.pose(now, body, blink)
        if body.mode is Mode.HOPPING and self.activity is Activity.CHEER:
            return ("happy", int(now * t.happy_fps))
        if body.mode in (Mode.FALLING, Mode.HOPPING):
            return ("fall", 0)
        if body.walk_target is not None:
            return ("walk", int(body.distance_walked // t.stride))
        if self.activity is Activity.SLEEP:
            return ("sleep", int(now * t.sleep_fps))
        if self.activity in (Activity.CHEER, Activity.WAKE):
            return ("happy", int(now * t.happy_fps))
        if self.activity in (Activity.SIT, Activity.LAND):
            return ("sit", 0)
        return ("idle", 1 if blink else 0)

    # ---- where to be ----------------------------------------------------

    def _resolve_home(self, world: WorldView, body: Body) -> Home | None:
        if self.pinned:
            if world.active_id is None or world.active_id == self.pinned_active:
                return None
            self.pinned = False
        home = world.home()
        if home is None and body.mode is Mode.STANDING and body.support and body.support[0] == "floor":
            # Nothing focused and we ended up on the floor: peek from the screen edge instead.
            d = display_for_point(body.x, body.y, world.displays)
            return world.screen_home(d) if d else None
        return home

    def _stranded(self, body: Body, world: WorldView) -> bool:
        """Standing somewhere we shouldn't stay: a covered edge, or the floor we weren't put on."""
        if body.mode is not Mode.STANDING or body.support is None:
            return False
        if body.support[0] == "floor":
            return not self.pinned
        return not world.surfaces.standable(body.support)

    @staticmethod
    def _here(body: Body) -> tuple | None:
        if body.mode is Mode.STANDING and body.support is not None:
            return ("stand", body.support)
        if body.mode is Mode.PEEKING and body.peek is not None:
            p = body.peek
            return ("peek", p.window_id if p.window_id is not None else ("screen", p.display_id))
        return None

    def _move_home(self, now: float, body: Body, world: WorldView, home: Home) -> None:
        """One calm move to where we belong."""
        self.activity = Activity.IDLE
        self.nap_until = None
        if home.stand is not None:
            if body.mode is Mode.PEEKING:
                self._keep_leaving(body, world, home)
            else:
                x = world.surfaces.nearest_point(home.stand, body.x, inset=body.edge_inset)
                if x is not None:
                    body.hop_to(home.stand, x, world.surfaces, self.tuning.hop_pace)
        elif body.mode is Mode.PEEKING:
            self.peek.relocate(home.peek, body)  # duck out, reappear at the new window's side
        else:
            self.peek.enter(now, body, home.peek, self.tuning.hop_pace)

    def _keep_leaving(self, body: Body, world: WorldView, home: Home | None) -> None:
        """Slide out from the edge, stand up, then hop onto the window."""
        if home is None or home.stand is None:
            # Changed our mind mid-exit: peek somewhere again instead.
            self.peek.relocate(home.peek if home else self.peek._next_edges, body)
            return
        if self.peek.leave(body):
            body.stop_peeking()
            x = world.surfaces.nearest_point(home.stand, body.x, inset=body.edge_inset)
            if x is not None:
                body.hop_to(home.stand, x, world.surfaces, self.tuning.hop_pace)

    # ---- hanging out ----------------------------------------------------

    def _say(self, kind: str, text: str | None = None) -> None:
        self.speech.append(Speech(kind, text))

    def _set(self, activity: Activity, now: float, duration: float | tuple[float, float]) -> None:
        if isinstance(duration, tuple):
            duration = self.rng.uniform(*duration)
        self.activity = activity
        self.until = now + duration

    def _schedule_blinks(self, now: float) -> None:
        if now >= self.next_blink:
            self.blink_until = now + self.tuning.blink_length
            self.next_blink = now + self.rng.uniform(*self.tuning.blink_every)

    def _track_user(self, now: float, ctx: Context) -> None:
        if ctx.user_idle < 1.0:
            if self._active_since is None:
                self._active_since = now
        elif ctx.user_idle > 5.0:
            self._active_since = None

    def _wake(self, now: float) -> None:
        self.nap_until = None
        self._set(Activity.WAKE, now, self.tuning.wake_for)

    def _sleep(self, now: float, body: Body, ctx: Context) -> bool:
        """Naps, and sleeping while you're away. True while asleep."""
        t = self.tuning
        near = math.hypot(ctx.cursor[0] - body.x, ctx.cursor[1] - (body.y + body.pet_h / 2)) < t.wake_radius
        if self.asleep:
            if self.nap_until is not None:
                if near:
                    self._wake(now)
                    return False
                if now >= self.nap_until:
                    if ctx.user_idle >= t.sleep_after:
                        self.nap_until = None  # you left during the nap: keep sleeping
                        return True
                    self._wake(now)
                    return False
                return True
            back = self._active_since is not None and now - self._active_since >= t.wake_after_active
            if near or back:
                self._wake(now)
                return False
            return True
        if ctx.user_idle >= t.sleep_after and self.activity not in (Activity.CHEER, Activity.WAKE):
            body.stop_walking()
            self.nap_until = None
            self._set(Activity.SLEEP, now, 0.0)
            return True
        return False

    def _do_cheer(self, now: float, body: Body, world: WorldView, text: str) -> None:
        body.stop_walking()
        self.nap_until = None
        if body.support is not None:
            body.hop_to(body.support, body.x, world.surfaces)  # a happy little hop in place
        self._set(Activity.CHEER, now, self.tuning.cheer_for)
        self._say("cheer", text)

    def _chase(self, now: float, body: Body, world: WorldView, ctx: Context) -> bool:
        """Follow a cursor that lingers just above the pet, then lose interest."""
        t = self.tuning
        dx = ctx.cursor[0] - body.x
        dy = ctx.cursor[1] - body.y
        # Just above the pet and off to one side (right on top of it isn't chasing).
        hovering = body.pet_w * 0.4 < abs(dx) < t.chase_radius and 0.0 < dy < body.pet_h * 2.1

        if self.activity is Activity.CHASE:
            if now >= self.until:
                body.stop_walking()
                self.bored_until = now + t.bored_for
                self._set(Activity.SIT, now, t.sit_time)
                if self.rng.random() < 0.6:
                    self._say("bored")
                return True
            if abs(dx) > t.chase_radius * 2.5 or dy < -body.pet_h * 0.3 or dy > body.pet_h * 3.8:
                body.stop_walking()  # the cursor wandered off
                self._set(Activity.IDLE, now, t.idle_time)
                return True
            seg = world.surfaces.segment_at(body.support, body.x) if body.support else None
            if seg is not None:
                target = seg.clamp(ctx.cursor[0], body.edge_inset)
                if abs(target - body.x) > t.stride:
                    body.walk_to(target, world.surfaces, t.chase_speed)
                else:
                    body.stop_walking()
            return True

        if ctx.mouse_down or now < self.bored_until or self.activity is Activity.WALK or not hovering:
            self.hover_since = None
            return False
        body.facing = 1 if dx > 0 else -1  # it notices you
        if self.hover_since is None:
            self.hover_since = now
        elif now - self.hover_since >= t.chase_hover:
            self.hover_since = None
            self._set(Activity.CHASE, now, t.chase_for)
            return True
        return False

    def _wander(self, now: float, body: Body, world: WorldView) -> None:
        t = self.tuning
        if self.activity is Activity.WALK:
            if body.walk_target is None:
                self._set(Activity.IDLE, now, t.idle_time)
            return
        if now < self.until:
            return
        if self.activity is Activity.SIT:
            if self.rng.random() < t.nap_chance:
                self._set(Activity.SLEEP, now, 0.0)
                self.nap_until = now + self.rng.uniform(*t.nap_time)
            else:
                self._set(Activity.IDLE, now, t.idle_time)
            return
        if self.activity is not Activity.IDLE:
            self._set(Activity.IDLE, now, t.idle_time)
            return
        if now >= self.next_walk and self.rng.random() < t.walk_chance and self._start_walk(body, world):
            self.next_walk = now + self.rng.uniform(*t.walk_every)
            return
        if self.rng.random() < 0.8:
            self._set(Activity.SIT, now, t.sit_time)
        else:
            self._set(Activity.IDLE, now, t.idle_time)

    def _start_walk(self, body: Body, world: WorldView) -> bool:
        if body.support is None:
            return False
        seg = world.surfaces.segment_at(body.support, body.x)
        if seg is None:
            return False
        lo, hi = seg.x0 + body.edge_inset, seg.x1 - body.edge_inset
        if hi - lo < body.pet_w * 0.3:
            return False
        room_left, room_right = max(0.0, body.x - lo), max(0.0, hi - body.x)
        direction = 1 if self.rng.random() * (room_left + room_right) < room_right else -1
        target = min(max(body.x + direction * self.rng.uniform(*self.tuning.walk_distance), lo), hi)
        if abs(target - body.x) < body.pet_w * 0.25:
            return False
        body.walk_to(target, world.surfaces, self.tuning.walk_speed)
        self.activity = Activity.WALK
        return True
