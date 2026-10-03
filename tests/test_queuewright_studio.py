"""Studio import, ownership, and loopback HTTP boundaries."""

from __future__ import annotations

import copy
import http.client
import json
import threading
import unittest
from pathlib import Path
from typing import Any

from queuewright.studio import StudioService, create_server
from queuewright.studio.server import MAX_BODY_BYTES

ROOT = Path(__file__).resolve().parents[1]


def example_bundle() -> dict[str, Any]:
    return {"profile": json.loads((ROOT / "queuewright/examples/minimal/profile.json").read_text()),
            "manifest": json.loads((ROOT / "queuewright/examples/minimal/desired-state.json").read_text())}


class StudioDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StudioService()

    def test_import_compile_is_deterministic(self) -> None:
        bundle = example_bundle()
        status, imported = self.service.dispatch("POST", "/api/v1/import-bundle", bundle)
        self.assertEqual(status, 200)
        project = imported["project"]
        status, first = self.service.dispatch("POST", "/api/v1/compile-project", {"project": project})
        self.assertEqual(status, 200)
        status, second = self.service.dispatch("POST", "/api/v1/compile-project", {"project": copy.deepcopy(project)})
        self.assertEqual((status, first["hashes"]), (200, second["hashes"]))

    def test_unsafe_project_and_path_are_rejected(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        project = imported["project"]
        project["id"] = "../../unsafe"
        status, body = self.service.dispatch("POST", "/api/v1/compile-project", {"project": project})
        self.assertEqual((status, body["path"]), (400, "id"))

    def test_resource_ownership_is_exact(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        project = imported["project"]
        resource = next(item for item in project["resource_ownership"] if item.startswith("groups:"))
        del project["resource_ownership"][resource]
        status, body = self.service.dispatch("POST", "/api/v1/compile-project", {"project": project})
        self.assertEqual((status, body["code"], body["path"]), (400, "invalid_project", "resource_ownership"))

    def test_settings_reject_urls_and_credentials(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        project = imported["project"]
        project["feature_state"]["macros"]["settings"] = {"api_key": "secret"}
        status, body = self.service.dispatch("POST", "/api/v1/compile-project", {"project": project})
        self.assertEqual((status, body["code"]), (400, "invalid_project"))

    def test_canonical_v2_compile_accepts_v1_and_matches_the_legacy_adapter(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        v1_project = imported["project"]
        status, compiled_from_bundle = self.service.dispatch(
            "POST", "/api/v2/compile", copy.deepcopy(example_bundle())
        )
        self.assertEqual(status, 200)
        status, compiled_from_v1 = self.service.dispatch(
            "POST", "/api/v2/compile", {"project": copy.deepcopy(v1_project)}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled_from_v1["project"]["project_schema_version"], "2.0")
        self.assertEqual(compiled_from_bundle, compiled_from_v1)

        status, migrated = self.service.dispatch(
            "POST", "/api/v2/migrate-project", {"project": copy.deepcopy(v1_project)}
        )
        self.assertEqual(status, 200)
        status, compiled_from_v2 = self.service.dispatch(
            "POST", "/api/v2/compile-project", {"project": migrated["project"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled_from_v1, compiled_from_v2)

        status, legacy = self.service.dispatch(
            "POST", "/api/v1/compile-project", {"project": copy.deepcopy(v1_project)}
        )
        self.assertEqual(status, 200)
        self.assertEqual(legacy["plan"], compiled_from_v1["plan"])
        self.assertEqual(legacy["hashes"]["plan"], compiled_from_v1["hashes"]["plan"])

    def test_v2_round_trip_and_bundle_structural_edit_are_normalized(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        _, migrated = self.service.dispatch("POST", "/api/v2/migrate-project", {"project": imported["project"]})
        exported = migrated["project"]
        status, first = self.service.dispatch("POST", "/api/v2/compile", {"project": copy.deepcopy(exported)})
        self.assertEqual(status, 200)
        status, second = self.service.dispatch("POST", "/api/v2/compile", {"project": copy.deepcopy(first["project"])})
        self.assertEqual((status, second), (200, first))

        draft = copy.deepcopy(exported)
        group = draft["bundle"]["manifest"]["groups"][1]
        group["name"] = "Example Prototype · Service::Edited"
        draft["bundle"]["manifest"]["tags"].append("example/added")
        draft["workbook"]["capability_decisions"]["organization"]["risk"] = "stale-registry-value"
        status, compiled = self.service.dispatch("POST", "/api/v2/compile", {"project": draft})
        self.assertEqual(status, 200)
        self.assertEqual(
            next(service["name"] for service in compiled["project"]["workbook"]["services"] if service["key"] == group["key"]),
            group["name"],
        )
        self.assertEqual(
            compiled["project"]["workbook"]["capability_decisions"]["organization"]["risk"],
            "medium",
        )
        self.assertEqual(compiled["project"]["bundle"]["resource_ownership"]["tags:example/added"], "custom")
        self.assertNotEqual(compiled["project"], draft)

        editable_only = copy.deepcopy(draft)
        for field in ("services", "policies", "uat"):
            del editable_only["workbook"][field]
        status, materialized = self.service.dispatch("POST", "/api/v2/compile", {"project": editable_only})
        self.assertEqual(status, 200)
        self.assertEqual(
            set(materialized["project"]["workbook"]),
            {"organization", "services", "policies", "capability_decisions", "uat"},
        )

        stale_state = copy.deepcopy(exported)
        stale_state["bundle"]["feature_state"].pop("cross_department_handoff")
        stale_state["bundle"]["feature_state"]["scheduled_reviews"]["enabled"] = True
        status, normalized = self.service.dispatch("POST", "/api/v2/compile", {"project": stale_state})
        self.assertEqual(status, 200)
        feature_state = normalized["project"]["bundle"]["feature_state"]
        self.assertFalse(feature_state["cross_department_handoff"]["enabled"])
        self.assertTrue(feature_state["scheduled_reviews"]["enabled"])
        self.assertTrue(feature_state["triggers"]["enabled"])

    def test_v2_feature_governance_and_access_edits_remain_authoritative(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        _, migrated = self.service.dispatch("POST", "/api/v2/migrate-project", {"project": imported["project"]})
        draft = migrated["project"]
        draft["bundle"]["feature_state"]["macros"]["settings"] = {"presentation": "compact"}
        draft["workbook"]["organization"]["service_owner_role"] = "governance"
        owner = next(key for key in draft["bundle"]["resource_ownership"] if key.startswith("roles:"))
        draft["bundle"]["resource_ownership"][owner] = "access_matrix"
        status, compiled = self.service.dispatch("POST", "/api/v2/compile", {"project": draft})
        self.assertEqual(status, 200)
        project = compiled["project"]
        self.assertEqual(project["bundle"]["feature_state"]["macros"]["settings"], {"presentation": "compact"})
        self.assertEqual(project["workbook"]["organization"]["service_owner_role"], "governance")
        self.assertEqual(project["bundle"]["resource_ownership"][owner], "access_matrix")
        self.assertTrue(all(node["owner"] == "governance" for node in compiled["graph"]["nodes"] if node["id"].startswith("capability:")))

    def test_v2_invalid_editable_content_is_rejected(self) -> None:
        _, imported = self.service.dispatch("POST", "/api/v1/import-bundle", example_bundle())
        _, migrated = self.service.dispatch("POST", "/api/v2/migrate-project", {"project": imported["project"]})
        draft = migrated["project"]
        draft["workbook"]["organization"]["api_key"] = "not-allowed"
        status, body = self.service.dispatch("POST", "/api/v2/compile", {"project": draft})
        self.assertEqual((status, body["code"]), (422, "invalid_project"))

        invalid_owner = copy.deepcopy(migrated["project"])
        owner = next(key for key in invalid_owner["bundle"]["resource_ownership"] if key.startswith("roles:"))
        invalid_owner["bundle"]["resource_ownership"][owner] = "not-a-catalog-owner"
        status, body = self.service.dispatch("POST", "/api/v2/compile", {"project": invalid_owner})
        self.assertEqual((status, body["code"]), (422, "invalid_project"))

        invalid_feature = copy.deepcopy(migrated["project"])
        invalid_feature["bundle"]["feature_state"]["macros"]["settings"] = {"api_key": "not-allowed"}
        status, body = self.service.dispatch("POST", "/api/v2/compile", {"project": invalid_feature})
        self.assertEqual((status, body["code"]), (422, "invalid_project"))


class StudioHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], dict[str, Any]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.server.server_port}", **(headers or {})})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), json.loads(response.read().decode())
        connection.close()
        return result

    def test_catalog_and_editor_compile_over_http(self) -> None:
        status, headers, catalog = self.request("GET", "/api/v1/catalog")
        self.assertEqual(status, 200)
        self.assertIn("schema_version", catalog)
        self.assertIn("features", catalog)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        status, headers, compiled = self.request(
            "POST", "/api/v2/compile-editor", json.dumps(example_bundle()).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(compiled["representation"], "editor-1")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(headers["Content-Type"].startswith("application/json"))

    def test_host_origin_content_type_and_size_boundaries(self) -> None:
        status, _, body = self.request("POST", "/api/v1/import-bundle", b"{}", {"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual((status, body["code"]), (415, "unsupported_media_type"))
        status, _, body = self.request("GET", "/api/v1/health", headers={"Host": "localhost:8765"})
        self.assertEqual((status, body["code"]), (400, "invalid_host"))
        status, _, body = self.request("GET", "/api/v1/health", headers={"Origin": "https://example.invalid"})
        self.assertEqual((status, body["code"]), (400, "invalid_origin"))
        status, _, body = self.request("POST", "/api/v1/import-bundle", b"{}", {"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)})
        self.assertEqual((status, body["code"]), (413, "body_too_large"))
