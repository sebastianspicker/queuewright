"""Bounded loopback JSON API for validating inert Studio projects."""

from __future__ import annotations

import copy
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from queuewright_studio.catalog import load_catalog
from queuewright_studio.http_input import read_json_body
from queuewright_studio.project_endpoints import (
    PROJECT_FIELDS,
    PROJECT_ID,
    PROJECT_SCHEMA_VERSION,
    ProjectEndpoints,
)

__all__ = [
    "MAX_BODY_BYTES",
    "PROJECT_FIELDS",
    "PROJECT_ID",
    "PROJECT_SCHEMA_VERSION",
    "StudioService",
    "create_server",
    "serve",
]


HOST = "127.0.0.1"
PORT = 8765
MAX_BODY_BYTES = 2 * 1024 * 1024
JSON_CONTENT_TYPE = "application/json"
API_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"
CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "studio"
    / "catalog"
    / "features.json"
)
SENSITIVE_SETTING_NAMES = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "env",
    "password",
    "secret",
    "session",
    "token",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _normalized_key_parts(key: str) -> set[str]:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return set(re.findall(r"[a-z0-9]+", snake_case.lower()))


def _unsafe_setting(value: Any, path: str) -> tuple[str, str] | None:
    scalar = _unsafe_scalar(value, path)
    if scalar is not _UNHANDLED:
        return scalar
    if isinstance(value, str):
        if "://" in value:
            return path, "settings must not contain URLs"
        return None
    if isinstance(value, list):
        return _unsafe_sequence(value, path)
    if isinstance(value, dict):
        return _unsafe_mapping(value, path)
    return path, "settings must contain only JSON values"


_UNHANDLED = object()


def _unsafe_scalar(value: Any, path: str) -> tuple[str, str] | None | object:
    if value is None or value.__class__ in {bool, int}:
        return None
    if value.__class__ is float:
        return None if math.isfinite(value) else (path, "settings must contain finite JSON numbers")
    return _UNHANDLED


def _unsafe_sequence(values: list[Any], path: str) -> tuple[str, str] | None:
    for index, item in enumerate(values):
        failure = _unsafe_setting(item, f"{path}[{index}]")
        if failure is not None:
            return failure
    return None


def _unsafe_mapping(values: dict[Any, Any], path: str) -> tuple[str, str] | None:
    for key, item in values.items():
        if not isinstance(key, str):
            return path, "settings object keys must be strings"
        parts = _normalized_key_parts(key)
        if parts & SENSITIVE_SETTING_NAMES or {"api", "key"} <= parts or {"private", "key"} <= parts:
            return f"{path}.{key}", "sensitive setting names are forbidden"
        failure = _unsafe_setting(item, f"{path}.{key}")
        if failure is not None:
            return failure
    return None


def _silence_log_message(*_args: Any) -> None:
    return


class StudioService:
    """Request dispatcher with no mutable filesystem or outbound network actions."""

    def __init__(self, catalog_path: Path = CATALOG_PATH) -> None:
        self._catalog = load_catalog(catalog_path, _unsafe_setting)
        self._projects = ProjectEndpoints(self._catalog)

    def dispatch(
        self, method: str, path: str, body: Any = None
    ) -> tuple[int, dict[str, Any]]:
        if method == "GET":
            return self._dispatch_get(path)
        if method == "POST":
            return self._dispatch_post(path, body)
        return 404, _error("not_found", path, "resource not found")

    def _dispatch_get(self, path: str) -> tuple[int, dict[str, Any]]:
        if path == f"{API_PREFIX}/health":
            return 200, {
                "status": "ok",
                "service": "queuewright-studio",
                "offline_only": True,
            }
        if path == f"{API_PREFIX}/catalog":
            return 200, copy.deepcopy(self._catalog)
        if path.startswith(API_PREFIX):
            return 404, _error("not_found", path, "API endpoint not found")
        return 404, _error("not_found", path, "resource not found")

    def _dispatch_post(self, path: str, body: Any) -> tuple[int, dict[str, Any]]:
        handlers = {
            f"{API_PREFIX}/import-bundle": self._projects.import_bundle,
            f"{API_PREFIX}/compile-project": self._projects.compile_project,
            f"{API_V2_PREFIX}/migrate-project": self._projects.migrate_project_v2,
            f"{API_V2_PREFIX}/compile-project": self._projects.compile_project_v2,
        }
        handler = handlers.get(path)
        if handler is not None:
            return handler(body)
        return 404, _error("not_found", path, "API endpoint not found")


class _StudioHandler(BaseHTTPRequestHandler):
    server_version = "ZammadStudio/1.0"
    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        rendered = _canonical(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(rendered)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(rendered)

    def _request_is_local(self) -> tuple[bool, dict[str, str] | None]:
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        allowed_host = f"{HOST}:{self.server.server_port}"
        if host != allowed_host:
            return False, _error(
                "invalid_host",
                "Host",
                "Host must target the loopback service",
            )
        allowed_origins = {f"http://{allowed_host}", "http://127.0.0.1:5173"}
        if origin is not None and origin not in allowed_origins:
            return False, _error(
                "invalid_origin",
                "Origin",
                "Origin must be the loopback service",
            )
        return True, None

    def _body(self) -> tuple[Any | None, tuple[int, dict[str, Any]] | None]:
        return read_json_body(
            self.headers,
            self.rfile,
            JSON_CONTENT_TYPE,
            MAX_BODY_BYTES,
            _error,
        )

    def _handle(self) -> None:
        allowed, failure = self._request_is_local()
        if not allowed:
            self._respond(
                400,
                failure or _error("invalid_request", "request", "request is invalid"),
            )
            return
        if self.command not in {"GET", "POST"}:
            self._respond(
                405,
                _error(
                    "method_not_allowed", self.path, "method is not allowed"
                ),
            )
            return
        body: Any = None
        if self.command == "POST":
            body, failure = self._body()
            if failure is not None:
                self._respond(*failure)
                return
        status, payload = self.server.studio_service.dispatch(
            self.command, self.path, body
        )
        self._respond(status, payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_OPTIONS = _handle

    log_message = _silence_log_message


class StudioHTTPServer(ThreadingHTTPServer):
    studio_service: StudioService


def create_server(host: str = HOST, port: int = PORT) -> StudioHTTPServer:
    if host != HOST:
        raise ValueError("Studio service only binds to 127.0.0.1")
    server = StudioHTTPServer((host, port), _StudioHandler)
    server.studio_service = StudioService()
    return server


def serve() -> None:
    with create_server() as server:
        server.serve_forever()
