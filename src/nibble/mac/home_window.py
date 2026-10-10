"""The home page window: a 16-bit character select for picking a pet.

The page is drawn on a 384×216 pixel canvas (core.home_scene) and shown
scaled by a whole number with no smoothing, so it stays crisp on Retina and
non-Retina displays alike. It animates at 12 fps only while it's open.
"""

from __future__ import annotations

import math
import time
from typing import Callable

import objc
import Quartz
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSGraphicsContext,
    NSMakeRect,
    NSScreen,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer

from ..core.home import H, W, Action, HomeModel
from ..core.home_scene import HomeRenderer
from ..core.spec import PetSpec
from .director import Callback
from .fonts import PixelFont
from .pet_panel import make_image_sized
from .sounds import Sounds

FPS = 12
KEYS = {123: "left", 124: "right", 125: "down", 126: "up", 36: "enter", 76: "enter", 53: "escape", 49: "space"}


def page_scale(screen) -> int:
    """The largest whole-number scale that keeps the window compact on this screen."""
    v = screen.visibleFrame().size if screen is not None else None
    if v is None:
        return 2
    return max(1, min(math.floor(v.width * 0.62 / W), math.floor(v.height * 0.75 / H)))


class HomeView(NSView):
    controller = objc.ivar()

    def acceptsFirstResponder(self) -> bool:
        return True

    def acceptsFirstMouse_(self, event) -> bool:
        return True

    def isOpaque(self) -> bool:
        return True

    def drawRect_(self, rect) -> None:
        image = self.controller.image if self.controller else None
        if image is None:
            return
        ctx = NSGraphicsContext.currentContext().CGContext()
        Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationNone)
        Quartz.CGContextSetShouldAntialias(ctx, False)
        Quartz.CGContextDrawImage(ctx, self.bounds(), image)

    def keyDown_(self, event) -> None:
        key = KEYS.get(event.keyCode()) or (event.charactersIgnoringModifiers() or "").lower()
        if self.controller:
            self.controller.on_key(key)

    def mouseDown_(self, event) -> None:
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        if self.controller:
            self.controller.on_click(p.x, p.y)


class _WindowDelegate(NSObject):
    def initWithOnClose_(self, on_close):
        self = objc.super(_WindowDelegate, self).init()
        if self is not None:
            self.on_close = on_close
        return self

    def windowWillClose_(self, _note) -> None:
        self.on_close()


class HomeWindow:
    def __init__(
        self,
        pets: list[PetSpec],
        on_start: Callable[[str, frozenset[str], str], None],
        on_settings: Callable[..., None],
        wardrobe: dict[str, frozenset[str]],
        sound: bool,
        running: Callable[[], list[str]],
        on_wardrobe: Callable[[str, frozenset[str]], None],
        on_closed: Callable[[], None] = lambda: None,
    ):
        self.pets = pets
        self.on_start = on_start
        self.on_settings = on_settings
        self.on_wardrobe = on_wardrobe
        self.on_closed = on_closed
        self.running = running
        self.model = HomeModel(pets, wardrobe=dict(wardrobe), sound=sound)
        self.renderer = HomeRenderer(PixelFont("big"), PixelFont("small"))
        self.sounds = Sounds()
        self.image = None
        self.window: NSWindow | None = None
        self.view: HomeView | None = None
        self.scale = 2
        self._timer = None
        self._tick_cb = Callback.alloc().initWithCallable_(self._tick)
        self._delegate = _WindowDelegate.alloc().initWithOnClose_(self._closed)

    @property
    def visible(self) -> bool:
        return self.window is not None and self.window.isVisible()

    def show(self) -> None:
        self.model.running = self.running()
        self.model.dialog = None
        self.model.version += 1
        screen = NSScreen.mainScreen()
        scale = page_scale(screen)
        if self.window is None or scale != self.scale:
            self._build(scale)
        self._render()
        self.window.center()
        f = self.window.frame()  # keep the origin on whole points so pixels stay crisp
        self.window.setFrameOrigin_((round(f.origin.x), round(f.origin.y)))
        NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.view)
        if self._timer is None:
            self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                1 / FPS, self._tick_cb, "fire:", None, True
            )
            NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    def close(self) -> None:
        if self.window is not None:
            self.window.close()

    def _build(self, scale: int) -> None:
        if self.window is not None:
            self.window.setDelegate_(None)
            self.window.close()
        self.scale = scale
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskFullSizeContentView
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W * scale, H * scale), style, NSBackingStoreBuffered, False
        )
        win.setTitle_("nibble")
        win.setTitlebarAppearsTransparent_(True)
        win.setTitleVisibility_(NSWindowTitleHidden)
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self._delegate)
        view = HomeView.alloc().initWithFrame_(NSMakeRect(0, 0, W * scale, H * scale))
        view.controller = self
        win.setContentView_(view)
        win.setContentMinSize_((W * scale, H * scale))  # fixed size: no resize handle,
        win.setContentMaxSize_((W * scale, H * scale))  # and Zoom does nothing
        self.window, self.view = win, view

    def _closed(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self.on_settings(seen_home=True)
        self.on_closed()

    def _tick(self) -> None:
        if self.visible:
            self._render()

    def _render(self) -> None:
        canvas = self.renderer.render(self.model, time.monotonic())
        self.image = make_image_sized(canvas.rgba(), W, H)
        if self.view is not None:
            self.view.setNeedsDisplay_(True)

    # ---- input --------------------------------------------------------------

    def on_key(self, key: str) -> None:
        self._do(self.model.press(key, time.monotonic()))

    def on_click(self, x: float, y: float) -> None:
        cx, cy = x / self.scale, H - 1 - y / self.scale  # view points -> canvas pixels (y down)
        self._do(self.model.click(cx, cy, time.monotonic()))

    def _do(self, actions: list[Action]) -> None:
        for a in actions:
            if a.kind == "sfx":
                if self.model.sound:
                    self.sounds.play(a.name)
            elif a.kind == "sound":
                self.on_settings(sound=a.on)
                if a.on:
                    self.sounds.play("toggle")
            elif a.kind == "wardrobe":
                self.on_wardrobe(a.pet_id, a.worn)
            elif a.kind == "describe":
                self.model.show_toast("Custom pets arrive in the next update (needs an OpenRouter key)", time.monotonic())
            elif a.kind == "start":
                self.on_start(a.pet_id, a.worn, a.mode)
                self.close()
            elif a.kind == "close":
                self.close()
        self._render()
