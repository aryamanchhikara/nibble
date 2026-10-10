"""The `nibble` command."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nibble", description="A pixel-art pet that lives on your windows.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    run = sub.add_parser("run", help="start nibble in the foreground")
    run.add_argument("--debug", action="store_true", help="draw the edges pets can stand on")
    run.add_argument("--demo", action="store_true", help="speed up cheers, naps and peeking for recording")
    args = parser.parse_args(argv)

    if args.command == "run":
        if sys.platform != "darwin":
            parser.exit(1, "nibble only runs on macOS.\n")
        from .mac.app import run as run_app

        run_app(debug=args.debug, demo=args.demo)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
