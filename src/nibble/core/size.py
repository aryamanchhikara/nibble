"""How big the pet is drawn, kept pixel-perfect on every display.

A sprite pixel must cover a whole number of device pixels or nearest-neighbour
scaling turns into uneven, shimmering pixels. On a Retina display (backing
scale 2) every size works as-is: 1.5 pt is exactly 3 device pixels. On a
non-Retina display (backing scale 1) the requested scale is rounded to the
nearest whole number, with a tie (Small's 1.5) going down so Small stays
smaller than Medium.

Behaviour numbers measured in points (walk speed, chase radius...) are tuned
for Large and scaled by size_factor so a small pet doesn't look like it's
sprinting.
"""

from __future__ import annotations

import math
from dataclasses import replace
from enum import Enum

from .sprites import GRID

REFERENCE_SCALE = 3.0  # Large: the size behaviour was tuned at


class Size(Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

    @property
    def scale(self) -> float:
        """Points per sprite pixel."""
        return {"small": 1.5, "medium": 2.0, "large": 3.0}[self.value]

    @property
    def label(self) -> str:
        return f"{self.value.capitalize()} ({GRID * self.scale:g} pt)"


DEFAULT = Size.MEDIUM


def parse(value: str | None) -> Size:
    try:
        return Size(value)
    except ValueError:
        return DEFAULT


def crisp_scale(requested: float, backing: float) -> float:
    """The closest scale at which one sprite pixel is a whole number of device pixels."""
    if backing <= 0:
        backing = 1.0
    device = requested * backing
    whole = math.floor(device)
    if device - whole > 0.5 + 1e-9:
        whole += 1  # round to nearest; an exact .5 rounds down
    return max(1, whole) / backing


def size_factor(scale: float) -> float:
    """How big this pet is relative to the size the behaviour was tuned at."""
    return scale / REFERENCE_SCALE


def scale_fields(obj, names: tuple[str, ...], factor: float):
    """A copy of a frozen dataclass with the named point-valued fields multiplied."""
    if factor == 1:
        return obj
    changes = {}
    for name in names:
        value = getattr(obj, name)
        changes[name] = tuple(v * factor for v in value) if isinstance(value, tuple) else value * factor
    return replace(obj, **changes)
