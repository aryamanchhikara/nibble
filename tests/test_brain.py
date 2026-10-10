import random

from conftest import APP_PID, PET_H, PET_W, snap, win

from nibble.core.brain import Activity, Brain, Tuning
from nibble.core.context import Context
from nibble.core.energy import BRAIN, Energy
from nibble.core.geometry import window_key
from nibble.core.physics import LANDED, Body, Mode
from nibble.core.world import WorldView

DT = 1 / 60


class Sim:
    """Drives a brain and body together over a sequence of snapshots."""

    def __init__(self, snapshot, x, tuning=None, peek_tuning=None):
        self.brain = Brain(random.Random(7), tuning, peek_tuning)
        self.body = Body(pet_w=PET_W, pet_h=PET_H)
        self.now = 0.0
        self.ctx = Context()
        self.said = []
        self.set(snapshot)
        self.body.drop_in(x, 900)
        self.run(3.0, until=LANDED)

    def set(self, snapshot):
        self.world = WorldView(snapshot, PET_W, PET_H)

    def run(self, seconds, until=None):
        for _ in range(int(seconds / DT)):
            self.now += DT
            self.brain.update(self.now, self.body, self.world, self.ctx)
            self.said += self.brain.drain_speech()
            events = self.body.step(DT, self.world.surfaces)
            if until and until in events:
                return True
        return False


def test_follows_focus_to_another_window():
    a, b = win(1, 100, 200, 500, 300), win(2, 800, 100, 600, 300)
    sim = Sim(snap(a, b), 300)
    assert sim.body.support == window_key(1)

    sim.set(snap(b, a))  # b comes to the front
    assert sim.run(3.0, until=LANDED)
    assert sim.body.support == window_key(2)


def test_waits_a_moment_before_one_calm_hop():
    a, b = win(1, 100, 200, 500, 300), win(2, 800, 100, 600, 300)
    sim = Sim(snap(a, b), 300)
    sim.set(snap(b, a))
    sim.run(1.1)
    assert sim.body.mode is Mode.STANDING  # still thinking about it
    sim.run(1.2)
    assert sim.body.mode is Mode.HOPPING
    assert sim.body.hop.duration >= 0.3 * Tuning().hop_pace  # unhurried


def test_flicking_between_windows_doesnt_send_it_bouncing():
    a, b = win(1, 100, 200, 500, 300), win(2, 800, 100, 600, 300)
    sim = Sim(snap(a, b), 300)
    for _ in range(6):  # alt-tabbing back and forth faster than it reacts
        sim.set(snap(b, a))
        sim.run(0.5)
        sim.set(snap(a, b))
        sim.run(0.5)
    assert sim.body.mode is Mode.STANDING and sim.body.support == window_key(1)


def test_peeks_instead_of_going_to_the_floor_when_the_window_has_no_headroom():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a), 300)
    tiled_left = win(2, 0, 0, 700, 949)  # reaches the menu bar, doesn't fill the display
    sim.set(snap(tiled_left, a))
    sim.run(6.0)
    assert sim.body.mode is Mode.PEEKING
    assert (sim.body.peek.side, sim.body.peek.edge_x, sim.body.peek.window_id) == (-1, 0, 2)


def test_peeks_when_the_focused_window_fills_the_display():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a), 300)
    maximized = win(2, 0, 0, 1512, 949)
    sim.set(snap(maximized, a))
    sim.run(3.0)
    assert sim.body.mode is Mode.PEEKING


def test_stays_where_dropped_until_focus_changes():
    a, b = win(1, 100, 200, 500, 300), win(2, 800, 100, 600, 300)
    sim = Sim(snap(a, b), 300)
    # The user carries the pet over to b and lets go, while a is still focused.
    sim.body.grab()
    sim.body.hold_at(1000, 600)
    sim.body.release()
    sim.brain.on_dropped(sim.world, sim.now)
    sim.run(3.0, until=LANDED)
    assert sim.body.support == window_key(2)
    sim.run(3.0)
    assert sim.body.support == window_key(2)  # didn't hop back to a

    c = win(3, 300, 500, 400, 200)
    sim.set(snap(c, a, b))  # focus moves to a new window
    sim.run(3.0, until=LANDED)
    assert sim.body.support == window_key(3)


def test_wandering_never_leaves_the_ledge():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a), 300, tuning=BRAIN[Energy.HYPER])
    lo, hi = 100 + sim.body.edge_inset, 600 - sim.body.edge_inset
    walked = False
    for _ in range(60):
        sim.run(1.0)
        walked |= sim.body.distance_walked > 0
        assert sim.body.support == window_key(1)
        assert lo <= sim.body.x <= hi
    assert walked


def test_stays_put_when_nothing_is_focused():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a), 300)
    sim.set(snap(a, front=None))
    sim.run(2.0)
    assert sim.body.support == window_key(1)


def test_poses():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a, front=APP_PID), 300)
    assert sim.brain.pose(sim.now, sim.body)[0] in {"idle", "sit", "walk"}
    sim.body.grab()
    assert sim.brain.pose(sim.now, sim.body)[0] == "dangle"
    sim.body.release()
    assert sim.brain.pose(sim.now, sim.body)[0] == "fall"


# ---- sleep ------------------------------------------------------------------


def idle_ctx(seconds, cursor=(-1e9, -1e9)):
    return Context(user_idle=seconds, cursor=cursor)


def test_naps_while_you_are_away_and_wakes_when_the_cursor_comes_near():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.ctx = idle_ctx(200)
    sim.run(1.0)
    assert sim.brain.asleep
    assert sim.brain.pose(sim.now, sim.body)[0] == "sleep"

    sim.ctx = idle_ctx(0.2)  # back, but not near the pet: keeps napping for now
    sim.run(5.0)
    assert sim.brain.asleep
    sim.ctx = idle_ctx(0.2, cursor=(sim.body.x + 40, sim.body.y + 30))
    sim.run(0.2)
    assert not sim.brain.asleep


def test_wakes_on_its_own_once_you_have_been_back_a_while():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300, tuning=Tuning(wake_after_active=3.0))
    sim.ctx = idle_ctx(200)
    sim.run(1.0)
    sim.ctx = idle_ctx(0.2)
    sim.run(4.0)
    assert not sim.brain.asleep


def test_clicking_a_sleeping_pet_wakes_it_without_a_quip():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.ctx = idle_ctx(200)
    sim.run(1.0)
    sim.brain.on_clicked(sim.now)
    assert sim.brain.activity is Activity.WAKE
    assert sim.brain.drain_speech() == []


def test_click_says_a_quip():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.brain.on_clicked(sim.now)
    assert [s.kind for s in sim.brain.drain_speech()] == ["quip"]


# ---- cheering -------------------------------------------------------------


def test_cheer_hops_happily_and_speaks():
    a = win(1, 100, 200, 500, 300)
    sim = Sim(snap(a), 300)
    sim.brain.cheer(sim.now, "you got this!")
    sim.run(0.1)
    assert sim.body.mode is Mode.HOPPING
    assert sim.brain.pose(sim.now, sim.body)[0] == "happy"
    assert ("cheer", "you got this!") in [tuple(s) for s in sim.said]
    sim.run(2.0)
    assert sim.body.support == window_key(1)


def test_welcome_back_cheer_wakes_the_pet():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.ctx = idle_ctx(900)
    sim.run(1.0)
    assert sim.brain.asleep
    sim.ctx = idle_ctx(0.5)
    sim.brain.cheer(sim.now, "welcome back!")
    sim.run(0.5)
    assert not sim.brain.asleep
    assert any(s.kind == "cheer" for s in sim.said)


def test_undeliverable_cheer_expires():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.body.grab()
    sim.brain.cheer(sim.now, "go go go")
    sim.run(11.0)  # held the whole time
    sim.body.release()
    sim.run(3.0)
    assert not any(s.kind == "cheer" for s in sim.said)


def test_sits_still_during_calls():
    sim = Sim(snap(win(1, 100, 200, 500, 300)), 300)
    sim.ctx = Context(in_call=True)
    sim.run(0.5)
    x = sim.body.x
    sim.run(20.0)
    assert sim.body.x == x
    assert sim.brain.pose(sim.now, sim.body)[0] == "sit"
