"""HTTP complexity bounds and lossless editor response compatibility."""

from __future__ import annotations

import copy
import http.client
import json
import socket
import threading
import unittest
from io import BytesIO
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from queuewright.contracts.safety import MAX_JSON_DEPTH, SafeJsonError, validate_safe_json
from queuewright.studio.input import read_json_body
from queuewright.studio.server import StudioService, create_server

ROOT = Path(__file__).resolve().parents[1]


def nested(depth: int) -> list:
    value = []
    for _ in range(depth - 1):
        value = [value]
    return value


class JsonBoundaryTests(unittest.TestCase):
    def parse(self, raw: bytes):
        return read_json_body(
            {"Content-Type": "application/json", "Content-Length": str(len(raw))},
            BytesIO(raw), "application/json", 2 * 1024 * 1024,
            lambda code, path, message: {"code": code, "path": path, "message": message},
        )

    def test_container_depth_boundary_and_cycles(self):
        validate_safe_json(nested(MAX_JSON_DEPTH), "settings")
        for value in (nested(MAX_JSON_DEPTH + 1), nested(2000)):
            with self.assertRaisesRegex(SafeJsonError, "nesting levels"):
                validate_safe_json(value, "settings")
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(SafeJsonError):
            validate_safe_json(cyclic, "settings")

    def test_parser_returns_errors_for_numeric_and_depth_limits(self):
        valid, failure = self.parse(b'[' * MAX_JSON_DEPTH + b'0' + b']' * MAX_JSON_DEPTH)
        self.assertIsNone(failure)
        self.assertIsInstance(valid, list)
        for raw in (b'1' * 5000, b'[' * 2000 + b'0' + b']' * 2000):
            with self.subTest(size=len(raw)):
                value, failure = self.parse(raw)
                self.assertIsNone(value)
                self.assertEqual((failure[0], failure[1]["code"]), (400, "invalid_json"))

    def test_content_length_requires_plain_decimal_digits(self):
        for raw_length in ("+2", "1_0", "-1", ""):
            with self.subTest(raw_length=raw_length):
                value, failure = read_json_body(
                    {"Content-Type": "application/json", "Content-Length": raw_length},
                    BytesIO(b"{}"),
                    "application/json",
                    2 * 1024 * 1024,
                    lambda code, path, message: {
                        "code": code,
                        "path": path,
                        "message": message,
                    },
                )
                self.assertIsNone(value)
                self.assertEqual((failure[0], failure[1]["code"]), (411, "length_required"))

    def test_direct_service_rejects_depth_before_copying(self):
        project = json.loads((ROOT / 'queuewright/examples/minimal/project-v2.json').read_text())
        project["extensions"] = {"nested": nested(2000)}
        status, error = StudioService().dispatch("POST", "/api/v2/compile", {"project": project})
        self.assertEqual((status, error["code"]), (400, "invalid_json"))


class EditorRepresentationTests(unittest.TestCase):
    def test_editor_representation_restores_identical_artifacts_and_validates_schema(self):
        service = StudioService()
        schema_dir = ROOT / "queuewright/contracts/schemas"
        schemas = [json.loads(path.read_text()) for path in schema_dir.glob("*.schema.json")]
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
        schema = json.loads((schema_dir / "queuewright-editor-compile.schema.json").read_text())
        validator = Draft202012Validator(schema, registry=registry)
        for example in ("minimal", "university"):
            project = json.loads((ROOT / f"queuewright/examples/{example}/project-v2.json").read_text())
            body = {"project": project}
            status, full = service.dispatch("POST", "/api/v2/compile", copy.deepcopy(body))
            editor_status, compact = service.dispatch("POST", "/api/v2/compile-editor", copy.deepcopy(body))
            self.assertEqual((status, editor_status), (200, 200))
            validator.validate(compact)
            self.assertLess(len(json.dumps(compact)), len(json.dumps(full)))
            restored = copy.deepcopy(compact)
            self.assertEqual(restored.pop("representation"), "editor-1")
            restored["bundle"] = restored["project"]["bundle"]
            operations = {operation["id"]: operation for operation in restored["plan"]["operations"]}
            for node in restored["graph"]["nodes"]:
                if "desired" not in node:
                    node["desired"] = operations[node["id"]]["desired_state"]
            self.assertEqual(restored, full)

    def test_compact_route_preserves_errors(self):
        service = StudioService()
        invalid = {"project": {"project_schema_version": "2.0"}}
        self.assertEqual(service.dispatch("POST", "/api/v2/compile-editor", invalid),
                         service.dispatch("POST", "/api/v2/compile", invalid))


class HttpLimitsTests(unittest.TestCase):
    @staticmethod
    def _raw_request(port: int, request: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(request)
            response = bytearray()
            while True:
                chunk = connection.recv(64 * 1024)
                if not chunk:
                    return bytes(response)
                response.extend(chunk)

    def test_malformed_limits_return_json_and_service_remains_usable(self):
        server = create_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for raw in (b'1' * 5000, b'[' * 2000 + b'0' + b']' * 2000):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("POST", "/api/v2/compile-editor", raw,
                                   {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(response.read())["code"], "invalid_json")
                connection.request("GET", "/api/v1/health")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["status"], "ok")
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_rejected_requests_close_before_unread_bytes_can_be_reparsed(self):
        server = create_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host = f"127.0.0.1:{server.server_port}"
        smuggled = (
            f"GET /api/v1/health HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
        )
        requests = {
            "invalid origin": (
                f"POST /api/v2/compile HTTP/1.1\r\nHost: {host}\r\n"
                "Origin: https://attacker.invalid\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(smuggled)}\r\n\r\n"
            ).encode()
            + smuggled,
            "duplicate length": (
                f"POST /api/v2/compile HTTP/1.1\r\nHost: {host}\r\n"
                "Content-Type: application/json\r\nContent-Length: 1\r\n"
                f"Content-Length: {len(smuggled)}\r\n\r\n"
            ).encode()
            + smuggled,
            "duplicate host": (
                f"POST /api/v2/compile HTTP/1.1\r\nHost: {host}\r\n"
                f"Host: {host}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(smuggled)}\r\n\r\n"
            ).encode()
            + smuggled,
            "transfer encoding": (
                f"POST /api/v2/compile HTTP/1.1\r\nHost: {host}\r\n"
                "Content-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n"
            ).encode()
            + smuggled,
            "get body": (
                f"GET /api/v1/health HTTP/1.1\r\nHost: {host}\r\n"
                f"Content-Length: {len(smuggled)}\r\n\r\n"
            ).encode()
            + smuggled,
        }
        try:
            for label, request in requests.items():
                with self.subTest(label=label):
                    response = self._raw_request(server.server_port, request)
                    self.assertEqual(response.count(b"HTTP/1.1"), 1)
                    self.assertIn(b"HTTP/1.1 400", response)
                    self.assertIn(b"Connection: close", response)
                    self.assertNotIn(b"HTTP/1.1 200", response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
