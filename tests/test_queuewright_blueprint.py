"""V2 offline blueprint contract tests."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from queuewright.blueprint import (
    compile_v2_project,
    load_capabilities,
    migrate_v1_project,
)
from queuewright.errors import ConfigurationError
from queuewright.compiler import compile_loaded_profile
from queuewright_studio.service import StudioService


ROOT = Path(__file__).resolve().parents[1]


def v1_project() -> dict[str, object]:
    profile = json.loads((ROOT / "profiles/example/profile.json").read_text())
    manifest = json.loads((ROOT / "profiles/example/desired-state.json").read_text())
    status, payload = StudioService().dispatch(
        "POST", "/api/v1/import-bundle", {"profile": profile, "manifest": manifest}
    )
    assert status == 200
    return payload["project"]


class BlueprintTests(unittest.TestCase):
    def test_migration_preserves_bundle_and_existing_hashes(self) -> None:
        source = v1_project()
        migrated = migrate_v1_project(source)
        self.assertEqual(migrated["bundle"], {key: source[key] for key in migrated["bundle"]})
        v1_plan = compile_loaded_profile({"profile": source["profile"], "manifest": source["manifest"]})
        compiled = compile_v2_project(migrated)
        self.assertEqual(compiled["plan"]["source_hashes"], v1_plan["source_hashes"])
        self.assertEqual(compiled["hashes"]["plan"], v1_plan["plan_hash"])

    def test_graph_and_capability_accounting_are_deterministic(self) -> None:
        migrated = migrate_v1_project(v1_project())
        first = compile_v2_project(migrated)
        second = compile_v2_project(copy.deepcopy(migrated))
        self.assertEqual(first["graph"], second["graph"])
        self.assertEqual(
            set(migrated["workbook"]["capability_decisions"]),
            {item["id"] for item in load_capabilities()},
        )
        graph_ids = {node["id"] for node in first["graph"]["nodes"]}
        capability_ids = {
            f"capability:{capability['id']}" for capability in load_capabilities()
        }
        operation_ids = {
            operation["id"] for operation in first["plan"]["operations"]
        }
        self.assertEqual(graph_ids, capability_ids | operation_ids)
        for node in first["graph"]["nodes"]:
            if node["resource_kind"] != "capability_gate":
                self.assertTrue(
                    any(
                        dependency.startswith("capability:")
                        for dependency in node["dependencies"]
                    )
                )
        decisions = migrated["workbook"]["capability_decisions"]
        self.assertEqual(decisions["tags"]["completion"], "ready")
        self.assertEqual(
            decisions["identity-security"]["completion"],
            "decision_required",
        )
        self.assertEqual(decisions["ai"]["completion"], "blocked")
        self.assertFalse(decisions["ai"]["enabled"])
        self.assertEqual(
            decisions["fields-core-workflows"]["delivery"],
            "guided_manual",
        )
        self.assertEqual(decisions["service-topology"]["delivery"], "automated")

    def test_v2_reuses_the_exact_v1_ownership_and_feature_contract(self) -> None:
        migrated = migrate_v1_project(v1_project())
        missing_owner = copy.deepcopy(migrated)
        missing_owner["bundle"]["resource_ownership"].popitem()
        with self.assertRaisesRegex(ConfigurationError, "missing resource ownership"):
            compile_v2_project(missing_owner)

        missing_feature = copy.deepcopy(migrated)
        del missing_feature["bundle"]["feature_state"]["macros"]
        with self.assertRaisesRegex(
            ConfigurationError,
            "feature_state must define every catalog feature exactly",
        ):
            compile_v2_project(missing_feature)

    def test_derived_workbook_drift_and_impossible_decisions_fail_closed(self) -> None:
        migrated = migrate_v1_project(v1_project())
        drifted = copy.deepcopy(migrated)
        drifted["workbook"]["services"] = []
        with self.assertRaisesRegex(ConfigurationError, "compiler-derived"):
            compile_v2_project(drifted)

        unsupported = copy.deepcopy(migrated)
        unsupported["workbook"]["capability_decisions"]["ai"].update(
            {"enabled": True, "completion": "blocked"}
        )
        with self.assertRaisesRegex(ConfigurationError, "must use registry"):
            compile_v2_project(unsupported)

        missing_dependency = copy.deepcopy(migrated)
        missing_dependency["workbook"]["capability_decisions"]["organization"].update(
            {"enabled": False, "completion": "decision_required"}
        )
        with self.assertRaisesRegex(ConfigurationError, "requires enabled dependency"):
            compile_v2_project(missing_dependency)

        fabricated_evidence = copy.deepcopy(migrated)
        fabricated_evidence["workbook"]["capability_decisions"]["tags"][
            "completion"
        ] = "verified"
        with self.assertRaisesRegex(
            ConfigurationError, "cannot claim applied or verified"
        ):
            compile_v2_project(fabricated_evidence)

    def test_derived_services_use_workflow_groups_and_role_acl_membership(self) -> None:
        source = v1_project()
        source["manifest"]["object_manager"]["core_workflows"].append(
            {
                "actions": "allow ticket creation only for selected managed services",
                "context": "customer_create",
                "key": "customer_create_entry_points",
                "match": "authenticated customer and group in [service_general]",
            }
        )
        source["profile"]["presentation"]["core_workflow_names"][
            "customer_create_entry_points"
        ] = "Example Prototype · CW · Customer entry points"
        source["resource_ownership"][
            "core_workflows:customer_create_entry_points"
        ] = "core"

        services = {
            service["key"]: service
            for service in migrate_v1_project(source)["workbook"]["services"]
        }
        self.assertTrue(services["service_general"]["customer_entry_point"])
        self.assertEqual(services["service_general"]["synthetic_agents"], ["service"])
        self.assertEqual(services["service"]["synthetic_agents"], [])

    def test_capability_registry_rejects_cycles(self) -> None:
        catalog = {"capabilities": load_capabilities()}
        by_id = {item["id"]: item for item in catalog["capabilities"]}
        by_id["organization"]["dependencies"] = ["service-topology"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "contain a cycle"):
                load_capabilities(path)

    def test_extensions_reject_urls_and_credential_shaped_keys(self) -> None:
        migrated = migrate_v1_project(v1_project())
        unsafe = copy.deepcopy(migrated)
        unsafe["extensions"] = {"api_key": "not-a-secret"}
        with self.assertRaisesRegex(ConfigurationError, "sensitive key"):
            compile_v2_project(unsafe)
        unsafe["extensions"] = {"note": "https://example.invalid"}
        with self.assertRaisesRegex(ConfigurationError, "URLs"):
            compile_v2_project(unsafe)

    def test_service_v2_endpoints_are_additive(self) -> None:
        service = StudioService()
        source = v1_project()
        status, migrated = service.dispatch(
            "POST", "/api/v2/migrate-project", {"project": source}
        )
        self.assertEqual(status, 200)
        status, compiled = service.dispatch(
            "POST", "/api/v2/compile-project", {"project": migrated["project"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled["bundle"], migrated["project"]["bundle"])
        self.assertEqual(compiled["issues"], [])


if __name__ == "__main__":
    unittest.main()
