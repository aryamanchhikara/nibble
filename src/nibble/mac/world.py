"""Reads the desktop (displays, windows, frontmost app) into core Snapshots.

Uses only CGWindowListCopyWindowInfo and NSWorkspace, which need no
permissions. Window titles would need Screen Recording, so we never ask for
them.
"""

from __future__ import annotations

import os

import Quartz
from AppKit import NSScreen, NSWorkspace

from ..core.geometry import DOCK_LAYER, Display, Rect, WindowInfo, flip_rect
from ..core.world import Snapshot

_SCAN_OPTIONS = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
_BOUNDS = Quartz.kCGWindowBounds
_NUMBER = Quartz.kCGWindowNumber
_PID = Quartz.kCGWindowOwnerPID
_OWNER = Quartz.kCGWindowOwnerName
_LAYER = Quartz.kCGWindowLayer
_ALPHA = Quartz.kCGWindowAlpha
_ONSCREEN = Quartz.kCGWindowIsOnscreen


def _rect(r) -> Rect:
    return Rect(r.origin.x, r.origin.y, r.size.width, r.size.height)


class WorldWatcher:
    def __init__(self) -> None:
        self.own_pid = os.getpid()
        self._front_pid: int | None = None
        self._front_name: str | None = None
        self._front_bundle: str | None = None
        self._primary_height = 0.0

    def displays(self) -> tuple[Display, ...]:
        screens = NSScreen.screens() or []
        if not screens:
            return ()
        self._primary_height = screens[0].frame().size.height
        return tuple(
            Display(
                id=int(s.deviceDescription()["NSScreenNumber"]),
                frame=_rect(s.frame()),
                visible=_rect(s.visibleFrame()),
                backing=float(s.backingScaleFactor()),
            )
            for s in screens
        )

    def _update_frontmost(self) -> None:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return
        pid = int(app.processIdentifier())
        # Our own windows (menus, New pet…) don't count: keep tracking the app
        # the user was in before.
        if pid == self.own_pid:
            return
        self._front_pid = pid
        self._front_name = app.localizedName()
        self._front_bundle = app.bundleIdentifier()

    def _bounds(self, d) -> Rect | None:
        ok, r = Quartz.CGRectMakeWithDictionaryRepresentation(d.objectForKey_(_BOUNDS), None)
        if not ok:
            return None
        return flip_rect(Rect(r.origin.x, r.origin.y, r.size.width, r.size.height), self._primary_height)

    def _window(self, d, layer: int, pid: int) -> WindowInfo | None:
        bounds = self._bounds(d)
        if bounds is None:
            return None
        alpha = d.objectForKey_(_ALPHA)
        return WindowInfo(
            id=int(d.objectForKey_(_NUMBER)),
            pid=pid,
            owner=str(d.objectForKey_(_OWNER) or ""),
            layer=layer,
            bounds=bounds,
            alpha=1.0 if alpha is None else float(alpha),
        )

    def scan(self) -> Snapshot:
        displays = self.displays()
        self._update_frontmost()
        info = Quartz.CGWindowListCopyWindowInfo(_SCAN_OPTIONS, Quartz.kCGNullWindowID) or []
        windows = []
        for d in info:
            # Cheap checks first: most entries are menu bar extras and other
            # system chrome that can neither hold nor hide a pet.
            layer = int(d.objectForKey_(_LAYER) or 0)
            if not 0 <= layer < DOCK_LAYER:
                continue
            pid = int(d.objectForKey_(_PID) or 0)
            if pid == self.own_pid:
                continue
            w = self._window(d, layer, pid)
            if w is not None:
                windows.append(w)
        return Snapshot(
            displays=displays,
            windows=tuple(windows),
            own_pid=self.own_pid,
            frontmost_pid=self._front_pid,
            frontmost_name=self._front_name,
            frontmost_bundle=self._front_bundle,
        )

    @staticmethod
    def user_idle() -> float:
        """Seconds since the last keyboard or mouse input (a query, not an event tap)."""
        return float(
            Quartz.CGEventSourceSecondsSinceLastEventType(
                Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType
            )
        )

    def bounds_of(self, window_id: int) -> Rect | None:
        """Cheap single-window poll (~0.1 ms) used while riding a window."""
        info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, window_id) or []
        for d in info:
            if int(d.objectForKey_(_NUMBER)) != window_id:
                continue
            if not d.objectForKey_(_ONSCREEN):
                return None  # minimized, hidden, or on another Space
            return self._bounds(d)
        return None
