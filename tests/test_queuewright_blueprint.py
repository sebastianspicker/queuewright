"""Blueprint migration and ownership fail-closed contracts."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from queuewright.errors import ConfigurationError
from queuewright.planning import compile_loaded_profile
from queuewright.projects import (
    compile_v2_project,
    migrate_v1_project,
    validate_exported_v2_project,
)
from queuewright.studio import StudioService

ROOT = Path(__file__).resolve().parents[1]
V2_FIXTURES = (
    ("minimal", "desired-state.json"),
    ("university", "university.desired-state.json"),
)


def v1_project() -> dict[str, object]:
    profile = json.loads((ROOT / "queuewright/examples/minimal/profile.json").read_text())
    manifest = json.loads((ROOT / "queuewright/examples/minimal/desired-state.json").read_text())
    status, payload = StudioService().dispatch("POST", "/api/v1/import-bundle", {
        "profile": profile, "manifest": manifest
    })
    assert status == 200
    return payload["project"]


class BlueprintTests(unittest.TestCase):
    def test_canonical_v2_fixtures_are_strict_and_stable(self) -> None:
        service = StudioService()
        for directory, manifest_name in V2_FIXTURES:
            with self.subTest(directory=directory):
                fixture = json.loads(
                    (ROOT / "queuewright/examples" / directory / "project-v2.json").read_text()
                )
                bundle = {
                    "profile": json.loads(
                        (ROOT / "queuewright/examples" / directory / "profile.json").read_text()
                    ),
                    "manifest": json.loads(
                        (ROOT / "queuewright/examples" / directory / manifest_name).read_text()
                    ),
                }
                status, imported = service.dispatch("POST", "/api/v1/import-bundle", bundle)
                self.assertEqual(status, 200)
                status, migrated = service.dispatch(
                    "POST", "/api/v2/migrate-project", {"project": imported["project"]}
                )
                self.assertEqual(status, 200)
                self.assertEqual(fixture, migrated["project"])
                self.assertEqual(validate_exported_v2_project(fixture), fixture)
                first = compile_v2_project(fixture)
                second = compile_v2_project(first["project"])
                self.assertEqual(first, second)

    def test_migration_preserves_hashes(self) -> None:
        source = v1_project()
        migrated = migrate_v1_project(source)
        v1_plan = compile_loaded_profile({"profile": source["profile"], "manifest": source["manifest"]})
        compiled = compile_v2_project(migrated)
        self.assertEqual(compiled["plan"]["source_hashes"], v1_plan["source_hashes"])
        self.assertEqual(compiled["hashes"]["plan"], v1_plan["plan_hash"])

    def test_v1_ownership_and_feature_inventory_remain_exact(self) -> None:
        missing_owner = copy.deepcopy(v1_project())
        missing_owner["resource_ownership"].popitem()  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "missing resource ownership"):
            migrate_v1_project(missing_owner)
        missing_feature = copy.deepcopy(v1_project())
        del missing_feature["feature_state"]["macros"]  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "feature_state must define every catalog feature exactly"):
            migrate_v1_project(missing_feature)

    def test_exported_v2_validator_rejects_stale_compiler_fields(self) -> None:
        exported = migrate_v1_project(v1_project())
        self.assertEqual(validate_exported_v2_project(exported), exported)
        stale = copy.deepcopy(exported)
        stale["workbook"]["services"] = []  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "compiler-derived workbook fields"):
            validate_exported_v2_project(stale)
