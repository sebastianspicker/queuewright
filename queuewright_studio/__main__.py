"""Run the local Studio HTTP service."""

from __future__ import annotations

import sys

from queuewright.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["studio", *sys.argv[1:]]))
