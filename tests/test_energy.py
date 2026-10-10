"""Energy presets: Chill mostly hangs out; chasing needs a deliberate hover."""

import random

import pytest
from conftest import PET_H, PET_W, snap, win

from nibble.core import settings
from nibble.core.brain import Activity, Brain
from nibble.core.context import Context
from nibble.core.energy import BRAIN, DEFAULT, DEMO_BRAIN, DEMO_PEEK, PEEK, Energy, parse, profiles
from nibble.core.physics import LANDED, Body, Mode
from nibble.core.world import WorldView

WIDE = win(1, 50, 150, 1400, 500)


def live(energy: Energy, minutes: float, seed: int = 5, dt: float = 0.1):
    """Let a pet hang out on a wide window while you work; report how much it moved."""
    brain = Brain(random.Random(seed), BRAIN[energy], PEEK[energy])
    body = Body(pet_w=PET_W, pet_h=PET_H)
    world = WorldView(snap(WIDE), PET_W, PET_H)
    body.drop_in(700, 800)
    ctx = Context(user_idle=1.0)  # you're at the keyboard; the cursor is elsewhere
    now, walks, naps, last = 0.0, 0, 0, Activity.IDLE
    for _ in range(int(minutes * 60 / dt)):
        now += dt
        brain.update(now, body, world, ctx)
        body.step(dt, world.surfaces)
        if brain.activity is not last:
            walks += brain.activity is Activity.WALK
            naps += brain.activity is Activity.SLEEP
            last = brain.activity
    return walks, naps, body.distance_walked


def test_chill_is_the_default():
    assert DEFAULT is Energy.CHILL and parse(None) is Energy.CHILL and parse("bogus") is Energy.CHILL


def test_chill_mostly_hangs_out():
    walks, naps, distance = live(Energy.CHILL, 30)
    assert walks <= 12  # at most one every ~2.5 minutes
    assert distance < 1500  # short walks
    assert naps >= 1


def test_more_energy_means_more_moving():
    chill = live(Energy.CHILL, 20)[2]
    normal = live(Energy.NORMAL, 20)[2]
    hyper = live(Energy.HYPER, 20)[2]
    assert chill * 3 < normal < hyper


def test_chill_walks_slowly_and_follows_you_unhurried():
    chill, hyper = BRAIN[Energy.CHILL], BRAIN[Energy.HYPER]
    assert chill.walk_speed < 30 and chill.walk_distance[1] <= 120
    assert chill.reaction_delay[0] >= 1.0 and chill.hop_pace > 1.5
    assert hyper.reaction_delay[1] < chill.reaction_delay[0]


def test_demo_mode_ignores_energy():
    for energy in Energy:
        assert profiles(energy, demo=True) == (DEMO_BRAIN, DEMO_PEEK)
    assert profiles(Energy.NORMAL) == (BRAIN[Energy.NORMAL], PEEK[Energy.NORMAL])


def test_energy_setting_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path).energy == "chill"
    settings.save(path, settings.Settings(energy="hyper"))
    assert settings.load(path).energy == "hyper"
    path.write_text('{"energy": "turbo"}')
    assert settings.load(path).energy == "chill"


# ---- cursor chasing ---------------------------------------------------------


class Chase:
    def __init__(self, energy=Energy.CHILL):
        self.t = BRAIN[energy]
        self.brain = Brain(random.Random(1), self.t, PEEK[energy])
        self.body = Body(pet_w=PET_W, pet_h=PET_H)
        self.world = WorldView(snap(WIDE), PET_W, PET_H)
        self.body.drop_in(700, 800)
        self.now = 0.0
        self.said = []
        self.run(3.0, Context(user_idle=1.0))
        assert self.body.mode is Mode.STANDING

    def run(self, seconds, ctx, dt=1 / 30):
        for _ in range(int(round(seconds / dt))):
            self.now += dt
            self.brain.update(self.now, self.body, self.world, ctx)
            self.said += self.brain.drain_speech()
            self.body.step(dt, self.world.surfaces)

    def hover(self, dx=70):
        return Context(cursor=(self.body.x + dx, self.body.y + 40), user_idle=0.1)


def test_a_passing_cursor_doesnt_start_a_chase():
    c = Chase()
    c.run(c.t.chase_hover * 0.7, c.hover())
    assert c.brain.activity is not Activity.CHASE


def test_a_deliberate_hover_starts_a_chase_and_it_gives_up_soon():
    c = Chase()
    c.run(c.t.chase_hover + 0.3, c.hover())
    assert c.brain.activity is Activity.CHASE
    start = c.body.x
    c.run(0.5, c.hover(dx=80))
    assert c.body.x > start  # heading for the cursor
    c.run(c.t.chase_for, c.hover(dx=80))
    assert c.brain.activity is not Activity.CHASE  # lost interest
    assert c.body.walk_target is None


def test_after_giving_up_it_ignores_the_cursor_for_a_while():
    c = Chase()
    c.run(c.t.chase_hover + c.t.chase_for + 1.0, c.hover())
    c.run(c.t.bored_for * 0.5, c.hover(dx=-70))
    assert c.brain.activity is not Activity.CHASE


@pytest.mark.parametrize("energy", list(Energy))
def test_every_energy_gives_up_eventually(energy):
    c = Chase(energy)
    c.run(c.t.chase_hover + c.t.chase_for + 0.5, c.hover())
    assert c.brain.activity is not Activity.CHASE


def test_chase_never_starts_while_a_mouse_button_is_held():
    c = Chase()
    ctx = Context(cursor=(c.body.x + 70, c.body.y + 40), mouse_down=True)
    c.run(c.t.chase_hover * 3, ctx)
    assert c.brain.activity is not Activity.CHASE
