"""How lively a pet is: the Energy menu.

Chill (the default) is a calm companion that mostly hangs out. Walks are rare,
short and slow; sits are long; naps are frequent; it waits a moment before
following you to another window and then makes one unhurried hop. Normal is
the original behaviour, toned down a little. Hyper is for when you want chaos.

Demo mode ignores the setting and uses its own lively profile so there's
always something to film.
"""

from __future__ import annotations

from enum import Enum

from .brain import Tuning
from .peek import PeekTuning


class Energy(Enum):
    CHILL = "chill"
    NORMAL = "normal"
    HYPER = "hyper"

    @property
    def label(self) -> str:
        return self.value.capitalize()


DEFAULT = Energy.CHILL

BRAIN: dict[Energy, Tuning] = {
    Energy.CHILL: Tuning(),  # Tuning's defaults are the calm profile
    Energy.NORMAL: Tuning(  # about half the walking of the original behaviour
        reaction_delay=(0.5, 1.0),
        hop_pace=1.25,
        idle_time=(2.0, 5.0),
        sit_time=(5.0, 14.0),
        walk_every=(4.0, 10.0),
        walk_chance=0.6,
        walk_distance=(45.0, 260.0),
        walk_speed=42.0,
        nap_chance=0.05,
        nap_time=(40.0, 120.0),
        chase_hover=0.7,
        chase_radius=110.0,
        chase_for=4.0,
        chase_speed=80.0,
        bored_for=40.0,
        sleep_after=180.0,
    ),
    Energy.HYPER: Tuning(
        reaction_delay=(0.1, 0.3),
        hop_pace=0.9,
        idle_time=(1.0, 3.0),
        sit_time=(2.0, 6.0),
        walk_every=(0.0, 3.0),
        walk_chance=0.7,
        walk_distance=(60.0, 360.0),
        walk_speed=64.0,
        nap_chance=0.0,
        chase_hover=0.25,
        chase_radius=140.0,
        chase_for=8.0,
        chase_speed=130.0,
        bored_for=15.0,
        sleep_after=300.0,
    ),
}

PEEK: dict[Energy, PeekTuning] = {
    Energy.CHILL: PeekTuning(),
    Energy.NORMAL: PeekTuning(slide_speed=110.0, look_every=(20.0, 50.0), quip_chance=0.35, move_chance=0.3, pop_hover=0.35),
    Energy.HYPER: PeekTuning(
        slide_speed=150.0, pop_speed=460.0, look_every=(8.0, 20.0), quip_chance=0.5, move_chance=0.4, pop_hover=0.1
    ),
}

# The original, lively behaviour with every slow timer cut short.
DEMO_BRAIN = Tuning(
    reaction_delay=(0.15, 0.45),
    hop_pace=1.0,
    idle_time=(1.5, 4.5),
    sit_time=(3.0, 9.0),
    walk_every=(0.0, 0.0),
    walk_chance=0.6,
    walk_distance=(50.0, 320.0),
    walk_speed=48.0,
    nap_chance=0.05,
    nap_time=(8.0, 15.0),
    chase_hover=0.4,
    chase_radius=120.0,
    chase_for=5.0,
    chase_speed=100.0,
    bored_for=15.0,
    sleep_after=12.0,
    wake_after_active=3.0,
)
DEMO_PEEK = PeekTuning(slide_speed=110.0, look_every=(3.6, 9.0), quip_chance=0.35, move_chance=0.3, pop_hover=0.3)


def parse(value: str | None) -> Energy:
    try:
        return Energy(value)
    except ValueError:
        return DEFAULT


def profiles(energy: Energy, demo: bool = False) -> tuple[Tuning, PeekTuning]:
    if demo:
        return DEMO_BRAIN, DEMO_PEEK
    return BRAIN[energy], PEEK[energy]
