from conftest import LAPTOP, PET_H, PET_W, snap, win
from test_brain import Sim

from nibble.core.context import Context
from nibble.core.geometry import window_key
from nibble.core.peek import DUCK, LOOK, POP, REST, PeekTuning, clip, layout, orient, rotate_ccw, rotate_cw
from nibble.core.physics import LANDED, Mode, Peek
from nibble.core.spec import STANDING, load_builtin
from nibble.core.sprites import TRANSPARENT, bbox

# A 4x4 frame with a single pixel in the top-left corner.
CORNER = ("1...", "....", "....", "....")


# ---- frames ---------------------------------------------------------------


def test_rotations():
    assert rotate_cw(CORNER) == ("...1", "....", "....", "....")  # top-left -> top-right
    assert rotate_ccw(CORNER) == ("....", "....", "....", "1...")  # top-left -> bottom-left
    assert rotate_ccw(rotate_cw(CORNER)) == CORNER


def test_lying_down_the_head_points_into_the_screen():
    pip = load_builtin("pip")
    upright = bbox([pip.frame("idle", 0)])
    for side in (1, -1):
        for look in (1, -1):
            turned = orient(pip.frame("idle", 0), side, upright=False, look=look)
            box = bbox([turned])
            assert box.width == upright.height  # lying sideways
            # The top of its head is the end farthest from the edge it hides behind:
            # the left end when peeking from the right edge, and vice versa.
            if side > 0:
                assert box.left == upright.top
            else:
                assert box.right == len(turned) - 1 - upright.top


def test_clip_shows_only_what_pokes_in_and_aligns_it_to_the_edge():
    pip = load_builtin("pip")
    standing = [f for n in STANDING for f in pip.frames[n]]
    for side in (1, -1):
        lay = layout(standing, side, upright=False, look=1, scale=3)
        frame = orient(pip.frame("idle", 0), side, upright=False, look=1)
        clipped, anchor = clip(frame, side, lay.ref, 10)
        cols = sorted({c for row in clipped for c, ch in enumerate(row) if ch != TRANSPARENT})
        assert len(cols) <= 10
        # Every visible column is on the screen side of the edge boundary.
        assert all(c < anchor for c in cols) if side > 0 else all(c >= anchor for c in cols)

        peek = Peek(display_id=1, side=side, edge_x=1512 if side > 0 else 0, y=500, depth=30)
        ox, _ = lay.origin(peek, anchor)
        xs = [ox + c * 3 for c in cols]
        if side > 0:
            assert max(xs) + 3 <= 1512 and min(xs) >= 1512 - 30
        else:
            assert min(xs) >= 0 and max(xs) + 3 <= 30


def test_nothing_shows_at_depth_zero():
    pip = load_builtin("pip")
    lay = layout([pip.frame("idle", 0)], 1, False, 1, 3)
    clipped, _ = clip(orient(pip.frame("idle", 0), 1, False, 1), 1, lay.ref, 0)
    assert all(set(row) == {TRANSPARENT} for row in clipped)


# ---- behaviour ------------------------------------------------------------

FAST = PeekTuning(look_every=(1000.0, 1000.0))  # no spontaneous look-arounds in tests
MAXIMIZED = win(9, 0, 0, 1512, 949)
NORMAL = win(1, 100, 200, 500, 300)


def peeking_sim(tuning=FAST):
    sim = Sim(snap(NORMAL), 300, peek_tuning=tuning)
    sim.set(snap(MAXIMIZED, NORMAL))
    sim.run(4.0)
    assert sim.body.mode is Mode.PEEKING
    return sim


def head(sim):
    return sim.body.x, sim.body.y


def toward_face(sim, distance):
    """A cursor point in front of the pet's face."""
    p = sim.body.peek
    return (sim.body.x - p.side * distance, sim.body.y)


def test_settles_mostly_hidden_with_its_head_poking_in():
    sim = peeking_sim()
    p = sim.body.peek
    assert sim.brain.peek.phase == REST and not p.upright
    assert abs(p.depth - PET_H * FAST.rest) < 1
    assert p.edge_x in (LAPTOP.frame.left, LAPTOP.frame.right)
    v = LAPTOP.visible
    assert v.bottom + 0.2 * v.h <= p.y <= v.bottom + 0.8 * v.h  # away from tabs and the Dock


def test_pops_in_when_the_cursor_lingers_then_retreats():
    sim = peeking_sim()
    sim.ctx = Context(cursor=toward_face(sim, 60))
    sim.run(FAST.pop_hover * 0.8)
    assert sim.brain.peek.phase == REST  # a passing cursor isn't enough
    sim.run(0.6)
    assert sim.brain.peek.phase == POP
    assert sim.body.peek.depth == PET_H
    assert sim.brain.pose(sim.now, sim.body)[0] == "happy"

    sim.ctx = Context(cursor=(LAPTOP.frame.center[0], LAPTOP.frame.center[1]))
    sim.run(1.0)
    assert sim.brain.peek.phase == REST
    assert abs(sim.body.peek.depth - PET_H * FAST.rest) < 1


def test_never_camps_in_view():
    sim = peeking_sim()
    sim.ctx = Context(cursor=toward_face(sim, 60))
    sim.run(FAST.pop_hover + FAST.pop_max + 1.5)
    assert sim.brain.peek.phase == REST


def test_ignores_a_cursor_in_the_scrollbar_strip():
    sim = peeking_sim()
    p = sim.body.peek
    sim.ctx = Context(cursor=(p.edge_x - p.side * 8, p.y + 30))
    sim.run(0.5)
    assert sim.brain.peek.phase == REST


def test_ducks_out_of_the_way_of_a_nearby_click():
    sim = peeking_sim()
    p = sim.body.peek
    sim.ctx = Context(cursor=(p.edge_x - p.side * 8, p.y + 60), mouse_down=True)
    sim.run(0.5)
    assert sim.brain.peek.phase == DUCK and p.depth == 0
    sim.ctx = Context()
    sim.run(FAST.duck_for + 2.0)
    assert sim.brain.peek.phase == REST


def test_looks_around_and_sometimes_says_something():
    sim = peeking_sim(PeekTuning(look_every=(0.5, 0.5), quip_chance=1.0, move_chance=0.0))
    looks = set()
    for _ in range(40):
        sim.run(0.1)
        if sim.brain.peek.phase == LOOK:
            looks.add(sim.body.peek.look)
    assert looks == {1, -1}  # turned its head both ways
    assert any(s.kind == "quip" for s in sim.said)


def test_cheers_from_the_edge():
    sim = peeking_sim()
    sim.brain.cheer(sim.now, "you got this!")
    sim.run(1.0)
    assert ("cheer", "you got this!") in [tuple(s) for s in sim.said]
    assert sim.body.peek.depth > PET_H * FAST.rest


def test_goes_back_to_the_window_edge_when_you_leave_fullscreen():
    sim = peeking_sim()
    sim.set(snap(NORMAL, MAXIMIZED))
    assert sim.run(5.0, until=LANDED)
    assert sim.body.mode is Mode.STANDING and sim.body.support == window_key(1)


def test_stays_where_you_drop_it_until_focus_changes():
    sim = peeking_sim()
    sim.body.grab()
    sim.body.hold_at(700, 500)
    sim.body.release()
    sim.brain.on_dropped(sim.world, sim.now)
    sim.run(10.0)
    assert sim.body.mode is Mode.STANDING and sim.body.support[0] == "floor"  # you put it there

    other = win(3, 0, 0, 1512, 949)  # focus a different maximized window
    sim.set(snap(other, MAXIMIZED, NORMAL))
    sim.run(6.0)
    assert sim.body.mode is Mode.PEEKING
