"""Per-tick facts about the user that a pet's brain reacts to."""

from __future__ import annotations

from dataclasses import dataclass

FAR_AWAY = (-1e9, -1e9)


@dataclass(frozen=True)
class Context:
    cursor: tuple[float, float] = FAR_AWAY
    mouse_down: bool = False  # any mouse button held, anywhere
    pressing_pet: bool = False  # ...and it's held on this pet
    user_idle: float = 0.0  # seconds since the last keyboard/mouse input
    in_call: bool = False  # stay still and silent
    can_speak: bool = True  # False in Quiet mode and during calls
