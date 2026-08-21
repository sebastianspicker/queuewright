"""Blueprint migration and ownership fail-closed contracts."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from queuewright.blueprint import compile_v2_project, migrate_v1_project
from queuewright.compiler import compile_loaded_profile
from queuewright.errors import ConfigurationError
from queuewright_studio.service import StudioService

ROOT = Path(__file__).resolve().parents[1]


def v1_project() -> dict[str, object]:
    profile = json.loads((ROOT / "profiles/example/profile.json").read_text())
    manifest = json.loads((ROOT / "profiles/example/desired-state.json").read_text())
    status, payload = StudioService().dispatch("POST", "/api/v1/import-bundle", {
        "profile": profile, "manifest": manifest
    })
    assert status == 200
    return payload["project"]


class BlueprintTests(unittest.TestCase):
    def test_migration_preserves_hashes(self) -> None:
        source = v1_project()
        migrated = migrate_v1_project(source)
        v1_plan = compile_loaded_profile({"profile": source["profile"], "manifest": source["manifest"]})
        compiled = compile_v2_project(migrated)
        self.assertEqual(compiled["plan"]["source_hashes"], v1_plan["source_hashes"])
        self.assertEqual(compiled["hashes"]["plan"], v1_plan["plan_hash"])

    def test_ownership_and_feature_inventory_are_exact(self) -> None:
        migrated = migrate_v1_project(v1_project())
        missing_owner = copy.deepcopy(migrated)
        missing_owner["bundle"]["resource_ownership"].popitem()  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "missing resource ownership"):
            compile_v2_project(missing_owner)
        missing_feature = copy.deepcopy(migrated)
        del missing_feature["bundle"]["feature_state"]["macros"]  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "feature_state must define every catalog feature exactly"):
            compile_v2_project(missing_feature)
