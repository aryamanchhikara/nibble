from __future__ import annotations

import pytest

from nibble.core.geometry import Display, Rect, WindowInfo
from nibble.core.world import Snapshot

OWN_PID = 1
APP_PID = 100

# A MacBook display with a 33pt menu bar and no Dock at the bottom, plus a
# 1080p monitor sitting above it (the layout on the dev machine).
LAPTOP = Display(1, frame=Rect(0, 0, 1512, 982), visible=Rect(0, 0, 1512, 949))
MONITOR = Display(2, frame=Rect(-266, 982, 1920, 1080), visible=Rect(-266, 982, 1920, 1080))
# A display with the Dock along the bottom.
DOCKED = Display(3, frame=Rect(0, 0, 1440, 900), visible=Rect(0, 70, 1440, 806))

PET_W, PET_H = 60.0, 72.0


def win(wid: int, left: float, bottom: float, w: float, h: float, *, pid: int = APP_PID, layer: int = 0, owner: str = "App") -> WindowInfo:
    return WindowInfo(id=wid, pid=pid, owner=owner, layer=layer, bounds=Rect(left, bottom, w, h))


def snap(*windows: WindowInfo, displays=(LAPTOP,), front: int | None = APP_PID) -> Snapshot:
    return Snapshot(displays=tuple(displays), windows=tuple(windows), own_pid=OWN_PID, frontmost_pid=front)


@pytest.fixture
def pet_size() -> tuple[float, float]:
    return PET_W, PET_H
