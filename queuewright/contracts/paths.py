"""Paths for packaged catalogs."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def catalog_path(name: str) -> Path:
    return PACKAGE_ROOT / "catalogs" / name

