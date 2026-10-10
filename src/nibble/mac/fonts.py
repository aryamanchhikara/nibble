"""The bundled pixel fonts, rasterized to 1-bit masks with CoreText.

Both fonts are drawn without antialiasing at their native pixel sizes, which
lands every glyph exactly on the pixel grid.
"""

from __future__ import annotations

import math
from importlib import resources

import CoreText
import Quartz
from Foundation import NSURL, NSAttributedString

from ..core.canvas import Mask

FONTS = {
    # name: (file, PostScript name, native size in px)
    "big": ("PressStart2P-Regular.ttf", "PressStart2P-Regular", 8),
    "small": ("Tiny5-Regular.ttf", "Tiny5-Regular", 10),
}

_registered = False


def register() -> None:
    """Make the bundled fonts available to this process (once)."""
    global _registered
    if _registered:
        return
    folder = resources.files("nibble.assets").joinpath("fonts")
    for file, _, _ in FONTS.values():
        path = str(folder.joinpath(file))
        CoreText.CTFontManagerRegisterFontsForURL(
            NSURL.fileURLWithPath_(path), CoreText.kCTFontManagerScopeProcess, None
        )
    _registered = True


class PixelFont:
    def __init__(self, key: str):
        register()
        _, name, size = FONTS[key]
        self.font = CoreText.CTFontCreateWithName(name, size, None)
        self.ascent = math.ceil(CoreText.CTFontGetAscent(self.font))
        self.descent = math.ceil(CoreText.CTFontGetDescent(self.font))
        # One spare row below for descenders that dip past the font's metrics.
        self.height = self.ascent + self.descent + 1

    def width(self, text: str) -> int:
        return math.ceil(CoreText.CTLineGetTypographicBounds(self._line(text), None, None, None)[0])

    def _line(self, text: str):
        attr = NSAttributedString.alloc().initWithString_attributes_(
            text, {CoreText.kCTFontAttributeName: self.font, CoreText.kCTForegroundColorFromContextAttributeName: True}
        )
        return CoreText.CTLineCreateWithAttributedString(attr)

    def mask(self, text: str) -> Mask:
        w, h = max(1, self.width(text) + 1), self.height
        ctx = Quartz.CGBitmapContextCreate(
            None, w, h, 8, w * 4, Quartz.CGColorSpaceCreateDeviceRGB(), Quartz.kCGImageAlphaPremultipliedLast
        )
        Quartz.CGContextSetShouldAntialias(ctx, False)
        Quartz.CGContextSetAllowsAntialiasing(ctx, False)
        Quartz.CGContextSetShouldSmoothFonts(ctx, False)
        Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        Quartz.CGContextSetTextPosition(ctx, 0, self.descent + 1)
        CoreText.CTLineDraw(self._line(text), ctx)
        img = Quartz.CGBitmapContextCreateImage(ctx)
        data = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img)))
        bits = tuple(data[i * 4 + 3] > 127 for i in range(w * h))  # rows come out top first
        return Mask(w, h, bits)
