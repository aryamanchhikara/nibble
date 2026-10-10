"""The home page (character select): layout, state and input, with no AppKit.

The page is a 384×216 pixel canvas. The window shows it scaled by a whole
number, so all coordinates here are canvas pixels, y down.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .spec import PetSpec

W, H = 384, 216
CARD_W, CARD_H, CARD_GAP = 76, 112, 10
CARD_Y = 30
CARDS_X = (W - (4 * CARD_W + 3 * CARD_GAP)) // 2
BOUNCE = (0, -3, -4, -3, -1, 0)  # card offset per animation step after selecting it
BOUNCE_STEP = 0.05  # seconds per step
HAPPY_FOR = 0.9  # the newly selected pet cheers this long

# "Describe your own pet…" (LLM-generated pets, needs an OpenRouter key). Off for
# v0.1: the page shows a plain "coming soon" note instead and never asks for a key.
CUSTOM_PETS = False


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


START = Box(144, 152, 96, 22)
LINK = Box(132, 200, 120, 12)
SOUND = Box(362, 5, 16, 12)
DIALOG = Box(82, 62, 220, 84)
DIALOG_BUTTONS = ("swap", "add", "back")


def card_box(i: int) -> Box:
    return Box(CARDS_X + i * (CARD_W + CARD_GAP), CARD_Y, CARD_W, CARD_H)


def toggle_box(i: int) -> Box:
    """The accessory switch on card i (only shown for pets that have one)."""
    c = card_box(i)
    return Box(c.x + 6, c.y + 96, c.w - 12, 11)


def dialog_button(i: int) -> Box:
    return Box(DIALOG.x + 12 + i * 68, DIALOG.y + 56, 60, 18)


# ---- what the window should do -------------------------------------------------


@dataclass(frozen=True)
class Action:
    kind: str  # start, close, describe, sound, wardrobe, sfx
    pet_id: str = ""
    worn: frozenset[str] = frozenset()
    mode: str = ""  # start: new, swap or add
    on: bool = False
    name: str = ""  # sfx: move, toggle, start, back, open


@dataclass
class Dialog:
    message: tuple[str, ...]
    focus: int = 0


@dataclass
class HomeModel:
    pets: list[PetSpec]
    wardrobe: dict[str, frozenset[str]] = field(default_factory=dict)
    sound: bool = False
    running: list[str] = field(default_factory=list)  # names of pets already out
    selected: int = 0
    selected_at: float = -10.0
    dialog: Dialog | None = None
    toast: tuple[str, float] | None = None
    version: int = 0  # bumped whenever something static on the page changes
    custom_pets: bool = CUSTOM_PETS  # show the "Describe your own pet…" link

    def __post_init__(self) -> None:
        for pet in self.pets:
            self.wardrobe.setdefault(pet.id, pet.default_worn)

    @property
    def pet(self) -> PetSpec:
        return self.pets[self.selected]

    def worn(self, pet: PetSpec) -> frozenset[str]:
        return self.wardrobe.get(pet.id, pet.default_worn)

    def bounce(self, now: float) -> int:
        step = int((now - self.selected_at) / BOUNCE_STEP)
        return BOUNCE[step] if 0 <= step < len(BOUNCE) else 0

    def cheering(self, now: float) -> bool:
        return now - self.selected_at < HAPPY_FOR

    # ---- input ------------------------------------------------------------

    def press(self, key: str, now: float) -> list[Action]:
        """key: left, right, up, down, enter, space, escape, g, m."""
        if self.dialog is not None:
            return self._dialog_key(key)
        if key in ("left", "up"):
            return self._select(self.selected - 1, now)
        if key in ("right", "down"):
            return self._select(self.selected + 1, now)
        if key == "enter":
            return self._start()
        if key in ("space", "g"):
            return self._toggle_accessory(self.selected)
        if key == "m":
            return self._toggle_sound()
        if key == "escape":
            return [Action("close")]
        return []

    def click(self, x: float, y: float, now: float) -> list[Action]:
        if self.dialog is not None:
            for i, name in enumerate(DIALOG_BUTTONS):
                if dialog_button(i).contains(x, y):
                    return self._choose(name)
            return []
        if SOUND.contains(x, y):
            return self._toggle_sound()
        if START.contains(x, y):
            return self._start()
        if self.custom_pets and LINK.contains(x, y):
            return [Action("describe")]
        for i, pet in enumerate(self.pets):
            if pet.accessories and toggle_box(i).contains(x, y):
                acts = [] if i == self.selected else self._select(i, now)
                return acts + self._toggle_accessory(i)
            if card_box(i).contains(x, y):
                return self._select(i, now) if i != self.selected else []
        return []

    def show_toast(self, text: str, now: float, seconds: float = 3.5) -> None:
        self.toast = (text, now + seconds)

    # ---- internals ----------------------------------------------------------

    def _changed(self) -> None:
        self.version += 1

    def _select(self, i: int, now: float) -> list[Action]:
        self.selected = i % len(self.pets)
        self.selected_at = now
        self._changed()
        return [Action("sfx", name="move")]

    def _toggle_accessory(self, i: int) -> list[Action]:
        pet = self.pets[i]
        if not pet.accessories:
            return []
        name = next(iter(pet.accessories))  # the first (and for now only) accessory
        worn = set(self.worn(pet))
        worn ^= {name}
        self.wardrobe[pet.id] = frozenset(worn)
        self._changed()
        return [Action("wardrobe", pet_id=pet.id, worn=frozenset(worn)), Action("sfx", name="toggle")]

    def _toggle_sound(self) -> list[Action]:
        self.sound = not self.sound
        self._changed()
        return [Action("sound", on=self.sound), Action("sfx", name="toggle")]

    def _start(self) -> list[Action]:
        if self.running:
            out = ", ".join(self.running[:2]) + (" & co." if len(self.running) > 2 else "")
            verb = "is" if len(self.running) == 1 else "are"
            self.dialog = Dialog((f"{out} {verb} already out!", f"Swap for {self.pet.name}, or add them too?"))
            self._changed()
            return [Action("sfx", name="open")]
        return self._launch("new")

    def _launch(self, mode: str) -> list[Action]:
        pet = self.pet
        return [Action("sfx", name="start"), Action("start", pet_id=pet.id, worn=self.worn(pet), mode=mode)]

    def _dialog_key(self, key: str) -> list[Action]:
        d = self.dialog
        assert d is not None
        if key in ("left", "up"):
            d.focus = (d.focus - 1) % len(DIALOG_BUTTONS)
        elif key in ("right", "down"):
            d.focus = (d.focus + 1) % len(DIALOG_BUTTONS)
        elif key in ("enter", "space"):
            return self._choose(DIALOG_BUTTONS[d.focus])
        elif key == "escape":
            return self._choose("back")
        else:
            return []
        self._changed()
        return [Action("sfx", name="move")]

    def _choose(self, name: str) -> list[Action]:
        self.dialog = None
        self._changed()
        if name == "back":
            return [Action("sfx", name="back")]
        return self._launch(name)
