"""Canonical JSON rendering shared by plans, projects, and HTTP responses."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return the byte-stable JSON representation used for all hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    """Hash canonical JSON without accepting alternate serializations."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
