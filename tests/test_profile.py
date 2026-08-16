"""Characterization tests for the public profile-validation facade."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from queuewright.errors import ConfigurationError
from queuewright.profile import validate_loaded_profile

ROOT = Path(__file__).resolve().parents[1]


def example_loaded() -> dict[str, object]:
    root = ROOT / "profiles" / "example"
    return {
        "profile": json.loads((root / "profile.json").read_text(encoding="utf-8")),
        "manifest": json.loads((root / "desired-state.json").read_text(encoding="utf-8")),
    }


class ProfileValidationTests(unittest.TestCase):
    def test_validation_keeps_fail_closed_messages_for_contract_boundaries(self) -> None:
        cases = (
            (
                "offline-only",
                lambda loaded: loaded["profile"].__setitem__("offline_only", False),
                "profile requires display_name and offline_only true",
            ),
            (
                "namespace",
                lambda loaded: loaded["manifest"].__setitem__("technical_namespace", "bad"),
                "invalid managed prefix or technical namespace",
            ),
            (
                "safety",
                lambda loaded: loaded["manifest"]["safety_contract"].__setitem__("allow_delete", True),
                "invalid safety contract",
            ),
            (
                "tags",
                lambda loaded: loaded["manifest"].__setitem__("tags", ["outside/managed"]),
                "tags must be unique and namespaced",
            ),
        )
        for name, mutate, message in cases:
            with self.subTest(name=name):
                loaded = copy.deepcopy(example_loaded())
                mutate(loaded)
                with self.assertRaisesRegex(ConfigurationError, message):
                    validate_loaded_profile(loaded)  # type: ignore[arg-type]
