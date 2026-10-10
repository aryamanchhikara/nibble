from conftest import DOCKED, LAPTOP, MONITOR, OWN_PID, PET_H, PET_W, win

from nibble.core.geometry import (
    Rect,
    Segment,
    SurfaceMap,
    floor_key,
    flip_rect,
    is_fullscreen,
    pick_active_window,
    subtract_intervals,
    top_edge_segments,
    window_key,
)


def segments(window, in_front=(), displays=(LAPTOP,)):
    return top_edge_segments(window, in_front, displays, PET_W, PET_H, OWN_PID)


# ---- coordinate flipping -------------------------------------------------


def test_flip_converts_quartz_to_cocoa():
    # 50pt below the top of a 982pt-tall primary display, 200pt tall.
    assert flip_rect(Rect(100, 50, 300, 200), 982) == Rect(100, 732, 300, 200)


def test_flip_is_its_own_inverse():
    r = Rect(-40, 123.5, 640, 480)
    assert flip_rect(flip_rect(r, 982), 982) == r


def test_flip_handles_display_above_primary():
    # Quartz puts a display stacked above the primary at negative y.
    assert flip_rect(Rect(-266, -1080, 1920, 1080), 982) == MONITOR.frame


# ---- standable edges -----------------------------------------------------


def test_whole_top_edge_is_standable_when_unobstructed():
    assert segments(win(1, 100, 200, 600, 400)) == [Segment(100, 700)]


def test_window_under_menu_bar_has_no_headroom():
    # Maximized: top edge is the bottom of the menu bar.
    assert segments(win(1, 0, 0, 1512, 949)) == []
    # Close to the menu bar but with less room than the pet is tall.
    assert segments(win(1, 100, 200, 600, 949 - 200 - 40)) == []
    # Exactly enough room.
    assert segments(win(1, 100, 200, 600, 949 - 200 - PET_H)) == [Segment(100, 700)]


def test_window_in_front_cuts_the_edge():
    back = win(1, 100, 200, 600, 400)  # top at 600
    front = win(2, 300, 500, 200, 300)  # spans y 500..800 over x 300..500
    assert segments(back, [front]) == [Segment(100, 300), Segment(500, 700)]


def test_windows_that_dont_cross_the_edge_dont_cut_it():
    back = win(1, 100, 200, 600, 400)  # top at 600
    floating_above = win(2, 300, 620, 200, 100)
    tucked_below = win(3, 300, 300, 200, 250)  # top at 550
    assert segments(back, [floating_above, tucked_below]) == [Segment(100, 700)]


def test_system_chrome_and_our_own_windows_dont_cut_edges():
    back = win(1, 100, 200, 600, 400)
    dock = win(2, 0, 0, 1512, 982, layer=20, owner="Dock")
    ours = win(3, 300, 500, 200, 300, pid=OWN_PID)
    assert segments(back, [dock, ours]) == [Segment(100, 700)]


def test_slivers_too_narrow_for_the_pet_are_dropped():
    back = win(1, 100, 200, 600, 400)
    front = win(2, 120, 500, 560, 300)  # leaves 20pt on the left and right
    assert segments(back, [front]) == []


def test_edge_is_clipped_to_the_display():
    hanging_off_left = win(1, -200, 200, 600, 300)
    assert segments(hanging_off_left) == [Segment(0, 400)]


def test_edge_on_the_upper_monitor():
    w = win(1, 0, 1200, 800, 500)  # top at 1700, on the monitor
    assert segments(w, displays=(LAPTOP, MONITOR)) == [Segment(0, 800)]


def test_subtract_intervals_merges_and_splits():
    assert subtract_intervals([(0, 10), (5, 20)], [(3, 4), (15, 30)]) == [(0, 3), (4, 15)]


# ---- active window -------------------------------------------------------


def test_active_window_is_frontmost_regular_window_of_frontmost_app():
    windows = [
        win(9, 0, 900, 30, 20),  # tiny (a tooltip or palette)
        win(8, 0, 0, 500, 500, layer=3),  # floating panel
        win(7, 0, 0, 500, 500, pid=OWN_PID),
        win(6, 0, 0, 500, 500, pid=200),  # another app
        win(5, 0, 0, 500, 500),
        win(4, 0, 0, 500, 500),
    ]
    assert pick_active_window(windows, 100, OWN_PID).id == 5
    assert pick_active_window(windows, None, OWN_PID) is None


def test_fullscreen_detection():
    assert is_fullscreen(win(1, 0, 0, 1512, 982), [LAPTOP])
    assert not is_fullscreen(win(1, 0, 0, 1512, 949), [LAPTOP])


# ---- surface map ---------------------------------------------------------


def surface_map(*windows, displays=(LAPTOP,)):
    return SurfaceMap(displays, windows, OWN_PID, PET_W, PET_H)


def test_landing_picks_the_highest_surface_crossed():
    upper = win(1, 100, 300, 600, 300)  # top 600
    lower = win(2, 0, 100, 800, 200)  # top 300
    s = surface_map(upper, lower)
    assert s.landing(400, 700, 0) == (window_key(1), 600)
    assert s.landing(400, 550, 0) == (window_key(2), 300)
    assert s.landing(750, 700, 0) == (window_key(2), 300)  # misses the upper window


def test_landing_skips_hidden_parts_of_an_edge():
    front = win(1, 300, 500, 200, 300)  # covers x 300..500 of the back window's edge
    back = win(2, 100, 200, 600, 400)
    s = surface_map(front, back)
    # Falling past the back window's edge where it's covered: no landing there.
    assert s.landing(400, 610, 590) is None
    assert s.landing(200, 610, 590) == (window_key(2), 600)


def test_floor_sits_on_top_of_the_dock():
    s = surface_map(displays=(DOCKED,))
    assert s.y(floor_key(3)) == 70
    assert s.landing(500, 100, 0) == (floor_key(3), 70)


def test_nearest_floor_rescues_a_pet_outside_every_display():
    s = surface_map(displays=(LAPTOP, MONITOR))
    key, x, y = s.nearest_floor(1700, 500)  # right of the laptop, below the monitor
    assert key == floor_key(1) and y == 0 and x <= 1512


def test_vanished_window_has_no_surface():
    s = surface_map(win(1, 100, 200, 600, 400))
    assert s.segments(window_key(99)) == []
    assert s.y(window_key(99)) is None
