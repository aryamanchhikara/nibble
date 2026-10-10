"""Pet size: crisp on every display, and everything tied to size scales with it."""

import random

import pytest
from conftest import snap, win

from nibble.core import settings
from nibble.core.brain import Activity, Brain, Tuning
from nibble.core.context import Context
from nibble.core.peek import PeekTuning, clip, layout, orient
from nibble.core.physics import Body, Mode, Peek
from nibble.core.size import DEFAULT, REFERENCE_SCALE, Size, crisp_scale, parse, size_factor
from nibble.core.spec import STANDING, load_builtin
from nibble.core.sprites import GRID, TRANSPARENT, hit_test
from nibble.core.world import WorldView

# ---- the setting ------------------------------------------------------------


def test_sizes_and_default():
    assert [GRID * s.scale for s in Size] == [48, 64, 96]
    assert DEFAULT is Size.MEDIUM
    assert parse("large") is Size.LARGE and parse("huge") is Size.MEDIUM and parse(None) is Size.MEDIUM
    assert Size.SMALL.label == "Small (48 pt)"


def test_size_setting_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path).size == "medium"
    settings.save(path, settings.Settings(size="small"))
    assert settings.load(path).size == "small"
    path.write_text('{"size": "enormous"}')
    assert settings.load(path).size == "medium"


# ---- crisp pixels -------------------------------------------------------------


@pytest.mark.parametrize(
    "requested, backing, expected",
    [
        (1.5, 2, 1.5),  # Retina: 3 device pixels, already whole
        (2.0, 2, 2.0),
        (3.0, 2, 3.0),
        (1.5, 1, 1.0),  # non-Retina: 1.5 is a tie, rounds down so Small stays small
        (2.0, 1, 2.0),
        (3.0, 1, 3.0),
        (1.25, 2, 1.0),  # 2.5 device px: tie, down
        (1.4, 2, 1.5),  # 2.8 device px: nearest is 3
        (0.2, 1, 1.0),  # never below one device pixel
    ],
)
def test_crisp_scale(requested, backing, expected):
    assert crisp_scale(requested, backing) == expected


@pytest.mark.parametrize("backing", [1.0, 2.0, 3.0])
@pytest.mark.parametrize("size", list(Size))
def test_every_sprite_pixel_is_whole_device_pixels(size, backing):
    device = crisp_scale(size.scale, backing) * backing
    assert device >= 1 and device == int(device)


def test_hit_testing_follows_fractional_scales():
    frame = ("1.", "..")  # one opaque pixel, top-left
    s = 1.5
    assert hit_test(frame, 0.2, 1.6, s) and hit_test(frame, 1.4, 2.9, s)
    assert not hit_test(frame, 1.6, 2.0, s)  # the transparent pixel to its right
    assert not hit_test(frame, 0.5, 1.4, s)  # the row below


# ---- behaviour scales with size -----------------------------------------------


def test_spatial_tuning_scales_and_timing_does_not():
    base = Tuning()
    small = base.for_size(size_factor(1.5))
    assert small.walk_speed == base.walk_speed / 2
    assert small.walk_distance == tuple(d / 2 for d in base.walk_distance)
    assert small.chase_radius == base.chase_radius / 2 and small.stride == base.stride / 2
    assert small.sit_time == base.sit_time and small.reaction_delay == base.reaction_delay
    assert base.for_size(size_factor(REFERENCE_SCALE)) is base


def test_peek_tuning_scales_but_the_scrollbar_strip_does_not():
    base = PeekTuning()
    medium = base.for_size(size_factor(2.0))
    assert medium.pop_radius == pytest.approx(base.pop_radius * 2 / 3)
    assert medium.slide_speed == pytest.approx(base.slide_speed * 2 / 3)
    assert medium.edge_strip == base.edge_strip
    assert medium.rest == base.rest  # fractions of the pet are size-free already


def test_small_pets_take_small_hops():
    def hop_height(pet_h):
        body = Body(pet_w=pet_h * 0.8, pet_h=pet_h)
        body.x, body.y = 100, 100
        body.hop_to_point(110, 100, Peek(1, 1, 0, 0))
        return body.hop.height

    assert hop_height(36) == pytest.approx(hop_height(72) / 2)


def test_a_small_pet_still_chases_a_hovering_cursor():
    k = size_factor(1.5)
    pet_w, pet_h = 30.0, 36.0
    brain = Brain(random.Random(1), Tuning().for_size(k))
    body = Body(pet_w=pet_w, pet_h=pet_h)
    world = WorldView(snap(win(1, 50, 150, 1400, 500)), pet_w, pet_h)
    body.drop_in(700, 800)
    now = 0.0
    for _ in range(int(2.0 / 0.02)):
        now += 0.02
        brain.update(now, body, world, Context(user_idle=1.0))
        body.step(0.02, world.surfaces)
    assert body.mode is Mode.STANDING
    hover = Context(cursor=(body.x + 35, body.y + 20), user_idle=0.1)
    for _ in range(int((brain.tuning.chase_hover + 0.3) / 0.02)):
        now += 0.02
        brain.update(now, body, world, hover)
        body.step(0.02, world.surfaces)
    assert brain.activity is Activity.CHASE


@pytest.mark.parametrize("scale", [1.5, 2.0, 3.0])
def test_peek_placement_keeps_visible_pixels_inside_the_edge(scale):
    pip = load_builtin("pip")
    standing = [f for n in STANDING for f in pip.frames[n]]
    for side in (1, -1):
        lay = layout(standing, side, upright=False, look=1, scale=scale)
        assert lay.full == lay.ref.width * scale
        clipped, anchor = clip(orient(pip.frame("idle", 0), side, False, 1), side, lay.ref, 12)
        edge = 1512 if side > 0 else 0
        ox, _ = lay.origin(Peek(1, side, edge, 500), anchor)
        cols = [c for row in clipped for c, ch in enumerate(row) if ch != TRANSPARENT]
        lo, hi = ox + min(cols) * scale, ox + (max(cols) + 1) * scale
        # Flush against the edge, and never more than the requested depth showing.
        if side > 0:
            assert hi == pytest.approx(edge) and lo >= edge - 12 * scale - 1e-9
        else:
            assert lo == pytest.approx(edge) and hi <= edge + 12 * scale + 1e-9
