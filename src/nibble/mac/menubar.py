"""The menu bar item and its menu."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from AppKit import (
    NSApp,
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)

from ..core.sprites import to_rgba
from .director import Callback
from .pet_panel import make_image_sized

# A tiny pet head, drawn as a template so macOS tints it for light/dark menu bars.
ICON = (
    "................",
    ".##..........##.",
    ".###........###.",
    ".####......####.",
    ".##############.",
    "################",
    "################",
    "###..######..###",
    "###..######..###",
    "################",
    "################",
    ".##############.",
    "..############..",
    "....########....",
    "................",
    "................",
)


def menu_icon() -> NSImage:
    doubled = tuple("".join(ch * 2 for ch in row) for row in ICON for _ in range(2))
    rgba = to_rgba(doubled, {"#": "#000000"})
    image = NSImage.alloc().initWithCGImage_size_(make_image_sized(rgba, 32, 32), (16, 16))
    image.setTemplate_(True)
    return image


class MenuBar:
    def __init__(self, title: str):
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.item.button().setImage_(menu_icon())
        self.item.button().setToolTip_("nibble")
        self.menu = NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.item.setMenu_(self.menu)
        self._callbacks: list[Callback] = []
        header = self.menu.addItemWithTitle_action_keyEquivalent_(title, None, "")
        header.setEnabled_(False)
        self.menu.addItem_(NSMenuItem.separatorItem())

    def add(self, title: str, action: Callable[[], None], key: str = "") -> NSMenuItem:
        cb = Callback.alloc().initWithCallable_(action)
        self._callbacks.append(cb)
        item = self.menu.addItemWithTitle_action_keyEquivalent_(title, "fire:", key)
        item.setTarget_(cb)
        return item

    def add_toggle(self, title: str, initial: bool, action: Callable[[bool], None]) -> NSMenuItem:
        holder: dict[str, NSMenuItem] = {}

        def flip() -> None:
            item = holder["item"]
            on = item.state() != NSControlStateValueOn
            item.setState_(NSControlStateValueOn if on else NSControlStateValueOff)
            action(on)

        holder["item"] = item = self.add(title, flip)
        item.setState_(NSControlStateValueOn if initial else NSControlStateValueOff)
        return item

    def add_choice(
        self,
        title: str,
        options: Sequence[tuple[str, Any]],
        current: Any,
        action: Callable[[Any], None],
        note: str | None = None,
    ) -> None:
        """A submenu where exactly one option is ticked."""
        parent = self.menu.addItemWithTitle_action_keyEquivalent_(title, None, "")
        submenu = NSMenu.alloc().initWithTitle_(title)
        submenu.setAutoenablesItems_(False)
        items: list[tuple[NSMenuItem, Any]] = []

        def choose(value: Any) -> None:
            for item, v in items:
                item.setState_(NSControlStateValueOn if v == value else NSControlStateValueOff)
            action(value)

        for label, value in options:
            cb = Callback.alloc().initWithCallable_(lambda v=value: choose(v))
            self._callbacks.append(cb)
            item = submenu.addItemWithTitle_action_keyEquivalent_(label, "fire:", "")
            item.setTarget_(cb)
            item.setState_(NSControlStateValueOn if value == current else NSControlStateValueOff)
            items.append((item, value))
        if note:
            submenu.addItem_(NSMenuItem.separatorItem())
            submenu.addItemWithTitle_action_keyEquivalent_(note, None, "").setEnabled_(False)
        self.menu.setSubmenu_forItem_(submenu, parent)

    def add_separator(self) -> None:
        self.menu.addItem_(NSMenuItem.separatorItem())

    def add_quit(self) -> None:
        self.add_separator()
        item = self.menu.addItemWithTitle_action_keyEquivalent_("Quit nibble", "terminate:", "q")
        item.setTarget_(NSApp)
