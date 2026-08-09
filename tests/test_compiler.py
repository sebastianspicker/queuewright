"""Characterization tests for deterministic symbolic plan compilation."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from queuewright.compiler import compile_loaded_profile

ROOT = Path(__file__).resolve().parents[1]


def example_loaded() -> dict[str, object]:
    root = ROOT / "profiles" / "example"
    return {
        "profile": json.loads((root / "profile.json").read_text(encoding="utf-8")),
        "manifest": json.loads((root / "desired-state.json").read_text(encoding="utf-8")),
    }


class CompilerTests(unittest.TestCase):
    def test_compilation_keeps_canonical_inventory_and_detaches_operation_state(self) -> None:
        loaded = example_loaded()
        first = compile_loaded_profile(loaded)  # type: ignore[arg-type]
        second = compile_loaded_profile(copy.deepcopy(loaded))  # type: ignore[arg-type]

        self.assertEqual(first, second)
        self.assertEqual(first["inventory"]["groups"], ["service", "service_general"])
        self.assertEqual(first["inventory"]["leaf_groups"], ["service_general"])
        group = next(
            item for item in first["operations"] if item["id"] == "groups:service_general"
        )
        group["desired_state"]["name"] = "mutated plan only"
        self.assertNotEqual(loaded["manifest"]["groups"][1]["name"], "mutated plan only")
