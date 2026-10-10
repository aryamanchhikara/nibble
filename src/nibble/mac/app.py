"""The menu bar app: starts AppKit, brings back your pets (or the home page), runs the loop."""

from __future__ import annotations

import logging
import os

import objc
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSRunningApplication
from Foundation import NSObject
from PyObjCTools import AppHelper

from .. import paths
from ..core.energy import Energy
from ..core.size import Size
from ..core.spec import PetSpec, load_builtin
from .debug_overlay import DebugOverlay
from .director import Director
from .home_window import HomeWindow
from .menubar import MenuBar

log = logging.getLogger(__name__)

# The built-in cast on the home page, in card order.
CAST = ("pearl", "archie", "dewey", "kernel")


def _builtin(pet_id: str) -> PetSpec | None:
    try:
        return load_builtin(pet_id)
    except (FileNotFoundError, KeyError, ValueError):
        log.warning("no built-in pet called %r", pet_id)
        return None


class AppDelegate(NSObject):
    def initWithDebug_demo_(self, debug: bool, demo: bool):
        self = objc.super(AppDelegate, self).init()
        if self is not None:
            self.debug = debug
            self.demo = demo
            self.director = None
            self.overlay = None
            self.home = None
        return self

    def applicationDidFinishLaunching_(self, _note) -> None:
        self.director = Director(demo=self.demo, settings_path=paths.settings_file())
        restored = self._restore_lineup()

        settings = self.director.settings
        self.menubar = MenuBar("nibble · demo mode (fast timers)" if self.demo else "nibble")
        self.menubar.add("Choose your nibble…", self.show_home)
        self.menubar.add_separator()
        self.menubar.add_toggle("Cheer me on", settings.cheer_me_on, lambda on: self.director.update_settings(cheer_me_on=on))
        self.menubar.add_toggle("Quiet mode", settings.quiet, lambda on: self.director.update_settings(quiet=on))
        self.menubar.add_choice(
            "Energy",
            [(e.label, e) for e in Energy],
            self.director.energy,
            self.director.set_energy,
            note="Demo mode moves fast regardless" if self.demo else None,
        )
        self.menubar.add_choice("Size", [(s.label, s) for s in Size], self.director.size, self.director.set_size)
        self.menubar.add_separator()
        self.menubar.add("Drop pets in again", self.director.respawn_all)
        self.menubar.add_toggle("Show standable edges", self.debug, self.set_overlay)
        self.menubar.add_quit()

        self.set_overlay(self.debug)
        self.director.start()
        log.info("nibble is running (displays: %d)", len(self.director.snapshot.displays))
        if not restored:
            self.show_home()  # first launch, or nobody was out last time

    # ---- pets -------------------------------------------------------------

    def _restore_lineup(self) -> bool:
        for entry in self.director.settings.pets:
            spec = _builtin(entry["id"])
            if spec is not None:
                self.director.spawn(spec, frozenset(entry.get("worn", [])))
        return bool(self.director.pets)

    def show_home(self) -> None:
        if self.home is None:
            settings = self.director.settings
            pets = [p for p in (_builtin(i) for i in CAST) if p is not None]
            self.home = HomeWindow(
                pets=pets,
                on_start=self._start_from_home,
                on_settings=self.director.update_settings,
                wardrobe={k: frozenset(v) for k, v in settings.wardrobe.items()},
                sound=settings.sound,
                running=self.director.running_names,
                on_wardrobe=self.director.set_worn,
                on_closed=self._return_focus,
            )
        self.home.show()

    def _start_from_home(self, pet_id: str, worn: frozenset[str], mode: str) -> None:
        spec = _builtin(pet_id)
        if spec is None:
            return
        if mode == "swap":
            self.director.swap(spec, worn)
        else:
            self.director.spawn(spec, worn)
        log.info("%s %s", spec.name, "swapped in" if mode == "swap" else "joined")

    def _return_focus(self) -> None:
        """Hand focus back to the app the user was in before the home page."""
        pid = self.director.snapshot.frontmost_pid
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
        if app is not None:
            app.activateWithOptions_(0)

    # ---- debug ------------------------------------------------------------

    def set_overlay(self, on: bool) -> None:
        if on and self.overlay is None:
            pets = self.director.pets
            self.overlay = DebugOverlay(lambda: (pets[0].body.pet_w, pets[0].body.pet_h) if pets else (40.0, 52.0))
            self.director.on_tick.append(self.overlay.update)
        elif not on and self.overlay is not None:
            self.director.on_tick.remove(self.overlay.update)
            self.overlay.close()
            self.overlay = None

    def applicationWillTerminate_(self, _note) -> None:
        if self.director is not None:
            self.director.stop()


def run(debug: bool = False, demo: bool = False) -> None:
    level = os.environ.get("NIBBLE_LOG", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(name)s: %(message)s")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # menu bar only, no Dock icon
    delegate = AppDelegate.alloc().initWithDebug_demo_(debug, demo)
    app.setDelegate_(delegate)
    # runEventLoop only hooks Ctrl-C when it creates the NSApplication itself,
    # which it doesn't here, so hook it explicitly.
    AppHelper.installMachInterrupt()
    AppHelper.runEventLoop()
