"""The pet definition: who it is, its palette, its frames, and what it says."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from importlib import resources
from typing import Any, Iterable

from .sprites import Frame, SpriteMetrics, bottom_row, metrics, overlay, shift_down

# Animation name -> number of frames the pet must provide.
ANIMATIONS: dict[str, int] = {
    "idle": 2,
    "walk": 4,
    "sit": 1,
    "sleep": 2,
    "happy": 2,
    "eat": 2,
    "dangle": 2,
    "fall": 1,
    "sideeye": 1,
}

# What a pet can say: category -> (fewest, most) lines. The validator and the
# generation prompt are both built from these, so they never disagree.
LINES: dict[str, tuple[int, int]] = {
    "quips": (8, 12),
    "petting": (5, 8),
    "hungry": (5, 8),
    "fed": (4, 6),
    "bored": (3, 6),
    "cheers": (8, 10),  # encouragement while you work
}
NESTED_LINES: dict[str, dict[str, tuple[int, int]]] = {
    "chatter": {"openers": (4, 6), "replies": (4, 6)},
    "reactions": {"coding": (3, 5), "terminal": (3, 5), "social": (3, 5)},
}
MAX_LINE_LENGTH = 60  # what fits in a speech bubble

# Frames used to find where the pet's feet are and how big it is when standing.
STANDING = ("idle", "walk", "sit")
# Poses that should touch the ground. Airborne ones (happy hops, dangle, fall)
# are left as drawn.
GROUNDED = ("idle", "walk", "sit", "sleep", "eat", "sideeye")


# Where an accessory goes in one frame: grid (x, y) of its top-left, or None
# to leave it off that frame.
Anchor = tuple[int, int] | None


@dataclass(frozen=True)
class Accessory:
    """An optional overlay (glasses, a hat...) drawn at a named anchor in every frame.

    The pet's "anchors" table gives that point for every frame of every
    animation, so the overlay follows the head through bobs, jumps and naps.
    Mirroring and peeking happen after it's drawn on, so it lines up there too.
    """

    name: str
    label: str
    anchor: str
    sprite: Frame
    default: bool = True


@dataclass(frozen=True)
class PetSpec:
    id: str
    name: str
    personality: str
    palette: dict[str, str]
    frames: dict[str, tuple[Frame, ...]]
    lines: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    model: str = ""
    blurb: str = ""  # one line for the home page
    anchors: dict[str, dict[str, tuple[Anchor, ...]]] = field(default_factory=dict)
    accessories: dict[str, Accessory] = field(default_factory=dict)

    def frame(self, animation: str, index: int, worn: Iterable[str] = ()) -> Frame:
        """A frame with the named accessories drawn on."""
        name = animation if self.frames.get(animation) else "idle"
        frames = self.frames[name]
        i = index % len(frames)
        frame = frames[i]
        wanted = set(worn)
        for acc in self.accessories.values():  # declaration order = drawing order
            if acc.name in wanted:
                at = self.anchor(acc.anchor, name, i)
                if at is not None:
                    frame = overlay(frame, acc.sprite, *at)
        return frame

    def anchor(self, anchor: str, animation: str, index: int) -> Anchor:
        points = self.anchors.get(anchor, {}).get(animation, ())
        return points[index] if index < len(points) else None

    @property
    def default_worn(self) -> frozenset[str]:
        return frozenset(a.name for a in self.accessories.values() if a.default)

    def lines_for(self, category: str) -> list[str]:
        """Lines for "cheers" or a nested category like "reactions.coding"."""
        node: Any = self.lines
        for part in category.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        return [line for line in node if isinstance(line, str)] if isinstance(node, list) else []

    def metrics(self) -> SpriteMetrics:
        return metrics([f for name in STANDING for f in self.frames.get(name, ())])

    def feet_on_ground(self) -> PetSpec:
        """Shift grounded poses so their lowest pixel sits on the standing feet line.

        Hand-drawn and LLM-drawn frames are often a pixel or two off, which
        would make the pet float above (or sink into) the window edge.
        """
        feet = self.metrics().feet_row
        frames = dict(self.frames)
        anchors = {k: dict(v) for k, v in self.anchors.items()}
        for name in GROUNDED:
            aligned = []
            for i, frame in enumerate(frames.get(name, ())):
                bottom = bottom_row(frame)
                moved = shift_down(frame, feet - bottom) if bottom is not None else frame
                aligned.append(moved)
                dy = (bottom_row(moved) or 0) - (bottom or 0)
                if dy:  # accessories move with the frame
                    for table in anchors.values():
                        points = list(table.get(name, ()))
                        if i < len(points) and points[i] is not None:
                            points[i] = (points[i][0], points[i][1] + dy)
                            table[name] = tuple(points)
            if name in frames:
                frames[name] = tuple(aligned)
        return replace(self, frames=frames, anchors=anchors)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PetSpec:
        return cls(
            id=data["id"],
            name=data["name"],
            personality=data.get("personality", ""),
            palette=dict(data["palette"]),
            frames={k: tuple(tuple(f) for f in v) for k, v in data["frames"].items()},
            lines=data.get("lines", {}),
            description=data.get("description", ""),
            model=data.get("model", ""),
            blurb=data.get("blurb", ""),
            anchors={
                name: {anim: tuple(tuple(pt) if pt is not None else None for pt in pts) for anim, pts in table.items()}
                for name, table in data.get("anchors", {}).items()
            },
            accessories={
                name: Accessory(name, a.get("label", name), a["anchor"], tuple(a["sprite"]), bool(a.get("default", True)))
                for name, a in data.get("accessories", {}).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "personality": self.personality,
            "description": self.description,
            "model": self.model,
            "palette": self.palette,
            "frames": {k: [list(f) for f in v] for k, v in self.frames.items()},
            "lines": self.lines,
        }
        if self.blurb:
            out["blurb"] = self.blurb
        if self.anchors:
            out["anchors"] = {
                name: {anim: [list(pt) if pt is not None else None for pt in pts] for anim, pts in table.items()}
                for name, table in self.anchors.items()
            }
        if self.accessories:
            out["accessories"] = {
                a.name: {"label": a.label, "anchor": a.anchor, "default": a.default, "sprite": list(a.sprite)}
                for a in self.accessories.values()
            }
        return out


def load_builtin(pet_id: str) -> PetSpec:
    """Load a pet shipped inside the package (nibble/pets/<id>.json)."""
    text = resources.files("nibble.pets").joinpath(f"{pet_id}.json").read_text("utf-8")
    return PetSpec.from_dict(json.loads(text))
