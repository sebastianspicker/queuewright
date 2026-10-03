"""Packaged fictional example profiles and projects."""

from __future__ import annotations

from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent


def example_path(name: str) -> Path:
    """Return the directory of one packaged example."""
    return EXAMPLES_ROOT / name
