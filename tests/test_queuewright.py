"""Small offline compiler and path-safety contracts."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from queuewright.cli import main
from queuewright.compiler import compile_plan
from queuewright.errors import ConfigurationError
from queuewright.profile import validate_profile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "profiles" / "example"


def bundle() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads((EXAMPLE / "profile.json").read_text(encoding="utf-8")),
        json.loads((EXAMPLE / "desired-state.json").read_text(encoding="utf-8")),
    )


class QueuewrightTests(unittest.TestCase):
    def write_bundle(self, profile: dict[str, object], manifest: dict[str, object]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (root / "desired-state.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def test_plan_is_deterministic_inert_and_dependency_ordered(self) -> None:
        first = compile_plan(EXAMPLE)
        self.assertEqual(first, compile_plan(EXAMPLE))
        self.assertFalse(first["safety"]["network_capability"])
        operations = {item["id"]: item for item in first["operations"]}
        self.assertEqual(operations["groups:service_general"]["depends_on"], ["groups:service"])
        self.assertEqual(operations["groups:service_general"]["action"], "create_inactive")
        sequences = [item["sequence"] for item in first["operations"]]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_safety_rejections(self) -> None:
        profile, manifest = bundle()
        unsafe = copy.deepcopy(manifest)
        unsafe["safety_contract"]["allow_delete"] = True  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "safety contract"):
            validate_profile(self.write_bundle(profile, unsafe))
        unsafe = copy.deepcopy(manifest)
        unsafe["groups"][0]["credential"] = "must-not-pass"  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "credential"):
            validate_profile(self.write_bundle(profile, unsafe))

    def test_profile_path_and_output_are_protected(self) -> None:
        profile, manifest = bundle()
        profile["manifest"] = "../outside.json"
        with self.assertRaisesRegex(ConfigurationError, "escapes"):
            validate_profile(self.write_bundle(profile, manifest))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["plan", str(EXAMPLE), "--output", str(EXAMPLE / "profile.json")])
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["plan", str(EXAMPLE), "--output", str(EXAMPLE / ".env.plan.json")])
