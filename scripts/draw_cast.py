"""Draw nibble's built-in cast (Pearl, Archie, Dewey, Kernel) as pet JSON.

Same house style as Pip: 32×32 palette-indexed frames, a 1px #2a1f45
outline, light from the top-left, pink cheeks, big glinting eyes, at most 15
colours. Every character is drawn by one chibi rig (head, torso, arms, legs
and face positions per pose) plus their own hair, outfit and props, so all
17 frames stay on-model.

Run: uv run python scripts/draw_cast.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from cast_lines import LINES
from pixelart import EMPTY, Grid

OUT = Path(__file__).resolve().parents[1] / "src" / "nibble" / "pets"

# Palette slots shared by every character, so the rig stays generic.
INK, SKIN, SKIN_D, HAIR, HAIR_D, HAIR_L, CLOTH, CLOTH_D, CLOTH_L, ACC, ACC2, PROP, PROP2, CHEEK, WHITE = (
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f",
)


@dataclass(frozen=True)
class Pose:
    bob: int = 0  # whole body up (-) or down (+)
    head_dy: int = 0  # head relative to body (sleepy droop)
    sit: bool = False
    legs: str = "stand"  # stand, a, b, pass, tuck, spread, dangle_a, dangle_b
    arms: str = "prop"  # prop (holding their thing), up, eat, dangle
    eyes: str = "open"  # open, blink, happy, wide, side, closed
    mouth: str = "smile"  # smile, open, o, flat, chew, sleep
    snack: int = -1  # eat frames: 0 whole, 1 bitten
    frame: int = 0  # little prop animations (smoke)
    airborne: bool = False


POSES: dict[str, list[Pose]] = {
    "idle": [Pose(), Pose(eyes="blink", frame=1)],
    "walk": [Pose(legs="a"), Pose(legs="pass", bob=-1, frame=1), Pose(legs="b"), Pose(legs="pass", bob=-1, frame=1)],
    "sit": [Pose(sit=True)],
    "sleep": [
        Pose(sit=True, eyes="closed", mouth="sleep", head_dy=1),
        Pose(sit=True, eyes="closed", mouth="sleep", head_dy=1, bob=1, frame=1),
    ],
    "happy": [
        Pose(arms="up", eyes="happy", mouth="open"),
        Pose(arms="up", eyes="happy", mouth="open", bob=-3, legs="tuck", airborne=True),
    ],
    "eat": [Pose(arms="eat", mouth="open", snack=0), Pose(arms="eat", eyes="happy", mouth="chew", snack=1)],
    "dangle": [
        Pose(bob=-2, legs="dangle_a", arms="dangle", eyes="wide", mouth="o", airborne=True),
        Pose(bob=-2, legs="dangle_b", arms="dangle", eyes="wide", mouth="o", airborne=True, frame=1),
    ],
    "fall": [Pose(bob=-1, legs="spread", arms="up", eyes="wide", mouth="o", airborne=True)],
    "sideeye": [Pose(eyes="side", mouth="flat")],
}

# Rig geometry (facing right; the face sits a pixel right of centre).
HEAD_RX, HEAD_RY = 7.0, 6.3
BACK_EYE, FRONT_EYE = 13, 19  # x of each 2-wide eye


@dataclass
class Body:
    dy: int  # vertical offset of the whole figure
    cx: float
    cy: float  # head centre
    eye_y: int  # top row of the eyes (3 tall)
    torso_top: int
    torso_bot: int
    sit: bool

    @property
    def mouth_y(self) -> int:
        return self.eye_y + 4


def body_for(p: Pose) -> Body:
    dy = p.bob + (5 if p.sit else 0)
    head_dy = dy + p.head_dy
    return Body(dy, 16.0, 12.0 + head_dy, 12 + head_dy, 18 + dy, 23 + dy, p.sit)


class Character:
    id = name = personality = blurb = ""
    palette: dict[str, str] = {}
    lines: dict = {}
    leg = SKIN
    shoe = INK
    sleeve = CLOTH
    lens = False  # draws glasses into the art
    round_lens = True
    lips = False
    tooth = False
    covered_back_eye = False
    lashes = False
    lidded = False

    # hooks
    def behind(self, g: Grid, b: Body, p: Pose) -> None: ...
    def outfit(self, g: Grid, b: Body, p: Pose) -> None: ...
    def hair(self, g: Grid, b: Body, p: Pose) -> None: ...
    def hold(self, g: Grid, b: Body, p: Pose) -> None:
        _arm_down(g, b, self.sleeve, front=True)

    def details(self, g: Grid, b: Body, p: Pose) -> None: ...

    def shade(self, g: Grid) -> None:
        g.rim({CLOTH, CLOTH_D, CLOTH_L}, CLOTH, CLOTH_D, dx=1, dy=0)
        g.rim({HAIR, HAIR_D, HAIR_L}, HAIR, HAIR_D, dx=1, dy=1)
        g.rim({SKIN, SKIN_D, CHEEK}, SKIN, SKIN_D, dx=1, dy=0)


# ---- the rig ------------------------------------------------------------------


def draw(ch: Character, p: Pose) -> tuple[list[str], tuple[int, int]]:
    """One frame, plus the eye anchor (top-left of the glasses area) for accessories."""
    g = Grid()
    b = body_for(p)
    ch.behind(g, b, p)
    if not p.sit:
        _legs(g, b, p, ch)
    _back_arm(g, b, p, ch)
    ch.outfit(g, b, p)
    if p.sit:
        _legs(g, b, p, ch)  # legs stretched out in front of the skirt or coat
    g.ellipse(b.cx, b.cy, HEAD_RX, HEAD_RY, SKIN)
    ch.hair(g, b, p)
    _front_arm(g, b, p, ch)
    if p.snack >= 0:
        g.ellipse(22.0, b.mouth_y + 0.5, 2.0, 2.0, ACC2)
        if p.snack == 1:
            g.put_all([(20, b.mouth_y - 1), (21, b.mouth_y - 1), (20, b.mouth_y)], EMPTY)
    ch.shade(g)
    g.outline(INK)
    _face(g, b, p, ch)
    if ch.lens:
        _glasses(g, b, p, ch)
    ch.details(g, b, p)
    return g.rows(), (BACK_EYE - 2, b.eye_y - 2)


def _legs(g: Grid, b: Body, p: Pose, ch: Character) -> None:
    leg, shoe = ch.leg, ch.shoe
    if p.sit:
        top = b.torso_bot + 1
        g.rect(13, top, 22, top + 1, leg)  # legs straight out in front
        g.rect(22, top - 2, 23, top + 1, shoe)  # toes up
        return
    top = b.torso_bot + 1
    if p.legs == "tuck":
        g.rect(14, top, 15, top + 1, leg)
        g.rect(18, top, 19, top + 1, leg)
        g.rect(13, top + 2, 15, top + 3, shoe)
        g.rect(18, top + 2, 20, top + 3, shoe)
        return
    if p.legs.startswith("dangle"):
        s = 0 if p.legs == "dangle_a" else 1
        g.rect(14 - s, top, 15 - s, top + 4, leg)
        g.rect(18 + s, top, 19 + s, top + 3, leg)
        g.rect(13 - s, top + 5, 15 - s, top + 5, shoe)
        g.rect(18 + s, top + 4, 20 + s, top + 4, shoe)
        return
    if p.legs == "spread":
        g.poly([(13.5, top), (15.5, top), (13.5, top + 4), (11.5, top + 4)], leg)
        g.poly([(18.5, top), (20.5, top), (22.5, top + 4), (20.5, top + 4)], leg)
        g.rect(10, top + 4, 13, top + 5, shoe)
        g.rect(20, top + 4, 23, top + 5, shoe)
        return
    back, front = {"a": (-1, 1), "b": (1, -1)}.get(p.legs, (0, 0))
    for x0, off in ((14, back), (18, front)):
        x = x0 + off
        g.rect(x, top, x + 1, 28, leg)
        g.rect(x, 29, x + 2, 30, shoe)


def _arm_down(g: Grid, b: Body, sleeve: str, front: bool) -> None:
    x = 21 if front else 11
    t = b.torso_top
    g.rect(x, t, x + 1, t + 3, sleeve)
    g.rect(x, t + 4, x + 1, t + 4, SKIN)


def _back_arm(g: Grid, b: Body, p: Pose, ch: Character) -> None:
    t = b.torso_top
    if p.arms == "up":
        g.poly([(11.5, t + 2), (13.5, t + 2), (11.5, t - 3), (9.5, t - 3)], ch.sleeve)
        g.rect(9, t - 5, 10, t - 4, SKIN)
    elif p.arms == "dangle":
        g.rect(11, t, 12, t + 4, ch.sleeve)
        g.rect(11, t + 5, 12, t + 5, SKIN)
    else:
        _arm_down(g, b, ch.sleeve, front=False)


def _front_arm(g: Grid, b: Body, p: Pose, ch: Character) -> None:
    t = b.torso_top
    if p.arms == "up":
        g.poly([(20.5, t + 2), (22.5, t + 2), (24.5, t - 3), (22.5, t - 3)], ch.sleeve)
        g.rect(23, t - 5, 24, t - 4, SKIN)
    elif p.arms == "dangle":
        g.rect(21, t, 22, t + 4, ch.sleeve)
        g.rect(21, t + 5, 22, t + 5, SKIN)
    elif p.arms == "eat":
        g.poly([(20.5, t + 2), (22.5, t + 2), (22.5, t - 2), (20.5, t - 2)], ch.sleeve)
        g.rect(20, b.mouth_y + 1, 21, b.mouth_y + 1, SKIN)
    else:
        ch.hold(g, b, p)


def _face(g: Grid, b: Body, p: Pose, ch: Character) -> None:
    ey = b.eye_y
    eyes = [BACK_EYE, FRONT_EYE]
    if ch.covered_back_eye and p.eyes not in ("wide",):
        eyes = [FRONT_EYE]
    if ch.lens:
        eyes = []  # the glasses draw the pupils inside the lenses
    for x in eyes:
        if p.eyes in ("open", "wide"):
            g.rect(x, ey, x + 1, ey + 2, INK)
            g.put(x, ey, WHITE)
            if ch.lidded and p.eyes == "open":
                g.put(x, ey, INK)
                g.put(x, ey + 1, WHITE)
                g.put(x + 2, ey, INK)
        elif p.eyes in ("blink", "closed"):
            g.rect(x, ey + 2, x + 1, ey + 2, INK)
            if p.eyes == "closed":
                g.put(x - 1, ey + 1, INK)
        elif p.eyes == "happy":
            g.put_all([(x - 1, ey + 2), (x, ey + 1), (x + 1, ey + 1), (x + 2, ey + 2)], INK)
        elif p.eyes == "side":
            g.rect(x - 1, ey, x + 1, ey, INK)
            g.put_all([(x - 1, ey + 1), (x, ey + 1)], WHITE)
            g.put_all([(x + 1, ey + 1), (x + 1, ey + 2)], INK)
            g.put(x, ey + 2, WHITE)
        if ch.lashes and p.eyes in ("open", "wide", "side") and not ch.lens:
            g.put(x + 2, ey - (0 if ch.lidded else 0), INK)
    # Cheeks, then mouth.
    my = b.mouth_y
    for x, y in ((11, my - 1), (12, my - 1), (22, my - 1)):
        if g.get(x, y) in (SKIN, SKIN_D):
            g.put(x, y, CHEEK)
    lip = ACC if ch.lips else INK
    m = p.mouth
    if m == "smile":
        if ch.lips:
            g.rect(17, my, 18, my, lip)
        else:
            g.put_all([(16, my), (17, my + 1), (18, my)], INK)
    elif m in ("open", "o"):
        g.rect(16, my, 18, my + 1, INK)
        if m == "open":
            g.put(17, my + 1, CHEEK)
        if ch.tooth:
            g.put(16, my, WHITE)
        if m == "o":
            g.put_all([(16, my), (18, my), (16, my + 1), (18, my + 1)], SKIN)
            g.rect(17, my, 17, my + 1, INK)
    elif m == "flat":
        g.rect(16, my, 17, my, lip)
    elif m == "chew":
        g.rect(16, my, 18, my, INK)
        g.put(21, my - 1, CHEEK)
    elif m == "sleep":
        g.put(17, my, INK)


def _glasses(g: Grid, b: Body, p: Pose, ch: Character) -> None:
    """Big glasses: a 5×5 frame per eye, white lens, the pupil inside."""
    ey = b.eye_y
    for x in (BACK_EYE, FRONT_EYE):
        x0, x1, y0, y1 = x - 1, x + 3, ey - 1, ey + 3
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                edge = xx in (x0, x1) or yy in (y0, y1)
                if edge and ch.round_lens and xx in (x0, x1) and yy in (y0, y1):
                    continue  # rounded corners
                g.put(xx, yy, INK if edge else WHITE)
        c = x + 1  # centre column of the lens
        if p.eyes == "open":
            g.rect(c, ey + 1, c, ey + 2, INK)  # dot pupil
        elif p.eyes == "wide":
            g.rect(c, ey, c, ey + 2, INK)
        elif p.eyes == "side":
            g.rect(c + 1, ey + 1, c + 1, ey + 2, INK)  # glancing sideways
            g.rect(x, ey, x + 2, ey, INK)  # heavy lid
        elif p.eyes == "happy":
            g.put_all([(x, ey + 2), (c, ey + 1), (x + 2, ey + 2)], INK)
        else:
            g.rect(x, ey + 2, x + 2, ey + 2, INK)
    g.put(BACK_EYE + 4, ey + 1, INK)  # bridge
    g.put(FRONT_EYE - 2, ey + 1, INK)


# ---- the cast -----------------------------------------------------------------


class Pearl(Character):
    id, name = "pearl", "Pearl"
    personality = "Unbothered, impossibly chic and calm. Treats every crisis like a vibe check and every bug like a mood."
    blurb = "Cool, calm, all-white everything."
    palette = {
        INK: "#2a1f45", SKIN: "#f6d3bd", SKIN_D: "#e0a98e", HAIR: "#2b2638", HAIR_D: "#181425", HAIR_L: "#6d6489",
        CLOTH: "#f7f5fc", CLOTH_D: "#cfc8e0", CLOTH_L: "#ffffff", ACC: "#d8475e", ACC2: "#f3b6c8",
        PROP: "#3a3456", PROP2: "#8f86ad", CHEEK: "#f3a5b5", WHITE: "#ffffff",
    }
    leg, shoe, sleeve = SKIN, CLOTH, SKIN
    lips = True
    lashes = True
    lidded = True

    def outfit(self, g, b, p):
        t, bot = b.torso_top, b.torso_bot
        hem = bot + (1 if b.sit else 2)
        g.rect(14, t - 1, 18, t, CLOTH)  # mock neck
        g.poly([(13, t), (21, t), (22.5, hem + 1), (11.5, hem + 1)], CLOTH)  # A-line mod dress
        g.rect(12, t, 13, t + 1, CLOTH)  # cap sleeves
        g.rect(20, t, 21, t + 1, CLOTH)

    def hold(self, g, b, p):
        _arm_down(g, b, SKIN, front=True)

    def hair(self, g, b, p):
        cx, cy = b.cx, b.cy
        brow = int(cy) - 3
        # Sleek bob: rounded crown, blunt fringe, longer at the back, jaw-length.
        g.ellipse(cx - 0.4, cy - 1.0, 7.8, 6.8, HAIR, only={EMPTY, SKIN})
        g.rect(10, brow + 1, 22, int(cy) + 8, SKIN, only={HAIR})
        g.ellipse(cx, cy, HEAD_RX, HEAD_RY, SKIN, only={EMPTY})
        g.rect(8, brow, 10, int(cy) + 4, HAIR, only={EMPTY, SKIN})  # back of the bob
        g.rect(22, brow, 23, int(cy) + 2, HAIR, only={EMPTY, SKIN})  # front lock
        g.rect(11, brow, 21, brow, HAIR)  # blunt fringe
        top = int(cy) - 7
        g.rect(10, top + 2, 21, top + 2, CLOTH_L, only={HAIR})  # white headband
        # Shine across the crown and down the back, so the bob keeps its shape on dark title bars.
        g.put_all([(12, top), (13, top), (14, top), (11, top + 1), (12, top + 1), (17, top + 1), (18, top + 1)], HAIR_L)
        g.put_all([(9, brow + 1), (9, brow + 2)], HAIR_L)

    def shade(self, g):
        g.rim({CLOTH, CLOTH_D, CLOTH_L}, CLOTH, CLOTH_D, dx=1, dy=1)
        g.rim({HAIR, HAIR_D, HAIR_L}, HAIR, HAIR_D, dx=1, dy=1)
        g.rim({SKIN, SKIN_D, CHEEK}, SKIN, SKIN_D, dx=1, dy=0)

    def details(self, g, b, p):
        y = b.eye_y + 3
        if g.get(9, y + 1) in (HAIR, HAIR_D):
            g.put(9, y + 1, WHITE)  # a pearl earring peeking out


class Archie(Character):
    id, name = "archie", "Archie"
    personality = "Archive-fashion devotee in a coat two sizes too big. Speaks mostly in obscure runway references and has never once hurried."
    blurb = "Oversized coat, undersized urgency."
    palette = {
        INK: "#2a1f45", SKIN: "#f1c9aa", SKIN_D: "#d8a081", HAIR: "#6e5d57", HAIR_D: "#4b3e3a", HAIR_L: "#9a8880",
        CLOTH: "#45434f", CLOTH_D: "#2f2d39", CLOTH_L: "#6b6878", ACC: "#ff7a3a", ACC2: "#ecebf2",
        PROP: "#c6c1d6", PROP2: "#2b2a35", CHEEK: "#e9a1a6", WHITE: "#ffffff",
    }
    leg, shoe, sleeve = PROP2, HAIR_D, CLOTH
    covered_back_eye = True
    lashes = False
    lidded = True

    def outfit(self, g, b, p):
        t, bot = b.torso_top, b.torso_bot
        hem = bot + (2 if b.sit else 3)
        if p.airborne:
            hem = bot + 3
        # Oversized long coat: dropped shoulders, flaring past the knees.
        g.poly([(10.5, t), (22.5, t), (23.5, hem + 1), (9.5, hem + 1)], CLOTH)
        g.rect(15, t - 1, 17, t, ACC2)  # white tee at the collar
        g.rect(13, t - 1, 14, t, CLOTH_L)  # turned-up collar
        g.rect(18, t - 1, 19, t, CLOTH_L)
        g.rect(17, t + 1, 17, hem, CLOTH_D)  # front edge of the coat
        g.rect(11, t + 1, 11, hem - 1, CLOTH_L, only={CLOTH})  # light catching the back

    def hair(self, g, b, p):
        cx, cy = b.cx, b.cy
        brow = int(cy) - 3
        g.ellipse(cx - 0.6, cy - 1.4, 7.6, 6.4, HAIR, only={EMPTY, SKIN})
        g.rect(12, brow + 1, 22, int(cy) + 8, SKIN, only={HAIR})
        g.ellipse(cx, cy, HEAD_RX, HEAD_RY, SKIN, only={EMPTY})
        # Long swept fringe hiding the back eye.
        g.poly([(10, brow - 2), (19, brow - 1), (17.5, brow + 2), (16.5, brow + 5), (12, brow + 5), (10, brow + 3)], HAIR)
        g.rect(8, brow, 10, int(cy) + 5, HAIR, only={EMPTY, SKIN})
        g.rect(22, brow - 1, 23, brow + 2, HAIR, only={EMPTY, SKIN})
        top = int(cy) - 7
        g.put_all([(11, top), (14, top - 1), (17, top - 1), (20, top)], HAIR)  # messy tufts
        g.put_all([(12, top + 1), (13, top + 1), (12, top + 2), (15, top)], HAIR_L)
        g.rect(13, brow + 3, 15, brow + 3, HAIR_D, only={HAIR})  # strand shadow

    def hold(self, g, b, p):
        # Arm bent, cigarette held out in front at chest height.
        t = b.torso_top
        g.poly([(20.5, t + 1), (22.5, t + 1), (24.5, t + 4), (22.5, t + 5)], CLOTH)
        g.rect(23, t + 3, 24, t + 3, SKIN)

    def details(self, g, b, p):
        if p.arms != "prop":
            return
        y = b.torso_top + 3
        g.rect(25, y, 26, y, WHITE)  # cigarette
        g.put(27, y, ACC)  # ember
        g.put_all([(25, y + 1), (26, y + 1), (27, y + 1)], INK)  # a shadow so it reads on white windows
        if p.legs == "stand" and p.mouth != "sleep" and not p.airborne and p.eyes != "side" or p.sit and p.mouth != "sleep":
            # A tiny smoke wisp that drifts between frames (idle and sit).
            if p.frame == 0:
                g.put_all([(27, y - 2), (28, y - 3)], PROP)
                g.put_all([(28, y - 5), (27, y - 6)], CLOTH_L)
            else:
                g.put_all([(28, y - 2), (27, y - 3)], PROP)
                g.put_all([(27, y - 5), (28, y - 7)], CLOTH_L)


class Dewey(Character):
    id, name = "dewey", "Dewey"
    personality = "A princess of the reading nook. Curtsies, pushes up her glasses, then tells you a fun fact about octopuses."
    blurb = "Royalty of the reading nook."
    palette = {
        INK: "#2a1f45", SKIN: "#f8d4bf", SKIN_D: "#e2a98f", HAIR: "#8f4f31", HAIR_D: "#673620", HAIR_L: "#c27b52",
        CLOTH: "#ff9ccd", CLOTH_D: "#df6aa6", CLOTH_L: "#ffc9e4", ACC: "#ffd24a", ACC2: "#ff4f8b",
        PROP: "#4a78db", PROP2: "#fff3dc", CHEEK: "#ff9fb2", WHITE: "#ffffff",
    }
    leg, shoe, sleeve = SKIN, ACC2, CLOTH
    lens, round_lens = True, True
    tooth = True
    lashes = False
    lidded = False

    def behind(self, g, b, p):
        cy = b.cy
        g.poly([(9.5, cy), (23, cy), (23.5, cy + 11), (9, cy + 11)], HAIR)  # long hair down her back

    def outfit(self, g, b, p):
        t, bot = b.torso_top, b.torso_bot
        g.rect(14, t, 19, bot - 2, CLOTH)  # bodice
        hem = bot + (1 if b.sit else 4)
        if p.airborne:
            hem = bot + 3
        g.poly([(13.5, bot - 3), (19.5, bot - 3), (23.5, hem + 1), (9.5, hem + 1)], CLOTH)  # bell skirt
        g.ellipse(12.5, t + 1.0, 1.9, 1.7, CLOTH_L)  # puff sleeves
        g.ellipse(20.5, t + 1.0, 1.9, 1.7, CLOTH_L)

    def hair(self, g, b, p):
        cx, cy = b.cx, b.cy
        brow = int(cy) - 3
        g.ellipse(cx - 0.3, cy - 1.3, 7.6, 6.4, HAIR, only={EMPTY, SKIN})
        g.rect(11, brow + 1, 22, int(cy) + 8, SKIN, only={HAIR})
        g.ellipse(cx, cy, HEAD_RX, HEAD_RY, SKIN, only={EMPTY})
        g.poly([(10, brow - 2), (20, brow - 2), (18.5, brow + 1), (14, brow), (11, brow + 2)], HAIR)  # swept bangs
        g.rect(8, brow, 10, int(cy) + 7, HAIR, only={EMPTY, SKIN})
        g.rect(22, brow, 23, int(cy) + 5, HAIR, only={EMPTY, SKIN})
        top = int(cy) - 7
        g.put_all([(12, top + 1), (13, top + 1), (12, top + 2)], HAIR_L)
        # Tiara.
        g.rect(13, top - 1, 19, top - 1, ACC)
        g.put_all([(13, top - 2), (16, top - 3), (16, top - 2), (19, top - 2)], ACC)
        g.put(16, top - 1, ACC2)

    def hold(self, g, b, p):
        # A book hugged to her chest.
        t = b.torso_top
        g.rect(15, t + 1, 21, t + 4, PROP)
        g.rect(21, t + 1, 21, t + 4, PROP2)  # page edges
        g.rect(20, t + 2, 21, t + 3, SKIN)  # her hand over it

    def details(self, g, b, p):
        if p.arms == "prop":
            g.rect(16, b.torso_top + 2, 18, b.torso_top + 2, PROP2)  # title on the cover


class Kernel(Character):
    id, name = "kernel", "Kernel"
    personality = "Wholesome mega-nerd in a mustard cardigan. Brings snacks to standup and has 47 tabs open about keyboards."
    blurb = "Cardigan, laptop, pure good vibes."
    palette = {
        INK: "#2a1f45", SKIN: "#eab993", SKIN_D: "#cc8f6c", HAIR: "#4a342b", HAIR_D: "#2e201a", HAIR_L: "#76574a",
        CLOTH: "#e3aa3e", CLOTH_D: "#b9822a", CLOTH_L: "#f6d27a", ACC: "#4fb3a7", ACC2: "#3b4c7d",
        PROP: "#c9cfdb", PROP2: "#8d95a8", CHEEK: "#ef9a95", WHITE: "#ffffff",
    }
    leg, shoe, sleeve = ACC2, WHITE, CLOTH
    lens, round_lens = True, False
    lashes = False
    lidded = False

    def outfit(self, g, b, p):
        t, bot = b.torso_top, b.torso_bot
        g.rect(13, t, 20, bot + 1, CLOTH)  # cardigan
        g.rect(15, t, 17, bot + 1, ACC)  # tee underneath
        g.put_all([(14, t + 2), (14, t + 4)], CLOTH_D)  # buttons

    def hair(self, g, b, p):
        cx, cy = b.cx, b.cy
        brow = int(cy) - 3
        g.ellipse(cx - 0.2, cy - 1.6, 7.8, 6.6, HAIR, only={EMPTY, SKIN})
        g.rect(11, brow + 1, 22, int(cy) + 8, SKIN, only={HAIR})
        g.ellipse(cx, cy, HEAD_RX, HEAD_RY, SKIN, only={EMPTY})
        g.rect(8, brow, 10, int(cy) + 3, HAIR, only={EMPTY, SKIN})
        g.rect(22, brow, 23, brow + 2, HAIR, only={EMPTY, SKIN})
        # Curly mop: clumps along the fringe and a bumpy crown.
        g.put_all([(12, brow + 1), (13, brow + 1), (16, brow + 1), (17, brow + 1), (20, brow + 1), (21, brow + 1)], HAIR)
        top = int(cy) - 8
        g.put_all([(9, top + 3), (11, top + 1), (14, top), (18, top), (21, top + 1), (23, top + 3)], HAIR)
        # Curl shadows inside the mop.
        g.put_all([(12, top + 3), (15, top + 2), (18, top + 3), (14, brow - 1), (19, brow - 1), (10, brow + 1)], HAIR_D)
        g.put_all([(12, top + 2), (13, top + 2), (16, top + 1)], HAIR_L)

    def hold(self, g, b, p):
        # A closed laptop tucked against his chest.
        t = b.torso_top
        g.rect(14, t + 1, 22, t + 3, PROP)
        g.rect(14, t + 3, 22, t + 3, PROP2)
        g.rect(21, t + 1, 22, t + 2, SKIN)

    def details(self, g, b, p):
        if p.arms == "prop":
            g.put(17, b.torso_top + 2, CHEEK)  # a sticker on the lid


CAST = [Pearl(), Archie(), Dewey(), Kernel()]

# Pearl's optional retro cat-eye sunglasses (white frames, dark lenses), drawn
# over her face at the "eyes" anchor in every frame.
SUNGLASSES = [
    "1..........1",
    "11111..11111",
    ".1cc1111cc1.",
    ".1fd1..1fd1.",
    "..11....11..",
]


def frames_for(ch: Character) -> tuple[dict[str, list[list[str]]], dict[str, list]]:
    frames: dict[str, list[list[str]]] = {}
    anchors: dict[str, list] = {}
    for anim, poses in POSES.items():
        frames[anim], anchors[anim] = [], []
        for pose in poses:
            rows, anchor = draw(ch, pose)
            frames[anim].append(rows)
            anchors[anim].append(list(anchor))
    return frames, anchors


def pet_json(ch: Character) -> dict:
    frames, anchors = frames_for(ch)
    pet = {
        "id": ch.id,
        "name": ch.name,
        "personality": ch.personality,
        "blurb": ch.blurb,
        "description": "nibble built-in cast",
        "model": "hand-drawn",
        "palette": ch.palette,
        "frames": frames,
        "lines": LINES[ch.id],
    }
    if isinstance(ch, Pearl):
        pet["anchors"] = {"eyes": anchors}
        pet["accessories"] = {"glasses": {"label": "Glasses", "anchor": "eyes", "default": True, "sprite": SUNGLASSES}}
    return pet


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="draw one character")
    args = ap.parse_args()
    for ch in CAST:
        if args.only and ch.id != args.only:
            continue
        path = OUT / f"{ch.id}.json"
        path.write_text(json.dumps(pet_json(ch), indent=1) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
