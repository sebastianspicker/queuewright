"""Lossless editor transport projection of canonical compilation artifacts."""

from __future__ import annotations

from typing import Any


def editor_representation(compiled: dict[str, Any]) -> dict[str, Any]:
    """Elide only values recoverable from the same authoritative response.

    The project owns the bundle. Operation graph nodes share desired state with
    their plan operation; capability gates retain their own desired state.
    Canonical artifacts and their hashes are otherwise unchanged.
    """
    operation_ids = {operation["id"] for operation in compiled["plan"]["operations"]}
    nodes = [
        {key: value for key, value in node.items() if key != "desired"}
        if node["id"] in operation_ids else node
        for node in compiled["graph"]["nodes"]
    ]
    return {
        "representation": "editor-1",
        **{key: value for key, value in compiled.items() if key not in {"bundle", "graph"}},
        "graph": {**compiled["graph"], "nodes": nodes},
    }
