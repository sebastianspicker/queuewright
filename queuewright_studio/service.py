"""Bounded loopback JSON API for validating inert Studio projects."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from queuewright.compiler import compile_loaded_profile
from queuewright.blueprint import compile_v2_project, migrate_v1_project
from queuewright.errors import ConfigurationError
from queuewright.profile import validate_loaded_profile
from queuewright.studio_project import (
    StudioContractError,
    validate_studio_state,
)
from queuewright_studio.catalog import default_resource_ownership, enabled_features, load_catalog
from queuewright_studio.http_input import read_json_body


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
PROJECT_SCHEMA_VERSION = "1.0"
PROJECT_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
PROJECT_FIELDS = {
    "project_schema_version",
    "id",
    "name",
    "target_schema_version",
    "profile",
    "manifest",
    "resource_ownership",
    "feature_state",
}
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


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


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


def _project_versions_match(
    project: dict[str, Any], loaded: dict[str, Any]
) -> bool:
    target = project["target_schema_version"]
    return (
        target == loaded["profile"].get("schema_version")
        and target == loaded["manifest"].get("schema_version")
    )


class StudioService:
    """Request dispatcher with no mutable filesystem or outbound network actions."""

    def __init__(self, catalog_path: Path = CATALOG_PATH) -> None:
        self._catalog = load_catalog(catalog_path, _unsafe_setting)

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
            f"{API_PREFIX}/import-bundle": self._import_bundle,
            f"{API_PREFIX}/compile-project": self._compile_project,
            f"{API_V2_PREFIX}/migrate-project": self._migrate_project_v2,
            f"{API_V2_PREFIX}/compile-project": self._compile_project_v2,
        }
        handler = handlers.get(path)
        if handler is not None:
            return handler(body)
        return 404, _error("not_found", path, "API endpoint not found")

    def _bundle(
        self, body: Any, path: str
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        if not isinstance(body, dict):
            return None, (400, _error("invalid_request", path, "JSON object required"))
        unknown = set(body) - {"profile", "manifest"}
        missing = {"profile", "manifest"} - set(body)
        if missing:
            return None, (
                400,
                _error(
                    "invalid_request",
                    path,
                    f"missing required field: {sorted(missing)[0]}",
                ),
            )
        if unknown:
            return None, (
                400,
                _error(
                    "invalid_request",
                    path,
                    f"unsupported field: {sorted(unknown)[0]}",
                ),
            )
        if not isinstance(body["profile"], dict):
            return None, (400, _error("invalid_request", "profile", "object required"))
        if not isinstance(body["manifest"], dict):
            return None, (400, _error("invalid_request", "manifest", "object required"))
        return {
            "profile": copy.deepcopy(body["profile"]),
            "manifest": copy.deepcopy(body["manifest"]),
        }, None

    def _default_project(self, loaded: dict[str, Any]) -> dict[str, Any]:
        profile = loaded["profile"]
        manifest = loaded["manifest"]
        ownership = self._default_resource_ownership(profile, manifest)
        enabled = enabled_features(self._catalog["features"], ownership)
        return {
            "project_schema_version": PROJECT_SCHEMA_VERSION,
            "id": f"{profile['profile_key']}-project",
            "name": profile["display_name"],
            "target_schema_version": profile["schema_version"],
            "profile": copy.deepcopy(profile),
            "manifest": copy.deepcopy(manifest),
            "resource_ownership": ownership,
            "feature_state": {
                feature["id"]: {
                    "enabled": feature["id"] in enabled,
                    "settings": copy.deepcopy(feature["settings"]),
                }
                for feature in self._catalog["features"]
            },
        }

    def _default_resource_ownership(
        self, profile: dict[str, Any], manifest: dict[str, Any]
    ) -> dict[str, str]:
        return default_resource_ownership(profile, manifest)

    def _project(
        self, project: Any
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        if not isinstance(project, dict):
            return None, (400, _error("invalid_project", "project", "object required"))
        failure = self._validate_project_metadata(project)
        if failure is not None:
            return None, failure
        loaded, failure = self._project_bundle(project)
        if failure is not None or loaded is None:
            return None, failure
        return self._validated_project(project, loaded)

    def _project_bundle(
        self, project: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        loaded, failure = self._bundle(
            {"profile": project["profile"], "manifest": project["manifest"]},
            "project",
        )
        if failure is not None:
            status, error = failure
            return None, (status, _error("invalid_project", error["path"], error["message"]))
        if loaded is None:
            return None, (422, _error("invalid_project", "project", "bundle is invalid"))
        try:
            validate_loaded_profile(loaded)
        except (ConfigurationError, KeyError, TypeError) as error:
            return None, (422, _error("invalid_project", "project", str(error)))
        return loaded, None

    def _validated_project(
        self, project: dict[str, Any], loaded: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        try:
            ownership, feature_state = validate_studio_state(
                loaded["profile"],
                loaded["manifest"],
                project["resource_ownership"],
                project["feature_state"],
                self._catalog["features"],
            )
        except StudioContractError as error:
            return None, (error.status, _error("invalid_project", error.path, error.message))
        validated = {**project, "resource_ownership": ownership, "feature_state": feature_state}
        if not _project_versions_match(validated, loaded):
            return None, (
                422,
                _error(
                    "invalid_project",
                    "project",
                    "project metadata must match its profile and manifest",
                ),
            )
        return copy.deepcopy(validated), None
    @staticmethod
    def _validate_project_metadata(
        project: dict[str, Any]
    ) -> tuple[int, dict[str, Any]] | None:
        missing = PROJECT_FIELDS - set(project)
        unknown = set(project) - PROJECT_FIELDS
        if missing:
            return (
                400,
                _error(
                    "invalid_project",
                    "project",
                    f"missing required field: {sorted(missing)[0]}",
                ),
            )
        if unknown:
            return (
                400,
                _error(
                    "invalid_project",
                    "project",
                    f"unsupported field: {sorted(unknown)[0]}",
                ),
            )
        if project["project_schema_version"] != PROJECT_SCHEMA_VERSION:
            return (
                422,
                _error(
                    "invalid_project",
                    "project_schema_version",
                    "project_schema_version must be 1.0",
                ),
            )
        for field in ("id", "name", "target_schema_version"):
            if not isinstance(project[field], str) or not project[field].strip():
                return (
                    400,
                    _error("invalid_project", field, "non-empty string required"),
                )
        if PROJECT_ID.fullmatch(project["id"]) is None:
            return (
                400,
                _error(
                    "invalid_project",
                    "id",
                    "id must be a lowercase safe project key",
                ),
            )
        return None

    def _import_bundle(self, body: Any) -> tuple[int, dict[str, Any]]:
        loaded, failure = self._bundle(body, f"{API_PREFIX}/import-bundle")
        if failure is not None:
            return failure
        if loaded is None:
            return 422, _error("invalid_bundle", "bundle", "bundle is invalid")
        try:
            summary = validate_loaded_profile(loaded)
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_bundle", "bundle", str(error))
        project = self._default_project(loaded)
        return 200, {
            "project": project,
            "project_hash": _hash(project),
            "summary": summary,
        }

    def _migrate_project_v2(self, body: Any) -> tuple[int, dict[str, Any]]:
        path = f"{API_V2_PREFIX}/migrate-project"
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request", path,
                "request body must contain exactly one project field",
            )
        project, failure = self._project(body["project"])
        if failure is not None:
            return failure
        if project is None:
            return 422, _error("invalid_project", "project", "project is invalid")
        try:
            migrated = migrate_v1_project(project)
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_project", "project", str(error))
        return 200, {"project": migrated, "project_hash": _hash(migrated)}

    def _compile_project_v2(self, body: Any) -> tuple[int, dict[str, Any]]:
        path = f"{API_V2_PREFIX}/compile-project"
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request", path,
                "request body must contain exactly one project field",
            )
        try:
            compiled = compile_v2_project(body["project"])
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_project", "project", str(error))
        return 200, {"issues": [], **compiled}

    def _compile_project(self, body: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request",
                f"{API_PREFIX}/compile-project",
                "request body must contain exactly one project field",
            )
        candidate = body["project"]
        project, failure = self._project(candidate)
        if failure is not None:
            return failure
        if project is None:
            return 422, _error("invalid_project", "project", "project is invalid")
        loaded = {"profile": project["profile"], "manifest": project["manifest"]}
        try:
            plan = compile_loaded_profile(loaded)
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_project", "project", str(error))
        summary = validate_loaded_profile(loaded)
        profile_key = loaded["profile"]["profile_key"]
        profile_hash = _hash(loaded["profile"])
        manifest_hash = _hash(loaded["manifest"])
        return 200, {
            "artifact_filenames": [
                f"{profile_key}.project.json",
                f"{profile_key}.profile.json",
                f"{profile_key}.desired-state.json",
                f"{profile_key}.plan.json",
            ],
            "hashes": {
                "manifest": manifest_hash,
                "plan": plan["plan_hash"],
                "profile": profile_hash,
                "project": _hash(project),
            },
            "issues": [],
            "manifest": loaded["manifest"],
            "plan": plan,
            "profile": loaded["profile"],
            "project": project,
            "summary": summary,
        }


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
