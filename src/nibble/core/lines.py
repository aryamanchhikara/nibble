"""Picking what a pet says, with generic fallbacks for pets that lack a category.

Older pets (or a pet generated before a category existed) still get to talk:
anything missing comes from these built-in lines.
"""

from __future__ import annotations

import random

from .spec import PetSpec

GENERIC: dict[str, list[str]] = {
    "cheers": [
        "keep going, you're doing great!",
        "you got this!",
        "look at you go!",
        "one step at a time. proud of you.",
        "this is coming together nicely",
        "you're on a roll!",
        "tiny progress is still progress!",
        "deep breath. you've totally got this.",
        "rooting for you over here!",
        "future you is gonna be so grateful",
    ],
    "bored": [
        "okay, you win",
        "too fast for me",
        "*yawns* never mind",
        "i'll catch it next time",
    ],
    "quips": [
        "hi!",
        "what are we doing today?",
        "nice window you've got here",
        "*looks around curiously*",
        "boop!",
        "i'm just a little guy",
        "is it snack time yet?",
        "hehe",
    ],
}


class LinePicker:
    """Draws lines without repeating one until the whole category is used up."""

    def __init__(self, spec: PetSpec, rng: random.Random | None = None):
        self.spec = spec
        self.rng = rng or random.Random()
        self._bags: dict[str, list[str]] = {}
        self._last: dict[str, str] = {}

    def options(self, category: str) -> list[str]:
        return self.spec.lines_for(category) or GENERIC.get(category, [])

    def pick(self, category: str) -> str | None:
        bag = self._bags.get(category)
        if not bag:
            bag = list(self.options(category))
            if not bag:
                return None
            self.rng.shuffle(bag)
            # Don't start a fresh round with the line we just said.
            if len(bag) > 1 and bag[-1] == self._last.get(category):
                bag[0], bag[-1] = bag[-1], bag[0]
            self._bags[category] = bag
        line = bag.pop()
        self._last[category] = line
        return line
