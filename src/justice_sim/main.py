"""App entry point for the Justice Monument Simulator."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Justice Monument Simulator")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Launch and exit immediately to validate startup wiring.",
    )
    args = parser.parse_args(argv)

    if args.smoke:
        print("Smoke OK")
        return 0

    print("Entry point stub: launch not implemented. Use --smoke.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
