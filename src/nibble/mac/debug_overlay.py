"""Optional overlay that draws every surface a pet can stand on.

Green: window edges. Yellow: the focused window's edge. Blue: display floors.
One click-through window per display, redrawn a few times a second.
"""

from __future__ import annotations

import time
from typing import Callable

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSPanel,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSString

from ..core.geometry import Display, window_key
from ..core.world import Snapshot, WorldView
from .pet_panel import ALL_SPACES, PET_WINDOW_LEVEL

REDRAW_INTERVAL = 0.2


class _OverlayView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_OverlayView, self).initWithFrame_(frame)
        if self is not None:
            self.lines = []  # (x0, x1, y, kind) in view coordinates
            self.label = ""
        return self

    def isOpaque(self) -> bool:
        return False

    def drawRect_(self, rect) -> None:
        colors = {
            "window": NSColor.systemGreenColor(),
            "active": NSColor.systemYellowColor(),
            "floor": NSColor.systemBlueColor(),
        }
        for x0, x1, y, kind in self.lines:
            colors[kind].colorWithAlphaComponent_(0.85).setStroke()
            path = NSBezierPath.bezierPath()
            path.setLineWidth_(4 if kind == "active" else 2)
            path.moveToPoint_((x0, y))
            path.lineToPoint_((x1, y))
            path.stroke()
        if self.label:
            attrs = {
                NSFontAttributeName: NSFont.monospacedSystemFontOfSize_weight_(12, 0.3),
                NSForegroundColorAttributeName: NSColor.systemYellowColor(),
            }
            NSString.stringWithString_(self.label).drawAtPoint_withAttributes_((12, 12), attrs)


class DebugOverlay:
    def __init__(self, pet_size: Callable[[], tuple[float, float]]):
        self.pet_size = pet_size  # read every redraw: the pet can change size
        self._windows: dict[int, tuple[NSPanel, _OverlayView, Display]] = {}
        self._next = 0.0

    def close(self) -> None:
        for panel, _, _ in self._windows.values():
            panel.orderOut_(None)
        self._windows.clear()

    def update(self, snapshot: Snapshot) -> None:
        now = time.monotonic()
        if now < self._next:
            return
        self._next = now + REDRAW_INTERVAL
        self._sync_displays(snapshot)

        world = WorldView(snapshot, *self.pet_size())
        s = world.surfaces
        lines = []
        for key in s.all_keys():
            y = s.y(key)
            kind = key[0]
            if key == (window_key(world.active.id) if world.active else None):
                kind = "active"
            for seg in s.segments(key):
                lines.append((seg.x0, seg.x1, y, kind))
        front = snapshot.frontmost_name or "?"
        home = world.home()
        if home is None:
            where = "stay put"
        elif home.stand is not None:
            where = "stand on its top edge"
        else:
            where = "peek from its " + " or ".join("left" if e.side < 0 else "right" for e in home.peek) + " side"
        label = f"front: {front}  window {world.active_id}: {where}"

        for panel, view, d in self._windows.values():
            ox, oy = d.frame.x, d.frame.y
            view.lines = [(x0 - ox, x1 - ox, y - oy + 1, k) for x0, x1, y, k in lines]
            view.label = label if d.id == (world.active_display.id if world.active_display else d.id) else ""
            view.setNeedsDisplay_(True)

    def _sync_displays(self, snapshot: Snapshot) -> None:
        wanted = {d.id: d for d in snapshot.displays}
        for did in list(self._windows):
            if did not in wanted or self._windows[did][2] != wanted[did]:
                self._windows.pop(did)[0].orderOut_(None)
        for did, d in wanted.items():
            if did in self._windows:
                continue
            f = d.frame
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(f.x, f.y, f.w, f.h),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                NSBackingStoreBuffered,
                False,
            )
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(False)
            panel.setIgnoresMouseEvents_(True)
            panel.setLevel_(PET_WINDOW_LEVEL)
            panel.setCollectionBehavior_(ALL_SPACES)
            panel.setHidesOnDeactivate_(False)
            view = _OverlayView.alloc().initWithFrame_(NSMakeRect(0, 0, f.w, f.h))
            panel.setContentView_(view)
            panel.setFrame_display_(NSMakeRect(f.x, f.y, f.w, f.h), True)
            panel.orderFrontRegardless()
            self._windows[did] = (panel, view, d)
