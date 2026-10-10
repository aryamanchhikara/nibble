from nibble.core.spec import ANIMATIONS, GROUNDED, load_builtin
from nibble.core.sprites import GRID, bottom_row, hit_test, mirror, shift_down, to_rgba

TINY = ("..1", ".22", "...")  # 3x3 test frame


def test_pip_has_every_animation_with_full_size_frames():
    pip = load_builtin("pip")
    for name, count in ANIMATIONS.items():
        frames = pip.frames[name]
        assert len(frames) == count, name
        for frame in frames:
            assert len(frame) == GRID and all(len(row) == GRID for row in frame)
            assert set("".join(frame)) <= set(pip.palette) | {"."}


def test_pip_feet_touch_the_bottom_row():
    m = load_builtin("pip").metrics()
    assert m.feet_row == GRID - 1
    assert m.baseline(3) == 0


def test_mirror_flips_rows_and_round_trips():
    assert mirror(TINY) == ("1..", "22.", "...")
    assert mirror(mirror(TINY)) == TINY


def test_hit_test_uses_view_coordinates_from_the_bottom_left():
    scale = 10
    assert hit_test(TINY, 25, 25, scale)  # top-right pixel "1" (row 0 is the top)
    assert not hit_test(TINY, 5, 25, scale)  # transparent
    assert hit_test(TINY, 15, 15, scale)  # middle row "2"
    assert not hit_test(TINY, 15, 5, scale)  # empty bottom row
    assert not hit_test(TINY, -1, 15, scale) and not hit_test(TINY, 35, 15, scale)


def test_rgba_is_premultiplied_and_transparent_where_empty():
    data = to_rgba(TINY, {"1": "#ff0000", "2": "#00ff00"})
    assert len(data) == 9 * 4
    assert data[8:12] == bytes((255, 0, 0, 255))
    assert data[0:4] == bytes(4)


def test_shift_down_never_crops_pixels():
    assert shift_down(TINY, 1) == ("...", "..1", ".22")
    assert shift_down(TINY, 5) == ("...", "..1", ".22")  # only one empty row to give
    assert shift_down(TINY, -3) == TINY  # nothing empty on top


def test_feet_on_ground_aligns_grounded_poses():
    pip = load_builtin("pip")
    floating = tuple(["." * GRID] * 2 + list(pip.frames["sleep"][0][:-2]))
    lifted = pip.__class__(**{**pip.__dict__, "frames": {**pip.frames, "sleep": (floating, floating)}})
    fixed = lifted.feet_on_ground()
    for name in GROUNDED:
        for frame in fixed.frames[name]:
            assert bottom_row(frame) == GRID - 1, name
    # Mid-air poses are left alone.
    assert fixed.frames["happy"] == pip.frames["happy"]
