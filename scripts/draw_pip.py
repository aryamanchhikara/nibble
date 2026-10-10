"""Draw Pip, nibble's built-in pet, and write src/nibble/pets/pip.json.

Pip is drawn from shapes (body ellipse, ears, tail, auto-outline, then the
face) so every frame stays on-model. Run: uv run python scripts/draw_pip.py
"""

from __future__ import annotations

import json
from pathlib import Path

N = 32
OUT = Path(__file__).resolve().parents[1] / "src" / "nibble" / "pets" / "pip.json"

OUTLINE, BODY, SHADE, LIGHT, PINK, WHITE = "1", "2", "3", "4", "5", "6"
PALETTE = {
    OUTLINE: "#2a1f45",
    BODY: "#b9a3ff",
    SHADE: "#8c6fe0",
    LIGHT: "#e6deff",
    PINK: "#ff8fb8",
    WHITE: "#ffffff",
}


def blank() -> list[list[str]]:
    return [["."] * N for _ in range(N)]


def put(g, x, y, c):
    if 0 <= x < N and 0 <= y < N:
        g[y][x] = c


def ellipse(g, cx, cy, rx, ry, c, only=None):
    for y in range(N):
        for x in range(N):
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0:
                if only is None or g[y][x] in only:
                    g[y][x] = c


def triangle(g, a, b, c, color):
    def side(p, q, r):
        return (p[0] - r[0]) * (q[1] - r[1]) - (q[0] - r[0]) * (p[1] - r[1])

    for y in range(N):
        for x in range(N):
            p = (x + 0.5, y + 0.5)
            d1, d2, d3 = side(p, a, b), side(p, b, c), side(p, c, a)
            neg = d1 < 0 or d2 < 0 or d3 < 0
            pos = d1 > 0 or d2 > 0 or d3 > 0
            if not (neg and pos):
                g[y][x] = color


def outline(g, color):
    src = [row[:] for row in g]
    for y in range(N):
        for x in range(N):
            if src[y][x] != ".":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < N and 0 <= ny < N and src[ny][nx] != ".":
                    g[y][x] = color
                    break


def draw(
    *,
    cx=16.0,
    cy=21.5,
    rx=11.5,
    ry=8.5,
    dy=0,
    ear_dy=0.0,
    ear_tip_dy=0.0,
    face_dy=0,
    eyes="open",
    mouth="v",
    cheeks="dot",
    feet=((11.5, 29.5), (20.5, 29.5)),
    foot_r=(2.5, 1.2),
    tail=True,
) -> list[str]:
    g = blank()
    cy += dy

    # Body, ears and tail in one silhouette so the outline wraps all of them.
    ellipse(g, cx, cy, rx, ry, BODY)
    base_y = cy - ry + 2.0 + ear_dy
    tip_y = base_y - 7.0 + ear_tip_dy
    left_ear = ((cx - 8.5, base_y + 1.0), (cx - 2.5, base_y - 0.5), (cx - 7.5, tip_y))
    right_ear = ((cx + 2.5, base_y - 0.5), (cx + 8.5, base_y + 1.0), (cx + 7.5, tip_y))
    for ear in (left_ear, right_ear):
        triangle(g, *ear, BODY)
    if tail:
        tx, ty = round(cx - rx), round(cy)
        for ddx, ddy in ((0, 1), (0, 0), (-1, 0), (-1, -1), (-2, -1), (-2, -2), (-2, -3), (-2, -4), (-1, -4), (-1, -5)):
            put(g, tx + ddx, ty + ddy, BODY)

    # Shade the bottom and right rim, then a highlight on the upper left.
    for y in range(N):
        for x in range(N):
            if g[y][x] == BODY and ((y + 0.5 - cy) / ry > 0.5 or (x + 0.5 - cx) / rx > 0.86):
                g[y][x] = SHADE
    ellipse(g, cx - rx * 0.5, cy - ry * 0.55, 2.2, 1.1, LIGHT, only={BODY})
    for ear in (left_ear, right_ear):
        (ax, ay), (bx, by), (tx, ty) = ear
        mx, my = (ax + bx + tx) / 3, (ay + by + ty) / 3
        if tip_y < base_y - 5.5:  # tucked-in ears have no room for a pink inside
            inner = [(mx + (px - mx) * 0.55, my + (py - my) * 0.55 + 0.8) for px, py in ear]
            triangle(g, *inner, PINK)

    outline(g, OUTLINE)

    # Feet sit in front of the body with their own outline.
    for fx, fy in feet or ():
        fy += 0
        ellipse(g, fx, fy, foot_r[0] + 1, foot_r[1] + 1, OUTLINE)
    for fx, fy in feet or ():
        ellipse(g, fx, fy, foot_r[0], foot_r[1], SHADE)

    # Face, looking right.
    ey = 19 + dy + face_dy
    for x0 in (15, 21):
        if eyes == "open":
            for yy in range(ey, ey + 3):
                put(g, x0, yy, OUTLINE)
                put(g, x0 + 1, yy, OUTLINE)
            put(g, x0, ey, WHITE)
        elif eyes == "closed":
            put(g, x0, ey + 2, OUTLINE)
            put(g, x0 + 1, ey + 2, OUTLINE)
        elif eyes == "happy":
            put(g, x0 - 1, ey + 2, OUTLINE)
            put(g, x0, ey + 1, OUTLINE)
            put(g, x0 + 1, ey + 1, OUTLINE)
            put(g, x0 + 2, ey + 2, OUTLINE)
        elif eyes == "wide":
            for yy in range(ey - 1, ey + 3):
                for xx in range(x0 - 1, x0 + 2):
                    put(g, xx, yy, OUTLINE)
            put(g, x0 - 1, ey - 1, WHITE)
            put(g, x0, ey - 1, WHITE)
        elif eyes == "side":
            # Heavy lid, white of the eye, pupil shoved to the right.
            for xx in range(x0 - 1, x0 + 2):
                put(g, xx, ey, OUTLINE)
            for yy in (ey + 1, ey + 2):
                put(g, x0 - 1, yy, WHITE)
                put(g, x0, yy, WHITE)
                put(g, x0 + 1, yy, OUTLINE)
            put(g, x0 - 1, ey + 3, OUTLINE)
            put(g, x0, ey + 3, OUTLINE)

    my = 23 + dy + face_dy
    if cheeks:
        for x in (13, 14, 23, 24):
            put(g, x, my, PINK)
            if cheeks == "puff":
                put(g, x, my + 1, PINK)
    if mouth == "v":
        put(g, 18, my, OUTLINE)
        put(g, 19, my + 1, OUTLINE)
        put(g, 20, my, OUTLINE)
    elif mouth == "open":
        for xx in (18, 19, 20):
            put(g, xx, my, OUTLINE)
            put(g, xx, my + 1, OUTLINE)
        put(g, 19, my + 1, PINK)
    elif mouth == "wide":
        for yy in (my, my + 1, my + 2):
            for xx in (18, 19, 20):
                put(g, xx, yy, OUTLINE)
        put(g, 19, my + 2, PINK)
    elif mouth == "o":
        for xx in (18, 19):
            put(g, xx, my, OUTLINE)
            put(g, xx, my + 1, OUTLINE)
    elif mouth == "flat":
        for xx in (18, 19, 20):
            put(g, xx, my, OUTLINE)

    return ["".join(row) for row in g]


def frames() -> dict[str, list[list[str]]]:
    sleep = dict(cy=24.8, rx=12.5, ry=6.2, ear_dy=1.0, ear_tip_dy=2.0, face_dy=4, eyes="closed", mouth="none", feet=None)
    dangle = dict(cy=19.5, rx=10.0, ry=9.5, ear_tip_dy=-1.5, face_dy=-1, eyes="wide", mouth="o", foot_r=(2.0, 1.2))
    return {
        "idle": [draw(), draw(eyes="closed")],
        "walk": [
            draw(feet=((10.5, 29.5), (21.5, 29.5))),
            draw(dy=-1, feet=((12.5, 29.5), (20.5, 28.5))),
            draw(feet=((13.5, 29.5), (18.5, 29.5))),
            draw(dy=-1, feet=((11.5, 28.5), (19.5, 29.5))),
        ],
        "sit": [draw(cy=22.5, rx=12.5, ry=7.5, face_dy=1, feet=((19.5, 29.8), (24.0, 29.8)), foot_r=(2.0, 1.0))],
        "sleep": [draw(**sleep), draw(**{**sleep, "cy": 24.6, "ry": 6.6})],
        "happy": [
            draw(eyes="happy", mouth="open"),
            draw(dy=-3, eyes="happy", mouth="open", feet=((11.5, 27.0), (20.5, 27.0))),
        ],
        "eat": [draw(eyes="closed", mouth="wide"), draw(eyes="happy", mouth="flat", cheeks="puff")],
        "dangle": [
            draw(**dangle, feet=((12.5, 29.5), (19.5, 30.0))),
            draw(**dangle, feet=((13.5, 30.0), (20.5, 29.5))),
        ],
        "fall": [draw(cy=20.0, rx=11.0, ry=9.0, ear_tip_dy=-1.0, eyes="wide", mouth="o", feet=((8.5, 28.5), (23.5, 28.5)))],
        "sideeye": [draw(eyes="side", mouth="flat")],
    }


LINES = {
    "quips": [
        "every window is a new country!",
        "i've mapped 3 windows today. a record.",
        "what's behind this tab? adventure??",
        "the view from up here is amazing",
        "*sniffs the title bar*",
        "do windows have snacks?",
        "i'm an explorer. a small one.",
        "boop! hi! hello!",
        "this edge is very walkable. 10/10",
        "can we visit the dock later?",
    ],
    "petting": [
        "purrrr... the good spot!",
        "more pets. that's an order.",
        "you have very nice hands",
        "*happy fluff noises*",
        "best. human. ever.",
        "okay one more. okay two more.",
    ],
    "hungry": [
        "my tummy is rumbling...",
        "explorers need snacks!",
        "is that... a crumb? no. sadness.",
        "feed me and i'll map a new window",
        "running low on snack fuel...",
        "i could eat a whole menu bar",
    ],
    "fed": [
        "nom nom nom!",
        "fuel for adventure!",
        "that hit the spot, thank you!",
        "*happy chewing*",
        "best snack in all the windows",
    ],
    "bored": [
        "okay that's enough chasing",
        "you win this round, cursor",
        "*yawns* exploring something else",
        "too fast for me today",
    ],
    "cheers": [
        "keep going, explorer!",
        "you're charting new territory!",
        "look at you go!! so proud",
        "one more step, then another!",
        "this code is a whole new country",
        "you're doing amazing, honestly",
        "brave little coder, keep at it!",
        "every bug squashed is a map drawn",
        "i believe in you! (i'm small but sure)",
        "adventure mode: ON. you got this!",
    ],
    "chatter": {
        "openers": [
            "found any good windows lately?",
            "hey! wanna explore together?",
            "i saw a REALLY big window earlier",
            "psst. the dock is down there.",
            "have you tried the title bars?",
        ],
        "replies": [
            "ooh, tell me everything!",
            "yes! adventure buddies!",
            "no way, really??",
            "i'm writing that down",
            "let's go look right now!",
        ],
    },
    "reactions": {
        "coding": [
            "ooh, code! let's build something!",
            "i love watching you type",
            "a new world made of brackets!",
            "go go go, code explorer!",
        ],
        "terminal": [
            "the hacker window! so mysterious",
            "green text means it worked, right?",
            "type the magic words!",
            "ooh, a command line adventure",
        ],
        "social": [
            "hmm... just a quick peek, right?",
            "*side-eyes the feed*",
            "the adventure was in the code...",
            "scrolling again? suspicious.",
        ],
    },
}


def main() -> None:
    pet = {
        "id": "pip",
        "name": "Pip",
        "personality": "A curious little lilac fluffball who thinks every window is a new country to explore.",
        "description": "nibble's built-in pet",
        "model": "hand-drawn",
        "palette": PALETTE,
        "frames": frames(),
        "lines": LINES,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pet, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
