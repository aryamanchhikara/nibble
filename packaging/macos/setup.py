"""py2app config for Nibble.app. Run it through scripts/build_dmg.sh.

It lives here, not at the repo root, because setuptools would otherwise read
pyproject.toml's dependencies, and py2app refuses to build with those set.
"""

import tomllib
from pathlib import Path

from setuptools import setup

HERE = Path(__file__).resolve().parent
VERSION = tomllib.loads((HERE.parents[1] / "pyproject.toml").read_text())["project"]["version"]

OPTIONS = {
    # Copy nibble as a real folder, not into the zip: CoreText needs real paths for the fonts.
    "packages": ["nibble"],
    "iconfile": str(HERE / "Nibble.icns"),
    "plist": {
        "CFBundleName": "Nibble",
        "CFBundleDisplayName": "Nibble",
        "CFBundleIdentifier": "com.karroulabs.nibble",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
        # Menu bar only from the first moment (app.py also sets this, but only once Python is up).
        "LSUIElement": True,
        "NSHumanReadableCopyright": "© 2026 Aryaman Chhikara",
        # No usage descriptions: nibble uses no protected APIs (no Accessibility, Screen
        # Recording, camera or Input Monitoring). See "Privacy and permissions" in the README.
    },
}

setup(name="Nibble", version=VERSION, app=[str(HERE / "nibble_app.py")], options={"py2app": OPTIONS})
