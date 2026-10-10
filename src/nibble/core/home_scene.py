"""Draws the home page: an original 16-bit night scene with the character cards.

A dithered indigo sky full of stars, a crescent moon, a sleepy skyline with
warm windows, a rooftop with a streetlamp, a little couch and a retro TV.
Stars twinkle, the lamp flickers now and then, windows switch on and off and
the TV shows static. The cards, pets and buttons sit on top.

Pets are drawn at one canvas pixel per sprite pixel, in their own style; only
the page around them is 16-bit.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Protocol

from .canvas import RGB, Canvas, Mask, hex_rgb
from .home import (
    CARD_H,
    CARD_W,
    DIALOG,
    DIALOG_BUTTONS,
    H,
    LINK,
    SOUND,
    START,
    W,
    Box,
    HomeModel,
    card_box,
    dialog_button,
    toggle_box,
)
from .sprites import GRID


class PixelFont(Protocol):
    height: int

    def mask(self, text: str) -> Mask: ...


# ---- palette ----------------------------------------------------------------------

C = {k: hex_rgb(v) for k, v in {
    "sky0": "#0a0920", "sky1": "#110e2e", "sky2": "#1a1540", "sky3": "#241c52", "sky4": "#33235f", "sky5": "#48296a",
    "star": "#fff7e0", "star_dim": "#8c84c6", "star_blue": "#a6d6ff", "star_warm": "#ffe1a0",
    "moon": "#fff1c4", "moon_d": "#e9cf8c", "halo": "#3a2f78",
    "far": "#251f52", "far_d": "#1f1a47", "near": "#18143a", "near_l": "#231d4b",
    "win": "#ffcf6b", "win2": "#ff9a4d", "win_off": "#2e2550",
    "floor": "#1f1839", "floor_d": "#181230", "floor_l": "#352b5c", "edge": "#4a3d78",
    "post": "#140f29", "post_l": "#2f2856", "lamp": "#2a2448", "bulb": "#fff0b3", "bulb_off": "#7a6a52",
    "warm": "#ffc65a", "warm_glow": "#5c3f6a", "warm_floor": "#3f2e55",
    "couch": "#7a3a5c", "couch_d": "#58284a", "couch_l": "#9c537a",
    "tv": "#6d5b91", "tv_d": "#4a3e6b", "tv_l": "#8f7db3", "screen": "#1f4a66", "static": "#9fe0ff", "static_l": "#e6fbff",
    "tv_glow": "#273a6b",
    "ink": "#0a0820", "card": "#120f2a", "card2": "#1b1640", "card_edge": "#4a4190", "card_hi": "#2d2668",
    "spot": "#2e2770", "shadow": "#0a0820",
    "text": "#fff4dc", "name": "#ffe9a8", "blurb": "#bdb5ea", "dim": "#8a82c4",
    "gold": "#ffd04a", "gold_l": "#fff2a8", "gold_d": "#d08a1c",
    "on": "#5fd38a", "off": "#5a5288", "knob": "#fff4dc",
    "btn": "#ffcf4a", "btn_l": "#fff1b0", "btn_d": "#c98a1d", "btn_text": "#3a1d10",
}.items()}

GOLD_CYCLE = [C["gold_d"], C["gold"], C["gold_l"], C["gold"]]
SKY = [C[f"sky{i}"] for i in range(6)]
HORIZON = 150
FLOOR_Y = 188
LAMP_X = 13
TV = Box(318, 158, 46, 34)
SCREEN = Box(TV.x + 5, TV.y + 6, 30, 19)


@dataclass
class Star:
    x: int
    y: int
    color: RGB
    kind: str  # dot, cross, sparkle
    phase: float
    twinkles: bool


@dataclass
class Window:
    x: int
    y: int
    color: RGB
    on: bool
    flicker: bool
    phase: float


@dataclass
class Scene:
    stars: list[Star] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)


def _sky_at(y: int) -> RGB:
    pos = min(1.0, y / HORIZON) * (len(SKY) - 1)
    return SKY[min(int(pos + 0.5), len(SKY) - 1)]


def build_background(seed: int = 7) -> tuple[Canvas, Scene]:
    rnd = random.Random(seed)
    c = Canvas(W, H)
    scene = Scene()
    c.vgradient(0, 0, W, HORIZON, SKY)
    c.rect(0, HORIZON, W, FLOOR_Y - HORIZON, SKY[-1])

    # Moon with a dithered halo, in the strip of sky right of the cards (clear
    # of the selection cursor and the speaker button).
    mx, my = 372, 36
    c.glow(mx, my, 16, 15, None, C["halo"], strength=0.55)
    for yy in range(my - 8, my + 9):
        for xx in range(mx - 8, mx + 9):
            if (xx - mx) ** 2 + (yy - my) ** 2 <= 62:
                inner = (xx - mx - 4) ** 2 + (yy - my + 2) ** 2 <= 48
                if not inner:
                    shade = (xx - mx) + (yy - my) > 5
                    c.set(xx, yy, C["moon_d"] if shade else C["moon"])

    # Stars (static dim ones; twinklers are redrawn every frame).
    for _ in range(90):
        x, y = rnd.randrange(2, W - 2), rnd.randrange(2, 118)
        if (x - mx) ** 2 + (y - my) ** 2 < 18 ** 2:
            continue
        roll = rnd.random()
        kind = "sparkle" if roll < 0.06 else "cross" if roll < 0.2 else "dot"
        color = rnd.choice([C["star"], C["star"], C["star_dim"], C["star_blue"], C["star_warm"]])
        star = Star(x, y, color, kind, rnd.random(), rnd.random() < 0.45)
        scene.stars.append(star)
        _draw_star(c, star, bright=False)

    # Skyline: a far layer and a near layer with windows.
    x = -4
    while x < W:
        w, h = rnd.randrange(14, 30), rnd.randrange(22, 52)
        c.rect(x, HORIZON + 6 - h, w, FLOOR_Y - (HORIZON + 6 - h), C["far"])
        c.rect(x + w - 2, HORIZON + 6 - h, 2, FLOOR_Y - (HORIZON + 6 - h), C["far_d"])
        x += w + rnd.randrange(0, 4)
    x = -6
    while x < W:
        w, h = rnd.randrange(18, 38), rnd.randrange(16, 40)
        top = HORIZON + 22 - h
        c.rect(x, top, w, FLOOR_Y - top, C["near"])
        c.rect(x, top, w, 1, C["near_l"])
        if rnd.random() < 0.35:  # antenna or water tower
            c.rect(x + w // 2, top - 6, 1, 6, C["near"])
        for wy in range(top + 4, FLOOR_Y - 6, 6):
            for wx in range(x + 3, x + w - 3, 5):
                if rnd.random() < 0.42:
                    lit = rnd.random() < 0.75
                    win = Window(wx, wy, rnd.choice([C["win"], C["win"], C["win2"]]), lit, rnd.random() < 0.12, rnd.random())
                    scene.windows.append(win)
                    _draw_window(c, win, win.on)
        x += w + rnd.randrange(2, 7)

    # Rooftop floor with tiles and a lit front edge.
    c.rect(0, FLOOR_Y, W, H - FLOOR_Y, C["floor"])
    c.rect(0, FLOOR_Y, W, 1, C["edge"])
    c.rect(0, FLOOR_Y + 1, W, 1, C["floor_l"])
    for ty in range(FLOOR_Y + 6, H, 7):
        c.rect(0, ty, W, 1, C["floor_d"])
    for tx in range(4, W, 16):
        for ty in range(FLOOR_Y + 2, H, 7):
            c.rect(tx + (8 if (ty // 7) % 2 else 0), ty, 1, 6, C["floor_d"])

    _couch(c)
    _tv(c)
    return c, scene


def _draw_star(c: Canvas, s: Star, bright: bool) -> None:
    col = s.color if bright else C["star_dim"] if s.twinkles else s.color
    c.set(s.x, s.y, col)
    if s.kind in ("cross", "sparkle") and bright:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.set(s.x + dx, s.y + dy, C["star_dim"])
    if s.kind == "sparkle" and bright:
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            c.set(s.x + dx, s.y + dy, C["star_dim"])


def _draw_window(c: Canvas, w: Window, on: bool) -> None:
    c.rect(w.x, w.y, 2, 3, w.color if on else C["win_off"])
    if on:
        c.set(w.x, w.y, C["star_warm"])


def _lamp(c: Canvas, on: bool) -> None:
    x = LAMP_X
    top = 62
    if on:
        # Pool of warm light on the floor and the couch, and a halo round the bulb.
        c.glow(x + 26, FLOOR_Y + 4, 42, 10, None, C["warm_floor"], strength=0.9)
        c.glow(x + 1, top + 6, 16, 14, None, C["warm_glow"], strength=0.7)
    c.rect(x, top + 8, 2, FLOOR_Y - top - 8, C["post"])
    c.rect(x, top + 8, 1, FLOOR_Y - top - 8, C["post_l"])
    c.rect(x - 2, FLOOR_Y - 3, 6, 3, C["post"])  # base
    c.rect(x - 4, top, 10, 4, C["lamp"])  # lamp head
    c.rect(x - 3, top - 2, 8, 2, C["lamp"])
    c.rect(x - 2, top + 4, 6, 3, C["bulb"] if on else C["bulb_off"])
    if on:
        c.rect(x - 1, top + 5, 4, 1, C["warm"])


def _couch(c: Canvas) -> None:
    x, y = 30, 168
    c.rect(x, y, 58, 10, C["couch_d"])  # back
    c.rect(x + 1, y + 1, 56, 2, C["couch_l"])
    c.rect(x - 4, y + 6, 66, 14, C["couch"])  # seat and arms
    c.rect(x - 4, y + 6, 8, 14, C["couch_d"])
    c.rect(x + 54, y + 6, 8, 14, C["couch_d"])
    c.rect(x - 4, y + 6, 8, 1, C["couch_l"])
    c.rect(x + 54, y + 6, 8, 1, C["couch_l"])
    for cx in (x + 5, x + 30):
        c.rect(cx, y + 10, 23, 1, C["couch_l"])  # cushions
    c.rect(x - 2, y + 20, 2, 2, C["ink"])  # legs
    c.rect(x + 58, y + 20, 2, 2, C["ink"])


def _tv(c: Canvas) -> None:
    t = TV
    c.glow(t.x + t.w // 2, FLOOR_Y + 4, 34, 7, None, C["tv_glow"], strength=0.8)
    c.rect(t.x + 4, t.y + t.h, t.w - 8, FLOOR_Y - (t.y + t.h), C["tv_d"])  # stand
    c.rect(t.x, t.y, t.w, t.h, C["tv"])
    c.rect(t.x, t.y, t.w, 1, C["tv_l"])
    c.rect(t.x + t.w - 2, t.y, 2, t.h, C["tv_d"])
    c.rect(t.x, t.y + t.h - 2, t.w, 2, C["tv_d"])
    c.rect(SCREEN.x - 1, SCREEN.y - 1, SCREEN.w + 2, SCREEN.h + 2, C["ink"])
    c.rect(t.x + t.w - 8, t.y + 7, 3, 3, C["tv_l"])  # knobs
    c.rect(t.x + t.w - 8, t.y + 13, 3, 3, C["tv_d"])
    for i in range(7):  # rabbit ears
        c.set(t.x + 16 - i, t.y - 1 - i, C["post_l"])
        c.set(t.x + 24 + i, t.y - 1 - i, C["post_l"])


# ---- the page -----------------------------------------------------------------------


def palette_rgb(pet) -> dict[str, RGB]:
    return {k: hex_rgb(v) for k, v in pet.palette.items()}


class HomeRenderer:
    def __init__(self, big: PixelFont, small: PixelFont, seed: int = 7):
        self.big, self.small = big, small
        self.bg, self.scene = build_background(seed)
        self._static: Canvas | None = None
        self._static_key: tuple | None = None
        self._out = Canvas(W, H)
        self._masks: dict[tuple[int, str], Mask] = {}
        self._palettes: dict[str, dict[str, RGB]] = {}
        covered = [card_box(i) for i in range(4)] + [START, SOUND, Box(80, 2, 224, 16)]
        self._visible_stars = [s for s in self.scene.stars if s.twinkles and not any(
            b.x - 3 <= s.x < b.x + b.w + 3 and b.y - 9 <= s.y < b.y + b.h + 3 for b in covered)]

    # ---- text -------------------------------------------------------------

    def _mask(self, font: PixelFont, text: str) -> Mask:
        key = (id(font), text)
        if key not in self._masks:
            self._masks[key] = font.mask(text)
        return self._masks[key]

    def text(self, c: Canvas, font: PixelFont, text: str, x: int, y: int, color: RGB,
             shadow: RGB | None = None, center: bool = False) -> int:
        m = self._mask(font, text)
        if center:
            x -= m.w // 2
        c.mask(m, x, y, color, shadow)
        return m.w

    def wrap(self, text: str, width: int) -> list[str]:
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if line and self._mask(self.small, trial).w > width:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    # ---- frame ---------------------------------------------------------------

    def render(self, model: HomeModel, now: float) -> Canvas:
        lamp_on = _lamp_on(now)
        windows = tuple(_window_on(w, now) for w in self.scene.windows if w.flicker)
        toast = model.toast[0] if model.toast and now < model.toast[1] else None
        key = (model.version, model.bounce(now), lamp_on, windows, toast, id(model))
        if key != self._static_key:
            self._static = self._build_static(model, now, lamp_on, toast)
            self._static_key = key
        c = self._out
        c.restore(self._static)
        self._animate(c, model, now)
        return c

    def _build_static(self, model: HomeModel, now: float, lamp_on: bool, toast: str | None) -> Canvas:
        c = self.bg.copy()
        for w in self.scene.windows:
            if w.flicker:
                _draw_window(c, w, _window_on(w, now))
        _lamp(c, lamp_on)

        self.text(c, self.big, "CHOOSE YOUR NIBBLE", W // 2, 5, C["name"], C["ink"], center=True)
        self._sound_icon(c, model.sound)
        for i, pet in enumerate(model.pets):
            dy = model.bounce(now) if i == model.selected else 0
            self._card(c, model, i, pet, dy)
        self._start_button(c)
        self.text(c, self.small, "< >  choose      enter  start", W // 2, START.y + START.h + 2, C["dim"], center=True)
        if model.custom_pets:
            link = "Describe your own pet..."
            w = self.text(c, self.small, link, W // 2, LINK.y, C["dim"], center=True)
            for xx in range(W // 2 - w // 2, W // 2 + w // 2, 2):
                c.set(xx, LINK.y + 10, C["dim"])  # dotted underline
        else:
            self.text(c, self.small, "Custom pets: coming soon", W // 2, LINK.y, C["dim"], center=True)  # not a link
        if toast:
            self._toast(c, toast)
        return c

    def _card(self, c: Canvas, model: HomeModel, i: int, pet, dy: int) -> None:
        b = card_box(i)
        x, y = b.x, b.y + dy
        selected = i == model.selected
        c.dither(x, y, CARD_W, CARD_H, C["card"], C["card2"], 0.35)
        c.rect(x + 1, y + 1, CARD_W - 2, 1, C["card_hi"])
        c.frame(x, y, CARD_W, CARD_H, C["card_edge"])
        for cx, cy in ((x, y), (x + CARD_W - 1, y), (x, y + CARD_H - 1), (x + CARD_W - 1, y + CARD_H - 1)):
            c.set(cx, cy, self.bg.get(cx, cy - dy) if 0 <= cy - dy < H else C["ink"])  # rounded corners
        # A little stage: a soft backdrop behind every pet (so dark outfits still
        # read), brighter for the selected one, and a shadow at its feet.
        px, py = x + (CARD_W - GRID) // 2, y + 8
        c.glow(x + CARD_W // 2, py + 18, 24, 20, None, C["spot"] if selected else C["card_hi"], strength=0.95 if selected else 0.6)
        c.dither(px + 6, py + GRID - 1, GRID - 12, 2, C["card"], C["shadow"], 0.75)
        # Name and blurb.
        self.text(c, self.big, pet.name.upper(), x + CARD_W // 2, y + 50, C["name"] if selected else C["text"], C["ink"], center=True)
        lines = 3 if pet.accessories else 4  # the accessory switch takes the last line
        for n, line in enumerate(self.wrap(pet.blurb or pet.personality, CARD_W - 10)[:lines]):
            self.text(c, self.small, line, x + CARD_W // 2, y + 62 + n * 10, C["blurb"], center=True)
        if pet.accessories:
            self._toggle(c, model, i, pet, dy)

    def _toggle(self, c: Canvas, model: HomeModel, i: int, pet, dy: int) -> None:
        b = toggle_box(i)
        x, y = b.x, b.y + dy
        acc = next(iter(pet.accessories.values()))
        on = acc.name in model.worn(pet)
        label = f"{acc.label}:"
        w = self._mask(self.small, label).w
        state = "ON" if on else "OFF"
        sw = self._mask(self.small, state).w
        total = w + 3 + 14 + 3 + sw
        x0 = x + (b.w - total) // 2
        self.text(c, self.small, label, x0, y - 1, C["text"])
        sx = x0 + w + 3
        # A pixel switch: pill with a knob.
        c.rect(sx + 1, y + 1, 12, 7, C["on"] if on else C["off"])
        c.rect(sx, y + 2, 14, 5, C["on"] if on else C["off"])
        kx = sx + 8 if on else sx + 1
        c.rect(kx, y + 2, 5, 5, C["knob"])
        self.text(c, self.small, state, sx + 17, y - 1, C["on"] if on else C["dim"])

    def _start_button(self, c: Canvas) -> None:
        b = START
        c.rect(b.x + 1, b.y, b.w - 2, b.h, C["ink"])
        c.rect(b.x, b.y + 1, b.w, b.h - 2, C["ink"])
        c.rect(b.x + 1, b.y + 1, b.w - 2, b.h - 2, C["btn"])
        c.rect(b.x + 1, b.y + 1, b.w - 2, 2, C["btn_l"])
        c.rect(b.x + 1, b.y + b.h - 4, b.w - 2, 3, C["btn_d"])
        c.rect(b.x + b.w - 3, b.y + 1, 2, b.h - 2, C["btn_d"])

    def _sound_icon(self, c: Canvas, on: bool) -> None:
        x, y = SOUND.x + 1, SOUND.y + 2
        col = C["blurb"]
        c.rect(x, y + 3, 3, 4, col)  # speaker
        for i in range(4):
            c.rect(x + 3 + i, y + 3 - i, 1, 4 + 2 * i, col)
        if on:
            c.rect(x + 9, y + 3, 1, 4, col)
            c.rect(x + 11, y + 1, 1, 8, col)
        else:
            for i in range(5):
                c.set(x + 9 + i, y + 3 + i, C["win2"])
                c.set(x + 13 - i, y + 3 + i, C["win2"])

    def _toast(self, c: Canvas, text: str) -> None:
        m = self._mask(self.small, text)
        w, h = m.w + 12, 14
        x, y = (W - w) // 2, 132 + 8
        c.rect(x, y, w, h, C["ink"])
        c.frame(x, y, w, h, C["gold"])
        c.mask(m, x + 6, y + 1, C["text"])

    # ---- animation ---------------------------------------------------------------

    def _animate(self, c: Canvas, model: HomeModel, now: float) -> None:
        for s in self._visible_stars:
            bright = math.sin((now * 1.3 + s.phase) * math.tau * 0.5) > 0.2
            if bright:
                _draw_star(c, s, True)
        self._tv_static(c, now)

        # Pets in their cards: blinking idle, and a happy hop for the one just picked.
        for i, pet in enumerate(model.pets):
            b = card_box(i)
            dy = model.bounce(now) if i == model.selected else 0
            if i == model.selected and model.cheering(now):
                frame = pet.frame("happy", int(now * 6), model.worn(pet))
            else:
                blinking = (now + i * 0.77) % 3.4 < 0.15
                frame = pet.frame("idle", 1 if blinking else 0, model.worn(pet))
            pal = self._palettes.setdefault(pet.id, palette_rgb(pet))
            c.sprite(frame, pal, b.x + (CARD_W - GRID) // 2, b.y + 8 + dy)

        # Selected card: cycling gold border and a bobbing cursor.
        b = card_box(model.selected)
        dy = model.bounce(now)
        gold = GOLD_CYCLE[int(now * 8) % len(GOLD_CYCLE)]
        c.frame(b.x - 1, b.y - 1 + dy, CARD_W + 2, CARD_H + 2, gold, thickness=2)
        for cx, cy in ((b.x - 1, b.y - 1), (b.x + CARD_W, b.y - 1), (b.x - 1, b.y + CARD_H), (b.x + CARD_W, b.y + CARD_H)):
            c.set(cx, cy + dy, C["ink"])
        ax, ay = b.x + CARD_W // 2, b.y - 7 + dy + (1 if int(now * 3) % 2 else 0)  # clear of the title even mid-bounce
        for row in range(4):
            c.rect(ax - 3 + row, ay + row, 7 - 2 * row, 1, C["gold"])
        c.rect(ax - 3, ay, 7, 1, C["gold_l"])

        # START: blinking text, arcade-style.
        col = C["btn_text"] if int(now * 2) % 2 == 0 else C["gold_d"]
        self.text(c, self.big, "START", START.x + START.w // 2, START.y + 7, col, center=True)
        if model.dialog is not None:
            self._dialog(c, model)

    def _tv_static(self, c: Canvas, now: float) -> None:
        rnd = random.Random(int(now * 10))
        s = SCREEN
        c.rect(s.x, s.y, s.w, s.h, C["screen"])
        for _ in range(70):
            x, y = s.x + rnd.randrange(s.w), s.y + rnd.randrange(s.h)
            c.set(x, y, C["static_l"] if rnd.random() < 0.3 else C["static"])
        roll = int(now * 18) % (s.h + 8)  # a rolling bar
        if roll < s.h:
            c.rect(s.x, s.y + roll, s.w, 1, C["static"])

    def _dialog(self, c: Canvas, model: HomeModel) -> None:
        d, b = model.dialog, DIALOG
        c.rect(b.x + 2, b.y + 2, b.w, b.h, C["ink"])  # drop shadow
        c.dither(b.x, b.y, b.w, b.h, C["card"], C["card2"], 0.3)
        c.frame(b.x, b.y, b.w, b.h, C["gold"], thickness=2)
        for n, line in enumerate(d.message):
            self.text(c, self.small, line, b.x + b.w // 2, b.y + 12 + n * 12, C["text"], center=True)
        for i, name in enumerate(DIALOG_BUTTONS):
            bb = dialog_button(i)
            focus = i == d.focus
            c.rect(bb.x, bb.y, bb.w, bb.h, C["btn"] if focus else C["card_hi"])
            c.frame(bb.x, bb.y, bb.w, bb.h, C["ink"] if focus else C["card_edge"])
            self.text(c, self.big, name.upper(), bb.x + bb.w // 2, bb.y + 5, C["btn_text"] if focus else C["text"], center=True)


def _lamp_on(now: float) -> bool:
    """Mostly on, with a quick stutter every few seconds."""
    cycle = now % 6.3
    return not (2.0 < cycle < 2.08 or 2.16 < cycle < 2.22 or 4.9 < cycle < 4.95)


def _window_on(w: Window, now: float) -> bool:
    return w.on if math.sin((now / 7 + w.phase) * math.tau) > -0.6 else not w.on
