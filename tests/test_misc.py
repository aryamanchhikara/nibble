"""App categories, line picking, bubble placement, settings."""

import random

from conftest import LAPTOP

from nibble.core import bubble, settings
from nibble.core.apps import Category, categorize
from nibble.core.lines import GENERIC, LinePicker
from nibble.core.spec import load_builtin

# ---- apps -----------------------------------------------------------------


def test_known_apps():
    assert categorize("com.microsoft.VSCode") is Category.CODING
    assert categorize("com.todesktop.230313mzl4w4u92", "Cursor") is Category.CODING
    assert categorize("com.apple.Terminal") is Category.TERMINAL
    assert categorize("com.mitchellh.ghostty") is Category.TERMINAL
    assert categorize("md.obsidian") is Category.WRITING
    assert categorize("com.hnc.Discord") is Category.SOCIAL
    assert categorize("us.zoom.xos") is Category.CALL
    assert categorize("com.colliderli.iina") is Category.VIDEO
    assert categorize("company.thebrowser.Browser") is Category.BROWSER


def test_bundle_ids_are_case_insensitive_and_families_match_by_prefix():
    assert categorize("COM.APPLE.TERMINAL") is Category.TERMINAL
    assert categorize("com.jetbrains.pycharm") is Category.CODING


def test_name_hints_and_unknowns():
    assert categorize("org.example.something", "Super Terminal") is Category.TERMINAL
    assert categorize("org.example.calculator", "Calculator") is Category.OTHER
    assert categorize(None, None) is Category.OTHER


# ---- lines ----------------------------------------------------------------


def test_picker_uses_every_line_before_repeating():
    pip = load_builtin("pip")
    picker = LinePicker(pip, random.Random(0))
    cheers = pip.lines_for("cheers")
    first_round = [picker.pick("cheers") for _ in cheers]
    assert sorted(first_round) == sorted(cheers)
    second = picker.pick("cheers")
    assert second != first_round[-1]  # no back-to-back repeat across rounds


def test_pets_without_cheers_fall_back_to_generic_ones():
    pip = load_builtin("pip")
    lines = {k: v for k, v in pip.lines.items() if k != "cheers"}
    no_cheers = pip.__class__(**{**pip.__dict__, "lines": lines})
    assert LinePicker(no_cheers).pick("cheers") in GENERIC["cheers"]
    assert 8 <= len(GENERIC["cheers"]) <= 10


def test_nested_lines_lookup():
    pip = load_builtin("pip")
    assert pip.lines_for("reactions.coding")
    assert pip.lines_for("reactions.nope") == []


# ---- bubbles --------------------------------------------------------------


def test_bubble_above_stays_on_screen_and_points_at_the_head():
    v = LAPTOP.visible
    lay = bubble.above(head_x=1500, head_top=300, w=180, h=40, visible=v)
    assert lay.box.right <= v.right and lay.box.left >= v.left
    assert lay.tip[1] < lay.box.bottom and lay.tail_side == "bottom"
    assert lay.box.left <= lay.tip[0] <= lay.box.right


def test_bubble_beside_a_peeking_pet_sits_on_the_screen_side():
    v = LAPTOP.visible
    right = bubble.beside(tip_x=1470, center_y=500, side=1, w=160, h=40, visible=v)
    assert right.box.right < 1470 and right.tail_side == "right"
    left = bubble.beside(tip_x=40, center_y=500, side=-1, w=160, h=40, visible=v)
    assert left.box.left > 40 and left.tail_side == "left"
    low = bubble.beside(tip_x=40, center_y=2, side=-1, w=160, h=40, visible=v)
    assert low.box.bottom >= v.bottom


# ---- settings -------------------------------------------------------------


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path) == settings.Settings()  # defaults: cheers on, quiet off
    settings.save(path, settings.Settings(cheer_me_on=False, quiet=True))
    assert settings.load(path) == settings.Settings(cheer_me_on=False, quiet=True)


def test_settings_survive_junk(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"quiet": "yes", "cheer_me_on": false, "mystery": 1}')
    assert settings.load(path) == settings.Settings(cheer_me_on=False, quiet=False)
    path.write_text("{not json")
    assert settings.load(path) == settings.Settings()
