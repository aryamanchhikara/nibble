"""When a pet cheers you on.

Three triggers, one shared rate limit (so it feels like a friend, not a
notification centre):
- focus: you've stayed in coding / terminal / writing apps for a while
  without wandering off to social, video or a call;
- welcome back: you return after a long time away from the keyboard;
- random: an occasional nudge while you're actively working.

Never during calls, in Quiet mode, with "Cheer me on" off, or while the pet
sleeps. Demo mode divides every interval by the demo factor.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .apps import DISTRACTING, PRODUCTIVE, Category

MINUTE = 60.0
WELCOME_WINDOW = 90.0  # a welcome-back that can't be said within this long is dropped


@dataclass(frozen=True)
class CheerTuning:
    min_gap: float = 15 * MINUTE  # between any two cheers
    focus_after: float = 20 * MINUTE  # of productive time before the first focus cheer
    focus_repeat: float = 25 * MINUTE  # more focus time before the next one
    away_after: float = 10 * MINUTE  # idle this long counts as "away"
    welcome_delay: float = 4.0  # seconds after you're back before saying hi
    random_every: float = 40 * MINUTE  # average gap for random nudges while working
    active_within: float = 60.0  # input this recent means you're actively working
    gone_after: float = 5 * MINUTE  # idle this long breaks a focus streak

    def scaled(self, factor: float) -> CheerTuning:
        """The waits divided by factor (demo mode).

        What counts as "actively working" or "gone" stays the same, so pausing
        to talk to the camera doesn't wipe out a demo focus streak.
        """
        if factor == 1:
            return self
        return replace(self, **{name: getattr(self, name) / factor for name in _SCALED})


_SCALED = ("min_gap", "focus_after", "focus_repeat", "away_after", "random_every")


@dataclass
class Moment:
    """What's going on right now, as far as cheering is concerned."""

    now: float
    category: Category
    user_idle: float
    in_call: bool = False
    quiet: bool = False
    enabled: bool = True
    pet_asleep: bool = False


class FocusTracker:
    """Seconds of productive work since you last got distracted or left."""

    def __init__(self, tuning: CheerTuning):
        self.tuning = tuning
        self.streak = 0.0
        self._last: float | None = None

    def update(self, m: Moment) -> None:
        dt = 0.0 if self._last is None else max(0.0, m.now - self._last)
        self._last = m.now
        if m.in_call or m.category in DISTRACTING or m.user_idle >= self.tuning.gone_after:
            self.streak = 0.0
        elif m.category in PRODUCTIVE and m.user_idle < self.tuning.active_within:
            self.streak += dt
        # Anything else (a browser, Finder, Slack) pauses the streak without ending it.


class CheerScheduler:
    def __init__(self, tuning: CheerTuning | None = None, rng: random.Random | None = None):
        self.tuning = tuning or CheerTuning()
        self.rng = rng or random.Random()
        self.focus = FocusTracker(self.tuning)
        self.last_cheer = -1e18
        self._next_focus_mark = self.tuning.focus_after
        self._away = False
        self._welcome_at: float | None = None
        self._last: float | None = None

    def update(self, m: Moment) -> str | None:
        """Returns why to cheer right now ("focus", "welcome", "random"), or None."""
        t = self.tuning
        dt = 0.0 if self._last is None else max(0.0, m.now - self._last)
        self._last = m.now
        self.focus.update(m)
        if self.focus.streak == 0:
            self._next_focus_mark = t.focus_after

        # Track leaving and coming back even when we can't speak right now.
        if m.user_idle >= t.away_after:
            self._away = True
            self._welcome_at = None
        elif self._away and m.user_idle < 2.0:
            self._away = False
            self._welcome_at = m.now + t.welcome_delay

        if not m.enabled or m.quiet or m.in_call or m.category is Category.CALL:
            self._welcome_at = None
            return None
        if m.now - self.last_cheer < t.min_gap:
            return None

        if self._welcome_at is not None and m.now > self._welcome_at + WELCOME_WINDOW:
            self._welcome_at = None  # too late to say hi now

        reason = None
        if self._welcome_at is not None and m.now >= self._welcome_at:
            reason = "welcome"
        elif self.focus.streak >= self._next_focus_mark:
            reason = "focus"
        elif (
            m.category in PRODUCTIVE
            and m.user_idle < t.active_within
            and self.rng.random() < dt / t.random_every
        ):
            reason = "random"

        if reason is None:
            return None
        if m.pet_asleep and reason != "welcome":
            return None  # only a welcome-back may wake the pet; the rest can wait
        if reason == "welcome":
            self._welcome_at = None
        elif reason == "focus":
            self._next_focus_mark = self.focus.streak + t.focus_repeat
        self.last_cheer = m.now
        return reason
