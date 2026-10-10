import copy
import json
from importlib import resources

import pytest

from nibble.core.spec import ANIMATIONS, LINES, MAX_LINE_LENGTH, NESTED_LINES
from nibble.core.validate import slugify, validate_lines, validate_pet


@pytest.fixture
def pip() -> dict:
    return json.loads(resources.files("nibble.pets").joinpath("pip.json").read_text())


def errors_for(data) -> list[str]:
    return validate_pet(data).errors


def test_pip_is_valid(pip):
    v = validate_pet(pip, "pip")
    assert v.ok and v.errors == [] and v.fixes == []
    assert v.spec.lines_for("cheers") == pip["lines"]["cheers"]


def test_schema_covers_cheers():
    assert LINES["cheers"] == (8, 10)


def test_missing_cheers_is_an_error(pip):
    del pip["lines"]["cheers"]
    assert any("lines.cheers" in e for e in errors_for(pip))


def test_too_few_cheers_is_an_error(pip):
    pip["lines"]["cheers"] = pip["lines"]["cheers"][:5]
    assert any("lines.cheers has 5" in e for e in errors_for(pip))


def test_extra_and_duplicate_lines_are_trimmed(pip):
    cheers = pip["lines"]["cheers"]
    pip["lines"]["cheers"] = cheers + [cheers[0].upper(), "one more!", "and another!", "ok last one"]
    v = validate_pet(pip)
    assert v.ok
    assert len(v.spec.lines_for("cheers")) == 10
    assert any("kept the first 10" in f for f in v.fixes)


def test_overlong_lines_are_dropped_when_enough_remain(pip):
    pip["lines"]["quips"].append("x" * (MAX_LINE_LENGTH + 1))
    v = validate_pet(pip)
    assert v.ok and any("over 60" in f for f in v.fixes)


def test_nested_lines_are_checked(pip):
    del pip["lines"]["reactions"]["social"]
    assert any("lines.reactions.social" in e for e in errors_for(pip))
    for group, keys in NESTED_LINES.items():
        assert group in pip["lines"]


def test_rows_off_by_one_are_repaired(pip):
    frame = pip["frames"]["idle"][0]
    frame[3] = frame[3][:-1]  # 31 characters
    frame.append("." * 32)  # 33 rows, last one empty
    v = validate_pet(pip)
    assert v.ok
    assert len(v.spec.frames["idle"][0]) == 32 and all(len(r) == 32 for r in v.spec.frames["idle"][0])
    assert v.fixes


def test_badly_sized_frames_are_errors(pip):
    pip["frames"]["walk"][1] = pip["frames"]["walk"][1][:20]
    assert any("frames.walk[1] has 20 rows" in e for e in errors_for(pip))


def test_unknown_colour_characters_are_errors(pip):
    row = pip["frames"]["sit"][0][15]
    pip["frames"]["sit"][0][15] = "Z" + row[1:]
    assert any("frames.sit[0] row 15 uses 'Z'" in e for e in errors_for(pip))


def test_identical_animation_frames_are_errors(pip):
    pip["frames"]["walk"] = [pip["frames"]["walk"][0]] * 4
    assert any("all 4 frames of walk are identical" in e for e in errors_for(pip))


def test_missing_or_short_animations_are_errors(pip):
    del pip["frames"]["sleep"]
    pip["frames"]["walk"] = pip["frames"]["walk"][:2]
    errs = errors_for(pip)
    assert any("frames.sleep is missing" in e for e in errs)
    assert any("frames.walk has 2" in e for e in errs)


def test_blank_frames_are_errors(pip):
    pip["frames"]["fall"] = [["." * 32] * 32]
    assert any("frames.fall[0] only has 0" in e for e in errors_for(pip))


def test_palette_is_normalized_and_checked(pip):
    pip["palette"]["1"] = "2A1F45"
    pip["palette"]["2"] = "#abc"
    v = validate_pet(pip)
    assert v.ok and v.spec.palette["1"] == "#2a1f45" and v.spec.palette["2"] == "#aabbcc"
    pip2 = copy.deepcopy(pip)
    pip2["palette"]["."] = "#000000"
    assert any('palette key' in e for e in errors_for(pip2))
    pip3 = copy.deepcopy(pip)
    pip3["palette"]["9"] = "purple"
    assert any('palette["9"]' in e for e in errors_for(pip3))


def test_frames_given_as_one_string_are_split(pip):
    pip["frames"]["fall"][0] = "\n".join(pip["frames"]["fall"][0])
    assert validate_pet(pip).ok


def test_every_animation_is_required():
    assert set(ANIMATIONS) == {"idle", "walk", "sit", "sleep", "happy", "eat", "dangle", "fall", "sideeye"}


def test_non_object_input():
    assert errors_for(["not", "an", "object"]) == ["The response must be a single JSON object."]


def test_lines_only_validation(pip):
    v = validate_lines({"lines": pip["lines"]})
    assert v.ok and v.lines["cheers"] == pip["lines"]["cheers"]
    del pip["lines"]["cheers"]
    assert not validate_lines(pip["lines"]).ok


def test_slugify():
    assert slugify("Sir Grumbles III!") == "sir-grumbles-iii"
    assert slugify("☆") == "pet"
