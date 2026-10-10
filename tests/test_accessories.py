"""Accessory overlays (Pearl's glasses) and pet-format compatibility."""

import copy
import json
from importlib import resources

import pytest

from nibble.core.peek import clip, layout, orient
from nibble.core.spec import ANIMATIONS, STANDING, PetSpec, load_builtin
from nibble.core.sprites import TRANSPARENT, bbox, mirror, overlay, shift_down
from nibble.core.validate import validate_pet

CAST = ("pearl", "archie", "dewey", "kernel")


def raw(pet_id: str) -> dict:
    return json.loads(resources.files("nibble.pets").joinpath(f"{pet_id}.json").read_text())


# ---- overlay ----------------------------------------------------------------------


def test_overlay_pastes_opaque_pixels_and_clips_at_the_edges():
    base = ("....", "....", "....")
    assert overlay(base, ("ab", ".c"), 1, 1) == ("....", ".ab.", "..c.")
    assert overlay(base, ("ab", "cd"), 3, 2) == ("....", "....", "...a")  # clipped
    assert overlay(base, ("ab",), -1, 0) == ("b...", "....", "....")


# ---- Pearl's glasses line up in every frame -------------------------------------------

# Pearl's palette: 1 outline/eyes, 2 skin, 3 skin shade, e cheek, f white glint.
FACE = set("123ef")
LENS = set("cd")


def lens_pixels(pet: PetSpec, anim: str, i: int):
    acc = pet.accessories["glasses"]
    ax, ay = pet.anchor(acc.anchor, anim, i)
    for dy, row in enumerate(acc.sprite):
        for dx, ch in enumerate(row):
            if ch in LENS:
                yield ax + dx, ay + dy


@pytest.mark.parametrize("anim", list(ANIMATIONS))
def test_glasses_sit_on_her_face_in_every_frame(anim):
    pearl = load_builtin("pearl").feet_on_ground()
    for i, base in enumerate(pearl.frames[anim]):
        assert pearl.anchor("eyes", anim, i) is not None, f"{anim}[{i}] has no anchor"
        under = {base[y][x] for x, y in lens_pixels(pearl, anim, i)}
        assert under <= FACE, f"{anim}[{i}]: lenses cover {under - FACE} instead of her face"


def sprite_pixels(pet: PetSpec, anim: str, i: int) -> set[tuple[int, int]]:
    acc = pet.accessories["glasses"]
    ax, ay = pet.anchor(acc.anchor, anim, i)
    return {(ax + dx, ay + dy) for dy, row in enumerate(acc.sprite) for dx, ch in enumerate(row) if ch != TRANSPARENT}


def test_glasses_cover_both_eyes():
    """Her eyes (open, blinking, happy or side-eyeing) end up under the glasses in every frame."""
    pearl = load_builtin("pearl")
    for anim, count in ANIMATIONS.items():
        for i in range(count):
            base = pearl.frames[anim][i]
            covered = sprite_pixels(pearl, anim, i)
            for left, right in ((12, 16), (18, 22)):  # around the back eye, around the front eye
                eye = {(x, y) for y, row in enumerate(base) for x, ch in enumerate(row)
                       if ch == "1" and left <= x <= right and (x, y) in covered}
                assert eye, f"{anim}[{i}]: an eye isn't under the glasses"
            assert pearl.frame(anim, i, {"glasses"}) != base


def test_glasses_are_optional_and_on_by_default():
    pearl = load_builtin("pearl")
    assert pearl.default_worn == {"glasses"}
    assert pearl.frame("idle", 0) == pearl.frames["idle"][0]
    assert pearl.frame("idle", 0, {"glasses"}) != pearl.frames["idle"][0]
    assert pearl.frame("idle", 0, {"a hat she doesn't have"}) == pearl.frames["idle"][0]


def test_glasses_follow_her_when_mirrored_and_peeking():
    pearl = load_builtin("pearl")
    dressed = pearl.frame("idle", 0, {"glasses"})
    assert mirror(dressed) == tuple(row[::-1] for row in dressed)
    standing = [f for n in STANDING for f in pearl.frames[n]]
    for side in (1, -1):
        lay = layout(standing, side, upright=False, look=1, scale=1)
        peeked, _ = clip(orient(dressed, side, False, 1), side, lay.ref, lay.ref.width)
        assert sum(row.count("c") for row in peeked) == sum(row.count("c") for row in dressed)


def test_anchors_move_with_frames_that_get_put_back_on_the_ground():
    pearl = load_builtin("pearl")
    lifted = dict(pearl.frames)
    lifted["sit"] = (shift_down(pearl.frames["sit"][0], -2),)  # drawn two pixels too high
    anchors = {"eyes": dict(pearl.anchors["eyes"])}
    x, y = pearl.anchors["eyes"]["sit"][0]
    anchors["eyes"]["sit"] = ((x, y - 2),)
    floaty = PetSpec(**{**pearl.__dict__, "frames": lifted, "anchors": anchors})
    fixed = floaty.feet_on_ground()
    assert fixed.frames["sit"][0] == pearl.frames["sit"][0]
    assert fixed.frame("sit", 0, {"glasses"}) == pearl.frame("sit", 0, {"glasses"})


# ---- format compatibility ---------------------------------------------------------------


def test_pets_without_accessories_still_load_and_validate():
    pip = raw("pip")
    assert "anchors" not in pip and "accessories" not in pip
    v = validate_pet(pip, "pip")
    assert v.ok and v.spec.accessories == {} and v.spec.anchors == {}
    spec = PetSpec.from_dict(pip)
    assert spec.frame("walk", 1, {"glasses"}) == spec.frames["walk"][1]  # asking for glasses is harmless


def test_round_trip_keeps_accessories_anchors_and_blurb():
    pearl = load_builtin("pearl")
    again = PetSpec.from_dict(json.loads(json.dumps(pearl.to_dict())))
    assert again == pearl
    assert "accessories" not in load_builtin("pip").to_dict()  # old pets stay byte-compatible


def test_the_cast_validates_cleanly():
    for pid in CAST:
        v = validate_pet(raw(pid), pid)
        assert v.ok and not v.fixes, (pid, v.errors, v.fixes)


def broken(mutate) -> list[str]:
    data = copy.deepcopy(raw("pearl"))
    mutate(data)
    return validate_pet(data).errors


def test_anchor_tables_must_cover_every_frame():
    errs = broken(lambda d: d["anchors"]["eyes"]["walk"].pop())
    assert any("anchors.eyes.walk needs exactly 4" in e for e in errs)
    errs = broken(lambda d: d["anchors"]["eyes"].pop("sleep"))
    assert any("anchors.eyes.sleep" in e for e in errs)


def test_anchor_points_must_be_grid_coordinates():
    errs = broken(lambda d: d["anchors"]["eyes"]["idle"].__setitem__(0, [3, 99]))
    assert any("anchors.eyes.idle[0]" in e for e in errs)
    errs = broken(lambda d: d["anchors"]["eyes"]["idle"].__setitem__(0, "here"))
    assert any("anchors.eyes.idle[0]" in e for e in errs)


def test_skipping_a_frame_with_null_is_allowed():
    data = copy.deepcopy(raw("pearl"))
    data["anchors"]["eyes"]["sleep"] = [None, None]
    v = validate_pet(data)
    assert v.ok and v.spec.frame("sleep", 0, {"glasses"}) == v.spec.frames["sleep"][0]


def test_accessories_must_use_a_known_anchor_and_the_palette():
    assert any("isn't one of the pet's anchors" in e for e in broken(lambda d: d["accessories"]["glasses"].update(anchor="nose")))
    assert any("not in the palette" in e for e in broken(lambda d: d["accessories"]["glasses"]["sprite"].append("zz")))
    assert any("rows of at most" in e for e in broken(lambda d: d["accessories"]["glasses"].update(sprite=["1" * 40])))


# ---- the cast's house style -------------------------------------------------------------


@pytest.mark.parametrize("pid", CAST)
def test_cast_matches_the_house_style(pid):
    pet, pip = load_builtin(pid), load_builtin("pip")
    assert len(pet.palette) <= 15
    assert pet.palette["1"] == pip.palette["1"]  # same outline colour as Pip
    for anim, count in ANIMATIONS.items():
        assert len(pet.frames[anim]) == count
        assert all(len(f) == 32 and all(len(r) == 32 for r in f) for f in pet.frames[anim])
    assert pet.metrics().feet_row == 31  # stands on the edge like Pip
    assert pet.blurb and len(pet.lines_for("cheers")) >= 8
    for category in ("quips", "petting", "hungry", "fed", "bored", "chatter.openers", "chatter.replies",
                     "reactions.coding", "reactions.terminal", "reactions.social"):
        assert pet.lines_for(category), (pid, category)


def test_each_cast_member_is_a_distinct_silhouette():
    boxes = {pid: bbox([load_builtin(pid).frames["idle"][0]]) for pid in CAST}
    frames = {pid: load_builtin(pid).frames["idle"][0] for pid in CAST}
    assert len(set(frames.values())) == 4
    assert all(b.height >= 24 for b in boxes.values())  # full chibi figures, not blobs


def test_archie_smokes_only_while_idling_and_sitting():
    archie = load_builtin("archie")
    smoke = "c"  # the wisp colour isn't used anywhere else on him
    for anim in ("idle", "sit"):
        assert all(smoke in "".join(f) for f in archie.frames[anim]), anim
    for anim in ("walk", "happy", "dangle", "fall", "sleep"):
        assert not any(smoke in "".join(f) for f in archie.frames[anim]), anim
