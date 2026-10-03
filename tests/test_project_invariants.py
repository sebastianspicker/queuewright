"""Invariants the golden baseline cannot see: aliasing, error precedence, CLI self-test."""

from __future__ import annotations

import contextlib
import copy
import io
import unittest
from typing import Any

from queuewright.cli import main
from queuewright.studio import StudioService
from tests.test_behavior_baseline import _bundle


def _projects(service: StudioService) -> tuple[dict[str, Any], dict[str, Any]]:
    _, imported = service.dispatch("POST", "/api/v1/import-bundle", _bundle("minimal"))
    v1 = imported["project"]
    _, migrated = service.dispatch("POST", "/api/v2/migrate-project", {"project": copy.deepcopy(v1)})
    return v1, migrated["project"]


class ResultIsolationTests(unittest.TestCase):
    def test_mutating_results_does_not_leak_into_later_responses(self) -> None:
        service = StudioService()
        v1, v2 = _projects(service)
        _, first = service.dispatch("POST", "/api/v2/compile", {"project": copy.deepcopy(v2)})
        _, catalog = service.dispatch("GET", "/api/v1/catalog")
        expected_catalog = copy.deepcopy(catalog)
        expected = copy.deepcopy(first)

        for decision in first["project"]["workbook"]["capability_decisions"].values():
            decision["dependencies"].append("tampered")
        for node in first["graph"]["nodes"]:
            node["dependencies"].append("tampered")
        for state in first["project"]["bundle"]["feature_state"].values():
            state["settings"]["tampered"] = True
        for feature in catalog["features"]:
            feature["settings"]["tampered"] = True
            feature["dependencies"].append("tampered")
        for decision in v2["workbook"]["capability_decisions"].values():
            decision["dependencies"].append("tampered")
        v1["feature_state"]["macros"]["settings"]["tampered"] = True

        _, second = service.dispatch("POST", "/api/v2/compile", {"project": copy.deepcopy(expected["project"])})
        self.assertEqual(second, expected)
        self.assertEqual(service.dispatch("GET", "/api/v1/catalog")[1], expected_catalog)
        _, fresh_import = service.dispatch("POST", "/api/v1/import-bundle", _bundle("minimal"))
        self.assertNotIn("tampered", fresh_import["project"]["feature_state"]["macros"]["settings"])


class ErrorPrecedenceTests(unittest.TestCase):
    """With several faults, the first reported error is part of the HTTP contract."""

    def setUp(self) -> None:
        self.service = StudioService()
        self.v1, self.v2 = _projects(self.service)

    def compile_v1(self, project: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return self.service.dispatch("POST", "/api/v1/compile-project", {"project": project})

    def compile_v2(self, project: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return self.service.dispatch("POST", "/api/v2/compile", {"project": project})

    def test_missing_field_is_reported_before_unknown_field(self) -> None:
        project = copy.deepcopy(self.v1)
        del project["feature_state"]
        project["extra"] = 1
        self.assertEqual(self.compile_v1(project), (400, {
            "code": "invalid_project", "path": "project", "message": "missing required field: feature_state",
        }))

    def test_schema_version_is_reported_before_id(self) -> None:
        project = copy.deepcopy(self.v1)
        project["id"] = "Bad"
        project["project_schema_version"] = "9"
        self.assertEqual(self.compile_v1(project), (422, {
            "code": "invalid_project", "path": "project_schema_version",
            "message": "project_schema_version must be 1.0",
        }))

    def test_ownership_inventory_precedes_feature_state_and_reports_smallest_key(self) -> None:
        project = copy.deepcopy(self.v1)
        groups = sorted(key for key in project["resource_ownership"] if key.startswith("groups:"))
        for key in groups[:2]:
            del project["resource_ownership"][key]
        project["feature_state"]["macros"] = {"enabled": "x", "settings": {}}
        self.assertEqual(self.compile_v1(project), (400, {
            "code": "invalid_project", "path": "resource_ownership",
            "message": f"missing resource ownership: {groups[0]}",
        }))

    def test_unknown_ownership_precedes_invalid_owner(self) -> None:
        project = copy.deepcopy(self.v1)
        first_group = min(key for key in project["resource_ownership"] if key.startswith("groups:"))
        project["resource_ownership"]["groups:zz"] = "core"
        project["resource_ownership"][first_group] = "nobody"
        self.assertEqual(self.compile_v1(project), (400, {
            "code": "invalid_project", "path": "resource_ownership",
            "message": "unknown resource ownership: groups:zz",
        }))

    def test_locked_feature_precedes_dependency_errors(self) -> None:
        project = copy.deepcopy(self.v1)
        project["feature_state"]["triggers"]["enabled"] = False
        project["feature_state"]["access_matrix"]["enabled"] = False
        self.assertEqual(self.compile_v1(project), (422, {
            "code": "invalid_project", "path": "feature_state.access_matrix.enabled",
            "message": "locked features must remain enabled",
        }))

    def test_v2_header_precedes_bundle_and_extensions_precede_workbook(self) -> None:
        project = copy.deepcopy(self.v2)
        project["id"] = "Bad"
        project["bundle"]["profile"]["offline_only"] = False
        self.assertEqual(self.compile_v2(project), (422, {
            "code": "invalid_project", "path": "project",
            "message": "id must be a lowercase safe project key",
        }))
        project = copy.deepcopy(self.v2)
        del project["workbook"]["capability_decisions"]["tags"]
        project["extensions"] = []
        self.assertEqual(self.compile_v2(project), (422, {
            "code": "invalid_project", "path": "project", "message": "extensions must be an object",
        }))


class CliSelfTestTests(unittest.TestCase):
    def test_self_test_validates_packaged_examples(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["self-test"]), 0)
        self.assertEqual(stdout.getvalue(), "self-test: ok\n")


if __name__ == "__main__":
    unittest.main()
