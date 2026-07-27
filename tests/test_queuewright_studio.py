"""Contract tests for the local-only Studio service."""

from __future__ import annotations

import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from queuewright_studio.service import MAX_BODY_BYTES, StudioService, create_server


ROOT = Path(__file__).resolve().parents[1]


def example_bundle() -> dict[str, Any]:
    profile = json.loads(
        (ROOT / "profiles/example/profile.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "profiles/example/desired-state.json").read_text(encoding="utf-8")
    )
    return {"profile": profile, "manifest": manifest}


def university_bundle() -> dict[str, Any]:
    root = ROOT / "studio" / "templates" / "university"
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / "university.desired-state.json").read_text(
            encoding="utf-8"
        )
    )
    return {"profile": profile, "manifest": manifest}


def expected_resource_ids(bundle: dict[str, Any]) -> set[str]:
    manifest = bundle["manifest"]
    identifiers = {
        f"{collection}:{resource['key']}"
        for collection in (
            "groups",
            "organizations",
            "roles",
            "overviews",
            "macros",
            "checklist_templates",
            "triggers",
            "jobs",
            "report_profiles",
        )
        for resource in manifest[collection]
    }
    identifiers.update(
        f"agents:{agent['key']}" for agent in manifest["users"]["agents"]
    )
    identifiers.update(
        f"customers:{customer['key']}"
        for customer in manifest["users"]["customers"]
    )
    identifiers.update(f"tags:{tag}" for tag in manifest["tags"])
    for collection in (
        "ticket_fields",
        "user_fields",
        "organization_fields",
        "group_fields",
    ):
        identifiers.update(
            f"object_manager_fields:{field['name']}"
            for field in manifest["object_manager"][collection]
        )
    identifiers.update(
        f"core_workflows:{workflow['key']}"
        for workflow in manifest["object_manager"]["core_workflows"]
    )
    identifiers.update(
        f"uat_scenarios:{scenario['key']}"
        for scenario in bundle["profile"]["uat"]["scenarios"]
    )
    return identifiers


class StudioDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StudioService()

    def test_catalog_has_required_feature_ids(self) -> None:
        status, body = self.service.dispatch("GET", "/api/v1/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(
            {item["id"] for item in body["features"]},
            {
                "ticket_fields",
                "user_classification",
                "organization_classification",
                "group_classification",
                "overviews",
                "macros",
                "checklists",
                "triggers",
                "scheduled_reviews",
                "report_profiles",
                "cross_department_handoff",
                "sensitive_area_handling",
                "dummy_users_uat",
                "access_matrix",
            },
        )
        for feature in body["features"]:
            self.assertIsInstance(feature["name"], str)
            self.assertIsInstance(feature["category"], str)
            self.assertIs(type(feature["default_enabled"]), bool)
            self.assertIs(type(feature["locked"]), bool)

    def test_catalog_rejects_unknown_dependencies_and_cycles(self) -> None:
        catalog = json.loads(
            (ROOT / "studio/catalog/features.json").read_text(encoding="utf-8")
        )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        catalog_path = Path(temporary.name) / "features.json"

        unknown = copy.deepcopy(catalog)
        unknown["features"][0]["dependencies"] = ["not_a_feature"]
        catalog_path.write_text(json.dumps(unknown), encoding="utf-8")
        with self.assertRaisesRegex(
            RuntimeError, "unknown dependency: not_a_feature"
        ):
            StudioService(catalog_path)

        cyclic = copy.deepcopy(catalog)
        by_id = {feature["id"]: feature for feature in cyclic["features"]}
        by_id["macros"]["dependencies"] = ["triggers"]
        by_id["triggers"]["dependencies"] = ["macros"]
        catalog_path.write_text(json.dumps(cyclic), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "dependencies contain a cycle"):
            StudioService(catalog_path)

    def test_import_returns_full_project_and_compile_is_deterministic(self) -> None:
        bundle = example_bundle()
        status, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", bundle
        )
        self.assertEqual(status, 200)
        project = imported["project"]
        self.assertEqual(project["project_schema_version"], "1.0")
        self.assertEqual(project["id"], "example-project")
        self.assertEqual(project["name"], bundle["profile"]["display_name"])
        self.assertEqual(project["target_schema_version"], "1.0")
        self.assertEqual(project["profile"], bundle["profile"])
        self.assertEqual(project["manifest"], bundle["manifest"])
        self.assertEqual(
            set(project["resource_ownership"]),
            expected_resource_ids(bundle),
        )
        role_key = bundle["manifest"]["roles"][0]["key"]
        self.assertEqual(
            project["resource_ownership"][f"roles:{role_key}"], "core"
        )
        ticket_field = bundle["manifest"]["object_manager"]["ticket_fields"][0]
        self.assertEqual(
            project["resource_ownership"][
                f"object_manager_fields:{ticket_field['name']}"
            ],
            "ticket_fields",
        )
        scenario_key = bundle["profile"]["uat"]["scenarios"][0]["key"]
        self.assertEqual(
            project["resource_ownership"][f"uat_scenarios:{scenario_key}"],
            "access_matrix",
        )
        self.assertTrue(project["feature_state"]["dummy_users_uat"]["enabled"])
        self.assertFalse(project["feature_state"]["sensitive_area_handling"]["enabled"])
        self.assertTrue(
            all(
                isinstance(state["settings"], dict)
                for state in project["feature_state"].values()
            )
        )
        status, compiled = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled["profile"], bundle["profile"])
        self.assertEqual(compiled["manifest"], bundle["manifest"])
        self.assertEqual(compiled["project"], project)
        self.assertEqual(compiled["issues"], [])
        self.assertEqual(compiled["hashes"]["plan"], compiled["plan"]["plan_hash"])
        self.assertEqual(
            compiled["artifact_filenames"],
            [
                "example.project.json",
                "example.profile.json",
                "example.desired-state.json",
                "example.plan.json",
            ],
        )

    def test_university_template_round_trips_with_all_feature_families(self) -> None:
        status, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", university_bundle()
        )
        self.assertEqual(status, 200)
        project = imported["project"]
        self.assertEqual(project["target_schema_version"], "1.1")
        self.assertEqual(project["name"], "University service desk template")
        _, catalog = self.service.dispatch("GET", "/api/v1/catalog")
        self.assertEqual(
            {
                feature_id
                for feature_id, state in project["feature_state"].items()
                if state["enabled"]
            },
            {feature["id"] for feature in catalog["features"]},
        )
        ownership = project["resource_ownership"]
        self.assertEqual(
            ownership["macros:prepare_handoff"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership["triggers:record_handoff"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership["object_manager_fields:university_handoff_type"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership["tags:university/handoff_pending"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership["uat_scenarios:scenario_handoff"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership["groups:information_security"],
            "sensitive_area_handling",
        )
        self.assertEqual(
            ownership["triggers:mark_sensitive"],
            "sensitive_area_handling",
        )
        self.assertEqual(
            ownership["object_manager_fields:university_sensitive_area"],
            "sensitive_area_handling",
        )
        self.assertEqual(
            ownership["tags:university/sensitive"],
            "sensitive_area_handling",
        )
        self.assertEqual(
            ownership["tags:university/uat"],
            "access_matrix",
        )
        self.assertEqual(
            ownership["uat_scenarios:seed_information_security"],
            "access_matrix",
        )
        self.assertEqual(
            ownership["object_manager_fields:university_user_population"],
            "user_classification",
        )
        self.assertEqual(
            ownership["object_manager_fields:university_organization_class"],
            "organization_classification",
        )
        self.assertEqual(
            ownership["object_manager_fields:university_group_class"],
            "group_classification",
        )
        self.assertEqual(ownership["checklist_templates:standard_intake"], "checklists")
        self.assertEqual(ownership["jobs:review_stale_handoff"], "scheduled_reviews")
        self.assertEqual(ownership["report_profiles:managed_volume"], "report_profiles")
        feature_state = project["feature_state"]
        for feature in catalog["features"]:
            if feature_state[feature["id"]]["enabled"]:
                self.assertTrue(
                    all(
                        feature_state[dependency]["enabled"]
                        for dependency in feature["dependencies"]
                    )
                )

        status, compiled = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled["summary"]["counts"]["groups"], 11)
        self.assertEqual(compiled["summary"]["counts"]["roles"], 7)
        self.assertEqual(compiled["summary"]["counts"]["uat_scenarios"], 8)
        self.assertEqual(compiled["summary"]["counts"]["object_manager_fields"], 6)
        self.assertEqual(compiled["plan"]["source_schema_version"], "1.1")
        self.assertEqual(
            compiled["artifact_filenames"][0], "university.project.json"
        )

        status, migrated = self.service.dispatch(
            "POST", "/api/v2/migrate-project", {"project": project}
        )
        self.assertEqual(status, 200)
        self.assertEqual(migrated["project"]["project_schema_version"], "2.0")
        status, compiled_v2 = self.service.dispatch(
            "POST", "/api/v2/compile-project", {"project": migrated["project"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled_v2["issues"], [])
        self.assertEqual(
            compiled_v2["hashes"]["graph"],
            compiled_v2["graph"]["graph_hash"],
        )

    def test_compile_rejects_unsafe_project_contract(self) -> None:
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", example_bundle()
        )
        project = imported["project"]
        safe_project_id = project["id"]
        project["project_schema_version"] = "2.0"
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (422, "invalid_project", "project_schema_version"),
        )
        project["project_schema_version"] = "1.0"
        project["id"] = "../../unsafe"
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (400, "invalid_project", "id"),
        )
        project["id"] = safe_project_id
        project["feature_state"]["dummy_users_uat"]["enabled"] = False
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (422, "invalid_project", "feature_state.dummy_users_uat.enabled"),
        )
        project["feature_state"]["dummy_users_uat"]["enabled"] = True
        project["feature_state"]["macros"] = {
            "enabled": "yes",
            "settings": {},
        }
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (400, "invalid_project", "feature_state.macros"),
        )

    def test_compile_requires_exact_project_envelope(self) -> None:
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", example_bundle()
        )
        project = imported["project"]
        for invalid in (project, example_bundle(), {"project": project, "extra": True}):
            status, body = self.service.dispatch(
                "POST", "/api/v1/compile-project", invalid
            )
            self.assertEqual(
                (status, body["code"], body["path"]),
                (400, "invalid_request", "/api/v1/compile-project"),
            )

    def test_compile_rejects_disabled_feature_dependencies(self) -> None:
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", university_bundle()
        )
        project = imported["project"]
        project["feature_state"]["macros"]["enabled"] = False
        for resource, owner in project["resource_ownership"].items():
            if owner == "macros":
                project["resource_ownership"][resource] = "custom"
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (
                422,
                "invalid_project",
                "feature_state.cross_department_handoff.enabled",
            ),
        )
        self.assertIn("macros", body["message"])

    def test_compile_rejects_resource_owner_when_feature_is_disabled(self) -> None:
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", example_bundle()
        )
        project = imported["project"]
        project["feature_state"]["macros"]["enabled"] = False
        macro_resource = next(
            resource
            for resource, owner in project["resource_ownership"].items()
            if owner == "macros"
        )
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (
                422,
                "invalid_project",
                f"resource_ownership.{macro_resource}",
            ),
        )
        self.assertIn("macros", body["message"])

    def test_resource_ownership_requires_exact_inventory_and_valid_owner(self) -> None:
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", example_bundle()
        )
        project = imported["project"]
        group_resource = next(
            resource
            for resource in project["resource_ownership"]
            if resource.startswith("groups:")
        )
        missing = copy.deepcopy(project)
        del missing["resource_ownership"][group_resource]
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": missing}
        )
        self.assertEqual((status, body["code"]), (400, "invalid_project"))
        self.assertEqual(body["path"], "resource_ownership")
        self.assertIn(group_resource, body["message"])

        extra = copy.deepcopy(project)
        extra["resource_ownership"]["groups:not-real"] = "core"
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": extra}
        )
        self.assertEqual((status, body["code"]), (400, "invalid_project"))
        self.assertEqual(body["path"], "resource_ownership")
        self.assertIn("groups:not-real", body["message"])

        invalid = copy.deepcopy(project)
        invalid["resource_ownership"][group_resource] = "administrator"
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": invalid}
        )
        self.assertEqual((status, body["code"]), (400, "invalid_project"))
        self.assertEqual(body["path"], f"resource_ownership.{group_resource}")

    def test_default_ownership_classifies_special_resources(self) -> None:
        bundle = university_bundle()
        status, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", bundle
        )
        self.assertEqual(status, 200)
        ownership = imported["project"]["resource_ownership"]
        restricted_group = next(
            group
            for group in bundle["manifest"]["groups"]
            if group.get("restricted") is True
        )
        handoff = bundle["profile"]["uat"]["handoff_probe"]
        job_probe = bundle["profile"]["uat"]["job_probe"]
        self.assertEqual(
            ownership[f"groups:{restricted_group['key']}"],
            "sensitive_area_handling",
        )
        self.assertEqual(
            ownership[f"uat_scenarios:{handoff['ticket_key']}"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership[f"tags:{handoff['pending_tag']}"],
            "cross_department_handoff",
        )
        self.assertEqual(
            ownership[f"tags:{job_probe['marker_tag']}"],
            "scheduled_reviews",
        )

        custom_bundle = example_bundle()
        custom_bundle["manifest"]["tags"].append("example/custom")
        status, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", custom_bundle
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            imported["project"]["resource_ownership"]["tags:example/custom"],
            "custom",
        )

    def test_advanced_feature_settings_are_lossless_and_safe(self) -> None:
        bundle = example_bundle()
        _, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", bundle
        )
        project = imported["project"]
        advanced = {
            "approval": {
                "mode": "strict",
                "thresholds": [1, 2.5, None],
                "notify": False,
            }
        }
        project["feature_state"]["macros"]["settings"] = advanced
        status, compiled = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": project}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            compiled["project"]["feature_state"]["macros"]["settings"],
            advanced,
        )
        self.assertEqual(compiled["profile"], bundle["profile"])
        self.assertEqual(compiled["manifest"], bundle["manifest"])

        unsafe = copy.deepcopy(project)
        unsafe["feature_state"]["macros"]["settings"] = {
            "api_token": "not-a-real-token"
        }
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": unsafe}
        )
        self.assertEqual((status, body["code"]), (400, "invalid_project"))
        self.assertEqual(
            body["path"], "feature_state.macros.settings.api_token"
        )

        unsafe["feature_state"]["macros"]["settings"] = {
            "callback": "https://example.invalid/hook"
        }
        status, body = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": unsafe}
        )
        self.assertEqual((status, body["code"]), (400, "invalid_project"))
        self.assertEqual(
            body["path"], "feature_state.macros.settings.callback"
        )

    def test_import_and_compile_follow_supported_target_schema_version(self) -> None:
        bundle = example_bundle()
        bundle["profile"]["schema_version"] = "1.1"
        bundle["manifest"]["schema_version"] = "1.1"
        status, imported = self.service.dispatch(
            "POST", "/api/v1/import-bundle", bundle
        )
        self.assertEqual(status, 200)
        self.assertEqual(imported["project"]["target_schema_version"], "1.1")
        status, compiled = self.service.dispatch(
            "POST",
            "/api/v1/compile-project",
            {"project": imported["project"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled["project"]["target_schema_version"], "1.1")

    def test_validation_error_is_stable_api_error(self) -> None:
        bundle = example_bundle()
        bundle["profile"]["offline_only"] = False
        status, body = self.service.dispatch("POST", "/api/v1/import-bundle", bundle)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "invalid_bundle")
        self.assertEqual(body["path"], "bundle")
        self.assertIn("offline_only", body["message"])


class StudioHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.server = create_server(port=0)
        except OSError as error:
            raise unittest.SkipTest(f"loopback socket unavailable: {error}") from error
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        request_headers = {
            "Host": f"127.0.0.1:{self.server.server_port}",
            **(headers or {}),
        }
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def test_health_and_exact_response_content_type(self) -> None:
        status, headers, body = self.request("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "queuewright-studio")

    def test_post_rejects_non_json_host_origin_and_oversize(self) -> None:
        status, _, body = self.request(
            "POST",
            "/api/v1/import-bundle",
            b"{}",
            {"Content-Type": "application/json; charset=utf-8"},
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (415, "unsupported_media_type", "Content-Type"),
        )
        status, _, body = self.request(
            "GET", "/api/v1/health", headers={"Host": "localhost:8765"}
        )
        self.assertEqual(
            (status, body["code"], body["path"]), (400, "invalid_host", "Host")
        )
        status, _, body = self.request(
            "GET", "/api/v1/health", headers={"Origin": "https://example.invalid"}
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (400, "invalid_origin", "Origin"),
        )
        status, _, body = self.request(
            "POST",
            "/api/v1/import-bundle",
            b"{}",
            {
                "Content-Type": "application/json",
                "Content-Length": str(MAX_BODY_BYTES + 1),
            },
        )
        self.assertEqual((status, body["code"]), (413, "body_too_large"))

    def test_vite_loopback_origin_is_accepted_without_cors_headers(self) -> None:
        status, headers, body = self.request(
            "GET", "/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"}
        )
        self.assertEqual((status, body["status"]), (200, "ok"))
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_method_and_json_errors(self) -> None:
        status, _, body = self.request("PUT", "/api/v1/health")
        self.assertEqual((status, body["code"]), (405, "method_not_allowed"))
        status, _, body = self.request(
            "POST",
            "/api/v1/import-bundle",
            b"{",
            {"Content-Type": "application/json"},
        )
        self.assertEqual(
            (status, body["code"], body["path"]),
            (400, "invalid_json", "body"),
        )
