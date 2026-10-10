"""Where can the pet be? Stand on the focused window, or peek from its outer side."""

import pytest
from conftest import LAPTOP, MONITOR, PET_H, PET_W, snap, win
from test_brain import Sim

from nibble.core.geometry import Display, Rect, window_key
from nibble.core.physics import LANDED, Mode
from nibble.core.world import TOUCHING, WorldView

V = LAPTOP.visible  # x 0..1512, y 0..949 (menu bar above)
MID = V.right / 2


def home(*windows, displays=(LAPTOP,)):
    return WorldView(snap(*windows, displays=displays), PET_W, PET_H).home()


def sides(h):
    return [(e.side, e.x) for e in h.peek]


# ---- the rule, case by case ----------------------------------------------------


def test_normal_window_with_room_above_stands_on_its_top_edge():
    h = home(win(1, 200, 150, 700, 500))
    assert h.stand == window_key(1) and h.peek == ()


def test_window_tiled_to_the_bottom_half_still_has_room_to_stand():
    h = home(win(1, 0, 0, V.w, V.h / 2))
    assert h.stand == window_key(1)


def test_maximized_window_peeks_from_either_screen_edge():
    h = home(win(1, 0, 0, V.w, V.h))
    assert h.stand is None
    assert sides(h) == [(-1, 0), (1, V.right)]  # left first: scrollbars live on the right


def test_fullscreen_window_peeks_from_either_screen_edge():
    h = home(win(1, 0, 0, LAPTOP.frame.w, LAPTOP.frame.h))
    assert sides(h) == [(-1, 0), (1, V.right)]


def test_split_view_left_half_peeks_from_the_left_screen_edge_only():
    left, right = win(1, 0, 0, MID, V.h), win(2, MID, 0, MID, V.h)
    assert sides(home(left, right)) == [(-1, 0)]


def test_split_view_right_half_peeks_from_the_right_screen_edge_only():
    left, right = win(1, 0, 0, MID, V.h), win(2, MID, 0, MID, V.h)
    assert sides(home(right, left)) == [(1, V.right)]


def test_never_peeks_from_the_divider():
    # Split View leaves a divider between the halves.
    left, right = win(1, 0, 0, MID - 4, V.h), win(2, MID + 4, 0, MID - 4, V.h)
    for focused, other in ((left, right), (right, left)):
        for e in home(focused, other).peek:
            assert abs(e.x - MID) > 100


def test_tiled_windows_with_margins_count_as_touching_the_edge():
    gap = 8  # macOS "tiled windows have margins"
    left = win(1, gap, gap, MID - 1.5 * gap, V.h - 2 * gap)
    right = win(2, MID + gap / 2, gap, MID - 1.5 * gap, V.h - 2 * gap)
    assert sides(home(left, right)) == [(-1, gap)]
    assert sides(home(right, left)) == [(1, V.right - gap)]


def test_tiled_top_quadrants_peek_from_their_outer_side():
    top_left = win(1, 0, V.h / 2, MID, V.h / 2)
    top_right = win(2, MID, V.h / 2, MID, V.h / 2)
    assert sides(home(top_left, top_right)) == [(-1, 0)]
    assert sides(home(top_right, top_left)) == [(1, V.right)]


def test_peek_height_stays_within_the_window():
    top_left = win(1, 0, V.h / 2, MID, V.h / 2)
    (edge,) = home(top_left).peek
    assert V.h / 2 < edge.y_lo < edge.y_hi < V.h
    # The middle half of the window: clear of its title bar and bottom edge.
    assert edge.y_lo == pytest.approx(V.h / 2 + V.h / 8)
    assert edge.y_hi == pytest.approx(V.h - V.h / 8)


def test_window_against_the_menu_bar_touching_neither_side_uses_the_nearer_side():
    centered_tall = win(1, 300, 0, 600, V.h)  # 300 from the left, 612 from the right
    assert sides(home(centered_tall)) == [(-1, 300)]


def test_touching_threshold():
    just_inside = win(1, TOUCHING, 0, MID, V.h)
    assert sides(home(just_inside)) == [(-1, TOUCHING)]


def test_dock_on_the_left_counts_as_the_screen_edge():
    docked = Display(4, frame=Rect(0, 0, 1440, 900), visible=Rect(64, 0, 1376, 875))
    tiled = win(1, 64, 0, 688, 875)
    assert sides(home(tiled, displays=(docked,))) == [(-1, 64)]


def test_maximized_on_the_upper_monitor_peeks_on_that_monitor():
    f = MONITOR.frame
    h = home(win(1, f.x, f.y, f.w, f.h), displays=(LAPTOP, MONITOR))
    assert sides(h) == [(-1, f.left), (1, f.right)]
    assert all(e.display_id == MONITOR.id and f.bottom < e.y_lo < e.y_hi < f.top for e in h.peek)


def test_nothing_focused():
    assert home(win(1, 200, 150, 700, 500), displays=(LAPTOP,)) is not None
    assert WorldView(snap(win(1, 200, 150, 700, 500), front=None), PET_W, PET_H).home() is None
    world = WorldView(snap(front=None), PET_W, PET_H)
    assert sides(world.screen_home(LAPTOP)) == [(-1, 0), (1, LAPTOP.frame.right)]


# ---- the pet actually goes there ---------------------------------------------


NORMAL = win(9, 300, 150, 500, 400)


def test_split_view_switching_halves_moves_the_peek_to_the_other_outer_side():
    left, right = win(1, 0, 0, MID - 4, V.h), win(2, MID + 4, 0, MID - 4, V.h)
    sim = Sim(snap(NORMAL), 400)
    sim.set(snap(left, right))
    sim.run(6.0)
    p = sim.body.peek
    assert sim.body.mode is Mode.PEEKING and (p.side, p.edge_x, p.window_id) == (-1, 0, 1)

    sim.set(snap(right, left))
    xs = []
    for _ in range(80):
        sim.run(0.1)
        if sim.body.peek and sim.body.peek.depth > 0:
            xs.append(sim.body.x)
    p = sim.body.peek
    assert (p.side, p.edge_x, p.window_id) == (1, V.right, 2)
    assert all(abs(x - MID) > 100 for x in xs)  # never seen near the divider


def test_maximizing_peeks_and_restoring_stands_again():
    sim = Sim(snap(NORMAL), 400)
    maxed = win(9, 0, 0, V.w, V.h)  # same window, maximized
    sim.set(snap(maxed))
    sim.run(6.0)
    assert sim.body.mode is Mode.PEEKING and sim.body.peek.window_id == 9
    sim.set(snap(NORMAL))
    assert sim.run(8.0, until=LANDED)
    assert sim.body.support == window_key(9)


def test_peek_rides_along_when_the_tiled_window_moves():
    tile = win(1, 0, V.h / 2, MID, V.h / 2)
    sim = Sim(snap(NORMAL), 400)
    sim.set(snap(tile, NORMAL))
    sim.run(6.0)
    tall_left = win(1, 0, 0, MID, V.h)  # stretched to the full height on the left
    sim.set(snap(tall_left, NORMAL))
    sim.run(1.0)
    e = WorldView(snap(tall_left, NORMAL), PET_W, PET_H).home().peek[0]
    assert sim.body.mode is Mode.PEEKING and sim.body.peek.window_id == 1
    assert e.y_lo <= sim.body.peek.y <= e.y_hi


def test_never_settles_on_the_floor_by_itself():
    sim = Sim(snap(NORMAL), 400)
    sim.set(snap(front=None))  # its window closes and nothing else is focused
    sim.run(3.0, until=LANDED)
    assert sim.body.support[0] == "floor"  # it fell...
    sim.run(6.0)
    assert sim.body.mode is Mode.PEEKING and sim.body.peek.window_id is None  # ...then went to the edge


def test_no_headroom_never_means_the_floor():
    tall = win(1, 300, 0, 600, V.h)
    sim = Sim(snap(NORMAL), 400)
    sim.set(snap(tall, NORMAL))
    for _ in range(60):
        sim.run(0.1)
        assert not (sim.body.mode is Mode.STANDING and sim.body.support[0] == "floor")
    assert sim.body.mode is Mode.PEEKING
