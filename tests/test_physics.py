from conftest import LAPTOP, MONITOR, OWN_PID, PET_H, PET_W, win

from nibble.core.geometry import SurfaceMap, floor_key, window_key
from nibble.core.physics import ARRIVED, COVERED, LANDED, LOST_SUPPORT, Body, Mode

DT = 1 / 60


def surfaces(*windows, displays=(LAPTOP,)):
    return SurfaceMap(displays, windows, OWN_PID, PET_W, PET_H)


def standing_on(window, x, s):
    body = Body(pet_w=PET_W, pet_h=PET_H)
    body.drop_in(x, window.bounds.top + 1)
    run(body, s, 0.2)
    assert body.mode is Mode.STANDING and body.support == window_key(window.id)
    return body


def run(body, s, seconds, until=None):
    events = []
    for _ in range(int(seconds / DT)):
        events += body.step(DT, s)
        if until and until in events:
            break
    return events


def test_rides_along_when_the_window_moves():
    w = win(1, 100, 200, 600, 400)
    body = standing_on(w, 400, surfaces(w))
    moved = win(1, 250, 150, 600, 400)
    body.step(DT, surfaces(moved))
    assert body.x == 550 and body.y == moved.bounds.top


def test_falls_when_the_window_closes_and_lands_on_the_one_below():
    top = win(1, 100, 400, 600, 300)
    below = win(2, 0, 100, 900, 200)
    body = standing_on(top, 400, surfaces(top, below))
    events = run(body, surfaces(below), 2.0, until=LANDED)
    assert LOST_SUPPORT in events and LANDED in events
    assert body.support == window_key(2) and body.y == below.bounds.top


def test_lands_on_the_floor_when_nothing_is_below():
    w = win(1, 100, 400, 600, 300)
    body = standing_on(w, 400, surfaces(w))
    run(body, surfaces(), 3.0, until=LANDED)
    assert body.support == floor_key(LAPTOP.id) and body.y == 0


def test_hop_lands_on_target_even_if_it_moves_midair():
    a = win(1, 100, 200, 400, 300)
    b = win(2, 800, 300, 500, 300)
    s = surfaces(a, b)
    body = standing_on(a, 300, s)
    assert body.hop_to(window_key(2), 900, s)
    run(body, s, 0.15)
    b_moved = win(2, 850, 350, 500, 300)
    run(body, surfaces(a, b_moved), 2.0, until=LANDED)
    assert body.support == window_key(2)
    assert body.x == 950 and body.y == b_moved.bounds.top


def test_hop_turns_into_a_fall_if_the_target_closes():
    a = win(1, 100, 200, 400, 300)
    b = win(2, 800, 300, 500, 300)
    s = surfaces(a, b)
    body = standing_on(a, 300, s)
    body.hop_to(window_key(2), 900, s)
    run(body, s, 0.1)
    body.step(DT, surfaces(a))
    assert body.mode is Mode.FALLING
    run(body, surfaces(a), 3.0, until=LANDED)
    assert body.grounded


def test_walking_stops_at_the_end_of_the_ledge():
    w = win(1, 100, 200, 600, 400)
    s = surfaces(w)
    body = standing_on(w, 400, s)
    body.walk_to(5000, s)
    events = run(body, s, 20.0, until=ARRIVED)
    assert ARRIVED in events
    assert body.x == 700 - body.edge_inset
    assert body.facing == 1


def test_hops_aside_when_a_window_covers_its_spot():
    back = win(2, 100, 200, 800, 400)
    body = standing_on(back, 450, surfaces(back))
    cover = win(1, 300, 500, 300, 300)  # now covers x 300..600 of the edge
    body.step(DT, surfaces(cover, back))
    assert body.mode is Mode.HOPPING
    run(body, surfaces(cover, back), 2.0, until=LANDED)
    assert body.support == window_key(2)
    assert not (300 < body.x < 600)


def test_holds_still_when_another_window_covers_its_whole_edge():
    back = win(2, 100, 200, 600, 400)
    body = standing_on(back, 400, surfaces(back))
    x, y = body.x, body.y
    cover = win(1, 50, 100, 800, 700)  # in front, hiding the entire top edge
    events = body.step(DT, surfaces(cover, back))
    assert COVERED in events and body.mode is Mode.STANDING and (body.x, body.y) == (x, y)


def test_thrown_pet_bounces_off_the_outer_wall_and_lands():
    body = Body(pet_w=PET_W, pet_h=PET_H)
    body.drop_in(1400, 600)
    body.release(vx=2500, vy=200)
    s = surfaces()
    run(body, s, 4.0, until=LANDED)
    assert body.grounded and 0 <= body.x <= 1512


def test_falls_from_the_upper_monitor_onto_its_floor():
    s = surfaces(displays=(LAPTOP, MONITOR))
    body = Body(pet_w=PET_W, pet_h=PET_H)
    body.drop_in(500, 1800)
    run(body, s, 3.0, until=LANDED)
    assert body.support == floor_key(MONITOR.id) and body.y == 982


def test_released_pet_keeps_throw_speed_capped():
    body = Body(pet_w=PET_W, pet_h=PET_H)
    body.grab()
    body.hold_at(500, 500)
    body.release(vx=30000, vy=0)
    assert body.mode is Mode.FALLING and abs(body.vx) <= 2500
