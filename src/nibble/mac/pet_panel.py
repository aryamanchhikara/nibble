"""The pet's on-screen window: a small transparent, non-activating panel.

The panel ignores the mouse except while the cursor is over one of the pet's
opaque pixels (the controller flips that every tick), so the rest of the
square is click-through. Non-activating means clicking the pet never steals
focus from the app the user is in.
"""

from __future__ import annotations

from typing import Protocol

import objc
import Quartz
from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSMakeRect,
    NSPanel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSData, NSNull

from ..core.sprites import GRID, Frame, to_rgba

PET_WINDOW_LEVEL = NSFloatingWindowLevel
ALL_SPACES = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorStationary
    | NSWindowCollectionBehaviorFullScreenAuxiliary
    | NSWindowCollectionBehaviorIgnoresCycle
)

_SRGB = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)


def make_image(frame: Frame, palette: dict[str, str]):
    """A GRID×GRID CGImage for one frame."""
    return make_image_sized(to_rgba(frame, palette), GRID, GRID)


def make_image_sized(rgba: bytes, width: int, height: int):
    """A CGImage from premultiplied RGBA bytes, top row first."""
    provider = Quartz.CGDataProviderCreateWithCFData(NSData.dataWithBytes_length_(rgba, len(rgba)))
    return Quartz.CGImageCreate(
        width,
        height,
        8,
        32,
        width * 4,
        _SRGB,
        Quartz.kCGImageAlphaPremultipliedLast,
        provider,
        None,
        False,
        Quartz.kCGRenderingIntentDefault,
    )


class MouseHandler(Protocol):
    def on_mouse_down(self, x: float, y: float, clicks: int) -> None: ...
    def on_mouse_dragged(self, x: float, y: float) -> None: ...
    def on_mouse_up(self, x: float, y: float, clicks: int) -> None: ...


class PetPanel(NSPanel):
    def canBecomeKeyWindow(self) -> bool:
        return False

    def canBecomeMainWindow(self) -> bool:
        return False


class PetView(NSView):
    handler = objc.ivar()

    def acceptsFirstMouse_(self, event) -> bool:
        return True

    def mouseDown_(self, event) -> None:
        p = NSEvent.mouseLocation()
        if self.handler is not None:
            self.handler.on_mouse_down(p.x, p.y, event.clickCount())

    def mouseDragged_(self, event) -> None:
        p = NSEvent.mouseLocation()
        if self.handler is not None:
            self.handler.on_mouse_dragged(p.x, p.y)

    def mouseUp_(self, event) -> None:
        p = NSEvent.mouseLocation()
        if self.handler is not None:
            self.handler.on_mouse_up(p.x, p.y, event.clickCount())


class PetWindow:
    """Owns the panel and its layer-backed view; positions and draws the pet."""

    def __init__(self, size: float, handler: MouseHandler):
        self.size = size
        self.panel = PetPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, size, size),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        p = self.panel
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(False)
        p.setLevel_(PET_WINDOW_LEVEL)
        p.setCollectionBehavior_(ALL_SPACES)
        p.setHidesOnDeactivate_(False)
        p.setReleasedWhenClosed_(False)
        p.setIgnoresMouseEvents_(True)
        p.setBecomesKeyOnlyIfNeeded_(True)

        view = PetView.alloc().initWithFrame_(NSMakeRect(0, 0, size, size))
        view.handler = handler
        view.setWantsLayer_(True)
        layer = view.layer()
        layer.setMagnificationFilter_(Quartz.kCAFilterNearest)
        layer.setContentsGravity_(Quartz.kCAGravityResize)
        # No implicit cross-fades between frames.
        layer.setActions_({"contents": NSNull.null()})
        p.setContentView_(view)
        self.view = view
        self.backing = 2.0  # device pixels per point on the pet's current display
        self._image = None
        self._origin: tuple[float, float] | None = None
        self._ignoring = True

    def show(self) -> None:
        self.panel.orderFrontRegardless()

    def close(self) -> None:
        self.view.handler = None
        self.panel.orderOut_(None)
        self.panel.close()

    def set_image(self, image) -> None:
        if image is not self._image:
            self._image = image
            self.view.layer().setContents_(image)

    def resize(self, size: float) -> None:
        if size == self.size:
            return
        self.size = size
        self.panel.setContentSize_((size, size))
        self.view.setFrame_(NSMakeRect(0, 0, size, size))
        self._origin = None  # re-place on the next move

    def move_to(self, x: float, y: float) -> None:
        # Land on whole device pixels so every sprite pixel stays crisp.
        b = self.backing
        origin = (round(x * b) / b, round(y * b) / b)
        if origin != self._origin:
            self._origin = origin
            self.panel.setFrameOrigin_(origin)

    def set_click_through(self, through: bool) -> None:
        if through != self._ignoring:
            self._ignoring = through
            self.panel.setIgnoresMouseEvents_(through)
