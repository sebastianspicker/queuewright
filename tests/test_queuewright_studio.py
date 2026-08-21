"""Studio import, ownership, and loopback HTTP boundaries."""

from __future__ import annotations

import copy
import http.client
import json
import threading
import unittest
from pathlib import Path
from typing import Any

from queuewright_studio.service import MAX_BODY_BYTES, StudioService, create_server

ROOT = Path(__file__).resolve().parents[1]


def example_bundle() -> dict[str, Any]:
    return {"profile": json.loads((ROOT / "profiles/example/profile.json").read_text()),
            "manifest": json.loads((ROOT / "profiles/example/desired-state.json").read_text())}


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

    def test_host_origin_content_type_and_size_boundaries(self) -> None:
        status, _, body = self.request("POST", "/api/v1/import-bundle", b"{}", {"Content-Type": "application/json; charset=utf-8"})
        self.assertEqual((status, body["code"]), (415, "unsupported_media_type"))
        status, _, body = self.request("GET", "/api/v1/health", headers={"Host": "localhost:8765"})
        self.assertEqual((status, body["code"]), (400, "invalid_host"))
        status, _, body = self.request("GET", "/api/v1/health", headers={"Origin": "https://example.invalid"})
        self.assertEqual((status, body["code"]), (400, "invalid_origin"))
        status, _, body = self.request("POST", "/api/v1/import-bundle", b"{}", {"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)})
        self.assertEqual((status, body["code"]), (413, "body_too_large"))
