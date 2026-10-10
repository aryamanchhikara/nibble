"""The home page: character select model, layout, rendering, fonts, settings, sounds."""

import wave
from importlib import resources
from io import BytesIO

import pytest

from nibble.core import settings
from nibble.core.canvas import Canvas, Mask
from nibble.core.home import (
    CARD_H,
    CARD_W,
    DIALOG_BUTTONS,
    H,
    LINK,
    SOUND,
    START,
    W,
    HomeModel,
    card_box,
    dialog_button,
    toggle_box,
)
from nibble.core.home_scene import C, HomeRenderer, build_background
from nibble.core.spec import load_builtin

CAST = ("pearl", "archie", "dewey", "kernel")


def model(**kw) -> HomeModel:
    return HomeModel([load_builtin(p) for p in CAST], **kw)


def kinds(actions) -> list[str]:
    return [a.kind for a in actions]


# ---- choosing a pet ------------------------------------------------------------------


def test_arrows_move_between_cards_and_wrap():
    m = model()
    m.press("right", 1.0)
    assert m.pet.id == "archie"
    m.press("left", 2.0)
    m.press("left", 3.0)
    assert m.pet.id == "kernel"  # wrapped around


def test_enter_starts_the_selected_pet_with_its_accessories():
    m = model()
    acts = m.press("enter", 1.0)
    start = [a for a in acts if a.kind == "start"][0]
    assert (start.pet_id, start.worn, start.mode) == ("pearl", frozenset({"glasses"}), "new")


def test_glasses_toggle_changes_what_starts():
    m = model()
    acts = m.press("g", 1.0)
    assert ("wardrobe", "pearl", frozenset()) in [(a.kind, a.pet_id, a.worn) for a in acts]
    start = [a for a in m.press("enter", 2.0) if a.kind == "start"][0]
    assert start.worn == frozenset()


def test_pets_without_accessories_ignore_the_toggle_key():
    m = model()
    m.press("right", 1.0)
    assert m.press("g", 2.0) == []


def test_clicking_the_glasses_switch_toggles_it():
    m = model()
    b = toggle_box(0)
    acts = m.click(b.x + b.w // 2, b.y + 4, 1.0)
    assert "wardrobe" in kinds(acts) and m.worn(m.pets[0]) == frozenset()


def test_clicking_a_card_selects_it_and_start_starts():
    m = model()
    b = card_box(2)
    m.click(b.x + 10, b.y + 10, 1.0)
    assert m.pet.id == "dewey"
    acts = m.click(START.x + 5, START.y + 5, 2.0)
    assert [a for a in acts if a.kind == "start"][0].pet_id == "dewey"


def test_with_a_pet_already_out_start_asks_swap_or_add():
    m = model(running=["Pearl"])
    m.press("right", 1.0)
    assert kinds(m.press("enter", 2.0)) == ["sfx"] and m.dialog is not None
    assert "Pearl" in m.dialog.message[0] and "Archie" in m.dialog.message[1]
    m.press("right", 3.0)  # focus "add"
    start = [a for a in m.press("enter", 4.0) if a.kind == "start"][0]
    assert (start.pet_id, start.mode) == ("archie", "add") and m.dialog is None


def test_dialog_buttons_and_escape():
    m = model(running=["Pearl", "Dewey", "Kernel"])
    m.press("enter", 1.0)
    assert m.dialog.message[0] == "Pearl, Dewey & co. are already out!"
    acts = m.click(dialog_button(0).x + 3, dialog_button(0).y + 3, 2.0)
    assert [a.mode for a in acts if a.kind == "start"] == ["swap"]
    m.press("enter", 3.0)
    assert kinds(m.press("escape", 4.0)) == ["sfx"] and m.dialog is None  # back, not close


def test_escape_closes_and_the_link_and_speaker_work():
    m = model()
    assert kinds(m.press("escape", 1.0)) == ["close"]
    assert kinds(m.click(LINK.x + 4, LINK.y + 4, 1.0)) == ["describe"]
    acts = m.click(SOUND.x + 2, SOUND.y + 2, 1.0)
    assert ("sound", True) in [(a.kind, a.on) for a in acts] and m.sound


def test_selection_bounces_then_settles():
    m = model()
    m.press("right", 10.0)
    assert min(m.bounce(10.0 + t / 100) for t in range(0, 30)) < 0
    assert m.bounce(11.0) == 0 and m.cheering(10.2) and not m.cheering(12.0)


# ---- layout ---------------------------------------------------------------------------


def inside(b) -> bool:
    return 0 <= b.x and 0 <= b.y and b.x + b.w <= W and b.y + b.h <= H


def overlaps(a, b) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def test_everything_fits_on_the_page_without_overlapping():
    cards = [card_box(i) for i in range(4)]
    boxes = cards + [START, LINK, SOUND]
    assert all(inside(b) for b in boxes)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not overlaps(a, b), (a, b)
    assert all(overlaps(toggle_box(i), cards[i]) for i in range(4))
    assert all(inside(dialog_button(i)) for i in range(len(DIALOG_BUTTONS)))


# ---- rendering (with a stand-in font) -------------------------------------------------------


class BoxFont:
    """Every character is a solid 5×7 block: enough to test layout without CoreText."""

    height = 8

    def mask(self, text: str) -> Mask:
        w = max(1, len(text) * 6)
        return Mask(w, self.height, tuple(x % 6 < 5 and y < 7 for y in range(self.height) for x in range(w)))


@pytest.fixture
def renderer():
    return HomeRenderer(BoxFont(), BoxFont())


def test_background_is_deterministic_and_page_sized():
    a, _ = build_background(7)
    b, _ = build_background(7)
    assert (a.w, a.h) == (W, H) and a.px == b.px


def test_render_draws_the_selected_card_highlight_and_live_pets(renderer):
    m = model()
    out = renderer.render(m, 5.0)
    assert (out.w, out.h) == (W, H)
    b = card_box(0)
    border = {out.get(b.x - 1, b.y + 20), out.get(b.x, b.y + 20)}
    assert border & {C["gold"], C["gold_l"], C["gold_d"]}
    # Pearl is drawn in her card, in her own colours.
    pearl_white = tuple(int(load_builtin("pearl").palette["7"][i:i + 2], 16) for i in (1, 3, 5))
    region = {out.get(x, y) for x in range(b.x, b.x + CARD_W) for y in range(b.y, b.y + 45)}
    assert pearl_white in region


def test_glasses_toggle_shows_up_in_the_preview(renderer):
    m = model()
    b = card_box(0)
    lens = tuple(int(load_builtin("pearl").palette["c"][i:i + 2], 16) for i in (1, 3, 5))

    def lens_visible():
        out = renderer.render(m, 5.0)
        return lens in {out.get(x, y) for x in range(b.x, b.x + CARD_W) for y in range(b.y, b.y + 45)}

    assert lens_visible()
    m.press("g", 5.0)
    assert not lens_visible()


def test_animation_actually_animates(renderer):
    m = model()
    frames = {bytes(renderer.render(m, t / 12).px) for t in range(24)}
    assert len(frames) > 5  # stars, TV static, blinking, cursor...


def test_canvas_png_export(tmp_path):
    c = Canvas(4, 3, (10, 20, 30))
    c.save_png(tmp_path / "x.png", scale=2)
    assert (tmp_path / "x.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---- real fonts (macOS) ------------------------------------------------------------------


def test_bundled_fonts_ship_with_their_licenses():
    folder = resources.files("nibble.assets").joinpath("fonts")
    for name in ("PressStart2P-Regular.ttf", "Tiny5-Regular.ttf"):
        assert folder.joinpath(name).is_file()
    for lic in ("PressStart2P-OFL.txt", "Tiny5-OFL.txt"):
        assert "SIL Open Font License" in folder.joinpath(lic).read_text()


def test_names_and_blurbs_fit_their_cards_in_the_real_fonts():
    from nibble.mac.fonts import PixelFont

    big, small = PixelFont("big"), PixelFont("small")
    r = HomeRenderer(big, small)
    for pid in CAST:
        pet = load_builtin(pid)
        assert big.mask(pet.name.upper()).w <= CARD_W - 4, pid
        lines = r.wrap(pet.blurb, CARD_W - 10)
        assert len(lines) <= (3 if pet.accessories else 4), (pid, lines)
    assert big.mask("CHOOSE YOUR NIBBLE").w < W - 2 * 40


def test_pixel_fonts_render_without_antialiasing():
    from nibble.mac.fonts import PixelFont

    m = PixelFont("small").mask("Royalty of the reading nook.")
    assert any(m.bits) and m.h == PixelFont("small").height  # pure on/off pixels by construction


# ---- settings and sounds -----------------------------------------------------------------


def test_lineup_and_wardrobe_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = settings.Settings(seen_home=True, sound=True, wardrobe={"pearl": []}, pets=[{"id": "dewey", "worn": []}])
    settings.save(path, s)
    assert settings.load(path) == s
    path.write_text('{"wardrobe": {"pearl": "glasses"}, "pets": [{"name": "nope"}, {"id": "pearl"}], "sound": 1}')
    loaded = settings.load(path)
    assert loaded.wardrobe == {} and loaded.pets == [{"id": "pearl", "worn": []}] and loaded.sound is False


def test_sound_effects_are_valid_wav():
    from nibble.mac.sounds import EFFECTS, synth

    for name, notes in EFFECTS.items():
        with wave.open(BytesIO(synth(notes))) as w:
            assert w.getnchannels() == 1 and w.getframerate() == 22050 and w.getnframes() > 100, name


def test_card_height_leaves_room_for_the_toggle():
    assert toggle_box(0).y + toggle_box(0).h <= card_box(0).y + CARD_H
