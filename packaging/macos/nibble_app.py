"""Nibble.app's entry point: the same as `nibble run`.

Extra arguments pass through, so `open Nibble.app --args --demo` works for recording.
"""

import sys

from nibble.cli import main

sys.exit(main(["run", *sys.argv[1:]]))
