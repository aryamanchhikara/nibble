import random

import pytest

from nibble.core.apps import Category
from nibble.core.cheers import CheerScheduler, CheerTuning, Moment

MIN = 60.0
# No random nudges unless a test asks for them.
QUIET_RNG = CheerTuning(random_every=1e12)


class Clock:
    def __init__(self, tuning=QUIET_RNG, seed=1):
        self.s = CheerScheduler(tuning, random.Random(seed))
        self.now = 0.0
        self.fired: list[tuple[float, str]] = []

    def run(self, seconds, step=1.0, **moment):
        moment.setdefault("category", Category.CODING)
        moment.setdefault("user_idle", 2.0)
        end = self.now + seconds
        while self.now < end:
            self.now += step
            reason = self.s.update(Moment(now=self.now, **moment))
            if reason:
                self.fired.append((self.now, reason))
        return [r for _, r in self.fired]


def test_focus_cheer_after_twenty_minutes_of_coding():
    c = Clock()
    assert c.run(19 * MIN) == []
    assert c.run(2 * MIN) == ["focus"]


def test_terminal_and_writing_count_toward_the_same_streak():
    c = Clock()
    c.run(8 * MIN, category=Category.TERMINAL)
    c.run(8 * MIN, category=Category.WRITING)
    c.run(5 * MIN, category=Category.CODING)
    assert c.fired and c.fired[0][1] == "focus"


def test_social_media_resets_the_streak():
    c = Clock()
    c.run(15 * MIN)
    c.run(10, category=Category.SOCIAL)
    assert c.run(15 * MIN) == []  # only 15 minutes since the detour


def test_a_browser_pauses_the_streak_without_resetting_it():
    c = Clock()
    c.run(15 * MIN)
    c.run(10 * MIN, category=Category.BROWSER)
    assert c.run(6 * MIN) == ["focus"]


def test_walking_away_resets_the_streak():
    c = Clock()
    c.run(15 * MIN)
    c.run(6 * MIN, user_idle=6 * MIN)
    c.fired.clear()
    assert "focus" not in c.run(15 * MIN)


def test_keeps_its_distance_between_cheers():
    c = Clock(CheerTuning(random_every=1.0))  # wants to cheer constantly
    c.run(60 * MIN)
    times = [t for t, _ in c.fired]
    assert len(times) >= 3
    assert all(b - a >= 15 * MIN for a, b in zip(times, times[1:]))


def test_random_nudges_average_out_to_the_configured_rate():
    c = Clock(CheerTuning(min_gap=0, focus_after=1e12, random_every=10 * MIN), seed=3)
    c.run(1000 * MIN)
    assert 60 <= len(c.fired) <= 140  # ~100 expected


def test_welcome_back_after_a_long_break():
    c = Clock()
    c.run(1 * MIN)
    c.run(11 * MIN, user_idle=11 * MIN, category=Category.OTHER)
    c.fired.clear()
    assert c.run(10, user_idle=0.5, category=Category.OTHER) == ["welcome"]


def test_no_welcome_after_a_short_break():
    c = Clock()
    c.run(1 * MIN)
    c.run(4 * MIN, user_idle=4 * MIN)
    c.fired.clear()
    assert "welcome" not in c.run(30, user_idle=0.5)


@pytest.mark.parametrize(
    "blocker",
    [{"in_call": True}, {"quiet": True}, {"enabled": False}, {"category": Category.CALL}],
)
def test_never_during_calls_quiet_mode_or_when_turned_off(blocker):
    c = Clock(CheerTuning(random_every=1.0))
    assert c.run(60 * MIN, **blocker) == []


def test_a_sleeping_pet_only_wakes_for_a_welcome():
    c = Clock(CheerTuning(random_every=1.0))
    assert c.run(30 * MIN, pet_asleep=True) == []
    c.run(11 * MIN, user_idle=11 * MIN, pet_asleep=True)
    assert c.run(10, user_idle=0.5, pet_asleep=True) == ["welcome"]


def test_a_blocked_focus_cheer_isnt_used_up():
    c = Clock()
    c.run(21 * MIN, pet_asleep=True)  # streak passes 20 min while the pet naps
    assert c.run(5, pet_asleep=False) == ["focus"]


def test_demo_mode_divides_every_interval():
    demo = CheerTuning().scaled(30)
    assert demo.min_gap == 30 and demo.focus_after == 40 and demo.away_after == 20
    # "Actively working" and "gone" mean the same thing in a demo.
    base = CheerTuning()
    assert (demo.welcome_delay, demo.active_within, demo.gone_after) == (base.welcome_delay, base.active_within, base.gone_after)
    c = Clock(CheerTuning(random_every=1e12).scaled(30))
    assert c.run(45, step=0.25, user_idle=8.0) == ["focus"]  # typing with pauses still counts
