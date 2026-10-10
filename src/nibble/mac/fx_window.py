"""Speech bubbles and sleepy z's. Always click-through, hidden when idle.

Quips are plain white bubbles that pop in. Cheers read as encouragement: a
warm gold bubble that bounces in, twinkling pixel sparkles at its corners and
a gentle bob while it's up.
"""

from __future__ import annotations

import math
from typing import Callable

import objc
from AppKit import (
    NSAttributedString,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontDescriptorSystemDesignRounded,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSPanel,
    NSParagraphStyleAttributeName,
    NSRectFill,
    NSStringDrawingUsesLineFragmentOrigin,
    NSTextAlignmentCenter,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSAffineTransform

from ..core.bubble import TAIL, BubbleLayout
from ..core.geometry import Rect
from ..core.sprites import parse_hex
from .pet_panel import ALL_SPACES, PET_WINDOW_LEVEL

FX_LEVEL = PET_WINDOW_LEVEL + 1  # always above the pets

FONT_SIZE = 14.0
MAX_TEXT_W = 210.0
PAD_X, PAD_Y = 11.0, 7.0
RADIUS = 8.0
STROKE = 2.0
SPARKLE_ROOM = 16.0  # extra window space around a cheer bubble for its sparkles

QUIP_FILL = "#ffffff"
CHEER_FILL = "#fff1b8"
SPARKLE = "#ffc531"
POP_IN = 0.16  # seconds
BOUNCE_IN = 0.38
FADE_OUT = 0.3

STAR = ("..#..", "..#..", "#####", "..#..", "..#..")
TWINKLE = (".....", "..#..", ".###.", "..#..", ".....")
ZED = ("#####", "...#.", "..#..", ".#...", "#####")


def _color(hex_color: str, alpha: float = 1.0) -> NSColor:
    r, g, b = parse_hex(hex_color)
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255, g / 255, b / 255, alpha)


def _font() -> NSFont:
    base = NSFont.systemFontOfSize_weight_(FONT_SIZE, NSFontWeightSemibold)
    rounded = base.fontDescriptor().fontDescriptorWithDesign_(NSFontDescriptorSystemDesignRounded)
    return NSFont.fontWithDescriptor_size_(rounded, FONT_SIZE) if rounded else base


def _overlay_panel(width: float, height: float) -> NSPanel:
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, width, height),
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(False)
    panel.setIgnoresMouseEvents_(True)
    panel.setLevel_(FX_LEVEL)
    panel.setCollectionBehavior_(ALL_SPACES)
    panel.setHidesOnDeactivate_(False)
    panel.setReleasedWhenClosed_(False)
    return panel


def _pixels(pattern, x: float, y: float, px: float, fill: NSColor, ink: NSColor) -> None:
    """Draw a tiny pixel pattern (top row first) with a 1-pixel ink outline."""
    cells = [(c, r) for r, row in enumerate(pattern) for c, ch in enumerate(row) if ch == "#"]
    n = len(pattern)
    ink.set()
    for c, r in cells:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            NSRectFill(NSMakeRect(x + (c + dx) * px, y + (n - 1 - r + dy) * px, px, px))
    fill.set()
    for c, r in cells:
        NSRectFill(NSMakeRect(x + c * px, y + (n - 1 - r) * px, px, px))


# ---- speech bubble --------------------------------------------------------


class _BubbleView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_BubbleView, self).initWithFrame_(frame)
        if self is not None:
            self.text = None
            self.box = (0, 0, 0, 0)
            self.tip = (0, 0)
            self.tail_side = "bottom"
            self.scale = 1.0
            self.cheer = False
            self.sparkle_t = 0.0
            self.ink = _color("#2a1f45")
            self.attrs = {}
        return self

    def isOpaque(self) -> bool:
        return False

    def drawRect_(self, rect) -> None:
        if self.text is None:
            return
        NSGraphicsContext.currentContext().saveGraphicsState()
        t = NSAffineTransform.transform()
        tx, ty = self.tip
        t.translateXBy_yBy_(tx, ty)
        t.scaleBy_(self.scale)
        t.translateXBy_yBy_(-tx, -ty)
        t.concat()

        x, y, w, h = self.box
        fill = _color(CHEER_FILL if self.cheer else QUIP_FILL)
        tail_fill, tail_line, seam = self._tail(x, y, w, h)
        body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), RADIUS, RADIUS)
        body.setLineWidth_(STROKE)
        tail_line.setLineWidth_(STROKE)
        fill.setFill()
        tail_fill.fill()
        body.fill()
        self.ink.setStroke()
        body.stroke()
        tail_line.stroke()
        fill.setFill()
        NSRectFill(seam)  # erase the bubble's border where the tail joins it

        text_rect = NSMakeRect(x + PAD_X, y + PAD_Y - 1, w - 2 * PAD_X, h - 2 * PAD_Y + 2)
        NSAttributedString.alloc().initWithString_attributes_(self.text, self.attrs).drawWithRect_options_(
            text_rect, NSStringDrawingUsesLineFragmentOrigin
        )
        if self.cheer:
            self._sparkles(x, y, w, h)
        NSGraphicsContext.currentContext().restoreGraphicsState()

    @objc.python_method
    def _tail(self, x, y, w, h):
        """Filled triangle, its two outer sides as a line, and the seam to erase."""
        tx, ty = self.tip
        half = 6.0
        inner = 2 * half - 2 * STROKE
        if self.tail_side == "bottom":
            a, b = (tx - half, y), (tx + half, y)
            seam = NSMakeRect(tx - half + STROKE, y - STROKE, inner, STROKE * 2)
        else:
            edge = x + w if self.tail_side == "right" else x
            a, b = (edge, ty - half), (edge, ty + half)
            seam = NSMakeRect(edge - STROKE, ty - half + STROKE, STROKE * 2, inner)
        line = NSBezierPath.bezierPath()
        line.moveToPoint_(a)
        line.lineToPoint_(self.tip)
        line.lineToPoint_(b)
        shape = line.copy()
        shape.closePath()
        return shape, line, seam

    @objc.python_method
    def _sparkles(self, x, y, w, h) -> None:
        gold, white = _color(SPARKLE), _color("#ffffff")
        spots = ((x - 9, y + h - 4), (x + w - 2, y + h + 2), (x + w + 2, y - 6), (x - 6, y - 4))
        for i, (sx, sy) in enumerate(spots):
            phase = (self.sparkle_t * 3.0 + i * 0.37) % 1.0
            big = phase < 0.5
            _pixels(STAR if big else TWINKLE, sx, sy, 2.0, gold if i % 2 == 0 else white, self.ink)


class BubbleWindow:
    """One speech bubble that follows a pet around."""

    def __init__(self, ink: str):
        self.panel = _overlay_panel(10, 10)
        self.view = _BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        self.view.ink = _color(ink)
        para = NSMutableParagraphStyle.alloc().init()
        para.setAlignment_(NSTextAlignmentCenter)
        self.view.attrs = {
            NSFontAttributeName: _font(),
            NSForegroundColorAttributeName: self.view.ink,
            NSParagraphStyleAttributeName: para,
        }
        self.panel.setContentView_(self.view)
        self.text: str | None = None
        self.kind = "quip"
        self.started = 0.0
        self.ends = 0.0
        self._size = (0.0, 0.0)
        self._frame: tuple | None = None

    def say(self, text: str, kind: str, now: float) -> None:
        self.text, self.kind = text, kind
        self.started = now
        hold = min(6.5, 2.4 + 0.06 * len(text)) + (1.2 if kind == "cheer" else 0.0)
        self.ends = now + hold
        size = NSAttributedString.alloc().initWithString_attributes_(text, self.view.attrs).boundingRectWithSize_options_(
            (MAX_TEXT_W, 1000), NSStringDrawingUsesLineFragmentOrigin
        ).size
        self._size = (max(44.0, math.ceil(size.width) + 2 * PAD_X), math.ceil(size.height) + 2 * PAD_Y)
        self.view.text = text
        self.view.cheer = kind == "cheer"
        self.panel.orderFrontRegardless()

    @property
    def showing(self) -> bool:
        return self.text is not None

    def animating(self, now: float) -> bool:
        intro = BOUNCE_IN if self.kind == "cheer" else POP_IN
        return self.showing and (now - self.started < intro or self.ends - now < FADE_OUT)

    def hide(self) -> None:
        self.text = None
        self.view.text = None
        self.panel.orderOut_(None)

    def close(self) -> None:
        self.hide()
        self.panel.close()

    def update(self, now: float, place: Callable[[float, float], BubbleLayout]) -> None:
        if self.text is None:
            return
        if now >= self.ends:
            self.hide()
            return
        w, h = self._size
        lay = place(w, h)
        cheer = self.kind == "cheer"
        bob = math.sin((now - self.started) * 5.0) * 1.5 if cheer else 0.0
        box = Rect(lay.box.x, lay.box.y + bob, w, h)
        tip = (lay.tip[0], lay.tip[1] + bob)

        room = SPARKLE_ROOM if cheer else 2 * STROKE
        x0 = min(box.left, tip[0]) - room
        y0 = min(box.bottom, tip[1]) - room
        x1 = max(box.right, tip[0]) + room
        y1 = max(box.top, tip[1]) + room
        frame = (round(x0), round(y0), math.ceil(x1 - x0), math.ceil(y1 - y0))
        if frame != self._frame:
            self._frame = frame
            self.panel.setFrame_display_(NSMakeRect(*frame), False)
            self.view.setFrame_(NSMakeRect(0, 0, frame[2], frame[3]))
        ox, oy = frame[0], frame[1]
        self.view.box = (box.x - ox, box.y - oy, w, h)
        self.view.tip = (tip[0] - ox, tip[1] - oy)
        self.view.tail_side = lay.tail_side
        self.view.scale = self._scale(now - self.started)
        self.view.sparkle_t = now - self.started
        self.panel.setAlphaValue_(min(1.0, max(0.0, (self.ends - now) / FADE_OUT)))
        self.view.setNeedsDisplay_(True)

    def _scale(self, age: float) -> float:
        if self.kind == "cheer":
            if age >= BOUNCE_IN:
                return 1.0
            x = age / BOUNCE_IN - 1  # ease-out-back: overshoot, then settle
            return 0.3 + 0.7 * (1 + 2.70158 * x**3 + 1.70158 * x**2)
        return 1.0 if age >= POP_IN else 0.6 + 0.4 * (age / POP_IN)


# ---- zzz --------------------------------------------------------------------


class _ZzzView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_ZzzView, self).initWithFrame_(frame)
        if self is not None:
            self.t = 0.0
            self.ink = _color("#2a1f45")
            self.scale = 1.0  # pet size relative to Large
            self.backing = 2.0
        return self

    def isOpaque(self) -> bool:
        return False

    def drawRect_(self, rect) -> None:
        # Dark z's with a light rim read on both light and dark windows.
        rim = _color("#ffffff")
        k, b = self.scale, self.backing
        for i in range(3):
            phase = (self.t / 2.4 + i / 3) % 1.0
            px = max(1.0, round((2.5 + phase * 1.5) * k * b)) / b  # whole device pixels
            x = round((4 + phase * 26) * k * b) / b
            y = round((4 + phase * 50) * k * b) / b
            alpha = min(1.0, phase * 4) * (1 - max(0.0, phase - 0.7) / 0.3)
            _pixels(ZED, x, y, px, self.ink.colorWithAlphaComponent_(alpha), rim.colorWithAlphaComponent_(alpha * 0.9))


class ZzzWindow:
    W, H = 60.0, 80.0

    def __init__(self, ink: str):
        self.panel = _overlay_panel(self.W, self.H)
        self.view = _ZzzView.alloc().initWithFrame_(NSMakeRect(0, 0, self.W, self.H))
        self.view.ink = _color(ink)
        self.panel.setContentView_(self.view)
        self.visible = False
        self.scale = 1.0  # pet size relative to Large
        self._origin: tuple | None = None

    def update(self, now: float, asleep: bool, head_x: float, head_top: float, backing: float = 2.0) -> None:
        if not asleep:
            if self.visible:
                self.visible = False
                self.panel.orderOut_(None)
            return
        origin = (round(head_x + 4 * self.scale), round(head_top - 18 * self.scale))
        if origin != self._origin:
            self._origin = origin
            self.panel.setFrameOrigin_(origin)
        if not self.visible:
            self.visible = True
            self.panel.orderFrontRegardless()
        self.view.t = now
        self.view.scale, self.view.backing = self.scale, backing
        self.view.setNeedsDisplay_(True)

    def close(self) -> None:
        self.panel.orderOut_(None)
        self.panel.close()
