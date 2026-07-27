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
CORE_OWNER = "core"
CUSTOM_OWNER = "custom"
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
    if value is None or type(value) in {bool, int}:
        return None
    if type(value) is float:
        if math.isfinite(value):
            return None
        return path, "settings must contain finite JSON numbers"
    if isinstance(value, str):
        if "://" in value:
            return path, "settings must not contain URLs"
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            failure = _unsafe_setting(item, f"{path}[{index}]")
            if failure is not None:
                return failure
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return path, "settings object keys must be strings"
            parts = _normalized_key_parts(key)
            if (
                parts & SENSITIVE_SETTING_NAMES
                or {"api", "key"} <= parts
                or {"private", "key"} <= parts
            ):
                return f"{path}.{key}", "sensitive setting names are forbidden"
            failure = _unsafe_setting(item, f"{path}.{key}")
            if failure is not None:
                return failure
        return None
    return path, "settings must contain only JSON values"


class StudioService:
    """Request dispatcher with no mutable filesystem or outbound network actions."""

    def __init__(self, catalog_path: Path = CATALOG_PATH) -> None:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(catalog, dict) or not isinstance(
            catalog.get("features"), list
        ):
            raise RuntimeError("Studio catalog must contain a features list")
        feature_ids = [feature.get("id") for feature in catalog["features"]]
        if (
            not all(isinstance(feature_id, str) for feature_id in feature_ids)
            or len(feature_ids) != len(set(feature_ids))
            or not all(
                type(feature.get("default_enabled")) is bool
                and type(feature.get("locked")) is bool
                and isinstance(feature.get("settings"), dict)
                for feature in catalog["features"]
            )
        ):
            raise RuntimeError("Studio catalog features are invalid")
        feature_id_set = set(feature_ids)
        dependencies_by_id: dict[str, set[str]] = {}
        for feature in catalog["features"]:
            if _unsafe_setting(feature["settings"], "catalog.settings") is not None:
                raise RuntimeError("Studio catalog feature settings are unsafe")
            dependencies = feature.get("dependencies")
            if (
                not isinstance(dependencies, list)
                or not all(isinstance(value, str) for value in dependencies)
                or len(dependencies) != len(set(dependencies))
            ):
                raise RuntimeError(
                    f"Studio catalog feature {feature['id']} dependencies are invalid"
                )
            unknown = set(dependencies) - feature_id_set
            if unknown:
                raise RuntimeError(
                    f"Studio catalog feature {feature['id']} has unknown dependency: "
                    f"{sorted(unknown)[0]}"
                )
            dependencies_by_id[feature["id"]] = set(dependencies)

        remaining = copy.deepcopy(dependencies_by_id)
        complete: set[str] = set()
        while remaining:
            ready = sorted(
                feature_id
                for feature_id, dependencies in remaining.items()
                if dependencies <= complete
            )
            if not ready:
                raise RuntimeError(
                    "Studio catalog feature dependencies contain a cycle: "
                    f"{sorted(remaining)[0]}"
                )
            for feature_id in ready:
                complete.add(feature_id)
                del remaining[feature_id]
        self._catalog = catalog

    def dispatch(
        self, method: str, path: str, body: Any = None
    ) -> tuple[int, dict[str, Any]]:
        if method == "GET" and path == f"{API_PREFIX}/health":
            return 200, {
                "status": "ok",
                "service": "queuewright-studio",
                "offline_only": True,
            }
        if method == "GET" and path == f"{API_PREFIX}/catalog":
            return 200, copy.deepcopy(self._catalog)
        if method == "POST" and path == f"{API_PREFIX}/import-bundle":
            return self._import_bundle(body)
        if method == "POST" and path == f"{API_PREFIX}/compile-project":
            return self._compile_project(body)
        if method == "POST" and path == f"{API_V2_PREFIX}/migrate-project":
            return self._migrate_project_v2(body)
        if method == "POST" and path == f"{API_V2_PREFIX}/compile-project":
            return self._compile_project_v2(body)
        if path.startswith(API_PREFIX):
            return 404, _error("not_found", path, "API endpoint not found")
        return 404, _error("not_found", path, "resource not found")

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
        resource_owners = set(ownership.values())
        enabled_features = {
            feature["id"]
            for feature in self._catalog["features"]
            if feature["locked"] or feature["id"] in resource_owners
        }
        dependencies_by_id = {
            feature["id"]: set(feature["dependencies"])
            for feature in self._catalog["features"]
        }
        while True:
            required = {
                dependency
                for feature_id in enabled_features
                for dependency in dependencies_by_id[feature_id]
            }
            expanded = enabled_features | required
            if expanded == enabled_features:
                break
            enabled_features = expanded
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
                    "enabled": feature["id"] in enabled_features,
                    "settings": copy.deepcopy(feature["settings"]),
                }
                for feature in self._catalog["features"]
            },
        }

    def _default_resource_ownership(
        self, profile: dict[str, Any], manifest: dict[str, Any]
    ) -> dict[str, str]:
        ownership: dict[str, str] = {}

        def add(collection: str, key: str, owner: str) -> None:
            ownership[f"{collection}:{key}"] = owner

        for group in manifest["groups"]:
            owner = (
                "sensitive_area_handling"
                if group.get("restricted") is True
                else CORE_OWNER
            )
            add("groups", group["key"], owner)
        for organization in manifest["organizations"]:
            add("organizations", organization["key"], CORE_OWNER)
        for role in manifest["roles"]:
            add("roles", role["key"], CORE_OWNER)
        for agent in manifest["users"]["agents"]:
            add("agents", agent["key"], "dummy_users_uat")
        for customer in manifest["users"]["customers"]:
            add("customers", customer["key"], "dummy_users_uat")

        profile_uat = profile["uat"]
        handoff = profile_uat.get("handoff_probe", {})
        job_probe = profile_uat.get("job_probe", {})
        handoff_tags = {
            handoff.get("pending_tag"),
            handoff.get("recorded_tag"),
        } - {None}
        uat_tags: set[str] = set()
        for scenario in profile_uat["scenarios"]:
            tags = set(scenario.get("expected_tags", []))
            uat_tags.update(tags)

        def action_tags(resource: dict[str, Any]) -> set[str]:
            return {
                action.partition(":")[2]
                for action in resource.get("actions", [])
                if isinstance(action, str) and action.startswith("add_tag:")
            }

        def named_for(resource: dict[str, Any], marker: str) -> bool:
            return any(
                marker in str(resource.get(field, "")).lower()
                for field in ("key", "name")
            )

        sensitive_trigger_tags = {
            tag
            for trigger in manifest["triggers"]
            if (
                named_for(trigger, "sensitive")
                or "group in S" in trigger.get("conditions", {}).get("all", [])
            )
            for tag in action_tags(trigger)
        }
        sensitive_tags = {
            tag
            for tag in manifest["tags"]
            if (
                tag in sensitive_trigger_tags
                or "sensitive" in tag.lower()
                or "restricted" in tag.lower()
            )
        }

        for tag in manifest["tags"]:
            if tag in handoff_tags:
                owner = "cross_department_handoff"
            elif tag == job_probe.get("marker_tag"):
                owner = "scheduled_reviews"
            elif tag in sensitive_tags:
                owner = "sensitive_area_handling"
            elif tag in uat_tags:
                owner = "access_matrix"
            else:
                owner = CUSTOM_OWNER
            add("tags", tag, owner)

        collection_owners = {
            "overviews": "overviews",
            "checklist_templates": "checklists",
            "jobs": "scheduled_reviews",
            "report_profiles": "report_profiles",
        }
        for collection, owner in collection_owners.items():
            for resource in manifest[collection]:
                add(collection, resource["key"], owner)

        for macro in manifest["macros"]:
            tags = action_tags(macro)
            if tags & handoff_tags or named_for(macro, "handoff"):
                owner = "cross_department_handoff"
            elif tags & sensitive_tags or named_for(macro, "sensitive"):
                owner = "sensitive_area_handling"
            else:
                owner = "macros"
            add("macros", macro["key"], owner)

        for trigger in manifest["triggers"]:
            tags = action_tags(trigger)
            if tags & handoff_tags or named_for(trigger, "handoff"):
                owner = "cross_department_handoff"
            elif (
                tags & sensitive_tags
                or named_for(trigger, "sensitive")
                or "group in S"
                in trigger.get("conditions", {}).get("all", [])
            ):
                owner = "sensitive_area_handling"
            else:
                owner = "triggers"
            add("triggers", trigger["key"], owner)

        field_owners = {
            "ticket_fields": "ticket_fields",
            "user_fields": "user_classification",
            "organization_fields": "organization_classification",
            "group_fields": "group_classification",
        }
        object_manager = manifest["object_manager"]
        for collection, owner in field_owners.items():
            for field in object_manager[collection]:
                field_name = field["name"].lower()
                if "handoff" in field_name:
                    field_owner = "cross_department_handoff"
                elif "sensitive" in field_name:
                    field_owner = "sensitive_area_handling"
                else:
                    field_owner = owner
                add("object_manager_fields", field["name"], field_owner)
        for workflow in object_manager["core_workflows"]:
            add("core_workflows", workflow["key"], CORE_OWNER)

        for scenario in profile_uat["scenarios"]:
            if (
                scenario["key"] == handoff.get("ticket_key")
                or scenario.get("kind") == "transfer"
            ):
                owner = "cross_department_handoff"
            elif scenario["key"] == job_probe.get("ticket_key"):
                owner = "scheduled_reviews"
            else:
                owner = "access_matrix"
            add("uat_scenarios", scenario["key"], owner)
        return dict(sorted(ownership.items()))

    def _project(
        self, project: Any
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        if not isinstance(project, dict):
            return None, (400, _error("invalid_project", "project", "object required"))
        missing = PROJECT_FIELDS - set(project)
        unknown = set(project) - PROJECT_FIELDS
        if missing:
            return None, (
                400,
                _error(
                    "invalid_project",
                    "project",
                    f"missing required field: {sorted(missing)[0]}",
                ),
            )
        if unknown:
            return None, (
                400,
                _error(
                    "invalid_project",
                    "project",
                    f"unsupported field: {sorted(unknown)[0]}",
                ),
            )
        if project["project_schema_version"] != PROJECT_SCHEMA_VERSION:
            return None, (
                422,
                _error(
                    "invalid_project",
                    "project_schema_version",
                    "project_schema_version must be 1.0",
                ),
            )
        for field in ("id", "name", "target_schema_version"):
            if not isinstance(project[field], str) or not project[field].strip():
                return None, (
                    400,
                    _error("invalid_project", field, "non-empty string required"),
                )
        if PROJECT_ID.fullmatch(project["id"]) is None:
            return None, (
                400,
                _error(
                    "invalid_project",
                    "id",
                    "id must be a lowercase safe project key",
                ),
            )
        loaded, failure = self._bundle(
            {"profile": project["profile"], "manifest": project["manifest"]},
            "project",
        )
        if failure is not None:
            status, error = failure
            return None, (
                status,
                _error("invalid_project", error["path"], error["message"]),
            )
        assert loaded is not None
        try:
            validate_loaded_profile(loaded)
        except (ConfigurationError, KeyError, TypeError) as error:
            return None, (
                422,
                _error("invalid_project", "project", str(error)),
            )

        try:
            ownership, feature_state = validate_studio_state(
                loaded["profile"],
                loaded["manifest"],
                project["resource_ownership"],
                project["feature_state"],
                self._catalog["features"],
            )
        except StudioContractError as error:
            return None, (
                error.status,
                _error("invalid_project", error.path, error.message),
            )
        project = {
            **project,
            "resource_ownership": ownership,
            "feature_state": feature_state,
        }

        if (
            project["target_schema_version"] != loaded["profile"].get("schema_version")
            or project["target_schema_version"]
            != loaded["manifest"].get("schema_version")
        ):
            return None, (
                422,
                _error(
                    "invalid_project",
                    "project",
                    "project metadata must match its profile and manifest",
                ),
            )
        return copy.deepcopy(project), None

    def _import_bundle(self, body: Any) -> tuple[int, dict[str, Any]]:
        loaded, failure = self._bundle(body, f"{API_PREFIX}/import-bundle")
        if failure is not None:
            return failure
        assert loaded is not None
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
        assert project is not None
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
        assert project is not None
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
        content_type = self.headers.get("Content-Type")
        if content_type != JSON_CONTENT_TYPE:
            return None, (
                415,
                _error(
                    "unsupported_media_type",
                    "Content-Type",
                    "Content-Type must be application/json",
                ),
            )
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            return None, (
                411,
                _error(
                    "length_required",
                    "Content-Length",
                    "Content-Length is required",
                ),
            )
        if length > MAX_BODY_BYTES:
            return None, (
                413,
                _error(
                    "body_too_large",
                    "body",
                    "request body exceeds 2097152 bytes",
                ),
            )
        raw = self.rfile.read(length)
        if len(raw) != length:
            return None, (
                400,
                _error(
                    "invalid_request", "body", "request body is incomplete"
                ),
            )
        try:
            return json.loads(raw.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, (
                400,
                _error(
                    "invalid_json",
                    "body",
                    "request body must be valid UTF-8 JSON",
                ),
            )

    def _handle(self) -> None:
        allowed, failure = self._request_is_local()
        if not allowed:
            assert failure is not None
            self._respond(400, failure)
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

    def log_message(self, format: str, *args: Any) -> None:
        return


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
