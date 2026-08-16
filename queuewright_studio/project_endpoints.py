"""Project endpoint contracts for the loopback Studio service."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from queuewright.blueprint import compile_v2_project, migrate_v1_project
from queuewright.compiler import compile_loaded_profile
from queuewright.errors import ConfigurationError
from queuewright.profile import validate_loaded_profile
from queuewright.studio_project import StudioContractError, validate_studio_state
from queuewright_studio.catalog import default_resource_ownership, enabled_features

API_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"
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


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _project_versions_match(project: dict[str, Any], loaded: dict[str, Any]) -> bool:
    target = project["target_schema_version"]
    return (
        target == loaded["profile"].get("schema_version")
        and target == loaded["manifest"].get("schema_version")
    )


class ProjectEndpoints:
    """Validate and compile inert Studio projects against one loaded catalog."""

    def __init__(self, catalog: dict[str, Any]) -> None:
        self._catalog = catalog

    def import_bundle(self, body: Any) -> tuple[int, dict[str, Any]]:
        loaded, failure = self.bundle(body, f"{API_PREFIX}/import-bundle")
        if failure is not None:
            return failure
        if loaded is None:
            return 422, _error("invalid_bundle", "bundle", "bundle is invalid")
        try:
            summary = validate_loaded_profile(loaded)
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_bundle", "bundle", str(error))
        project = self.default_project(loaded)
        return 200, {
            "project": project,
            "project_hash": _hash(project),
            "summary": summary,
        }

    def migrate_project_v2(self, body: Any) -> tuple[int, dict[str, Any]]:
        path = f"{API_V2_PREFIX}/migrate-project"
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request", path, "request body must contain exactly one project field"
            )
        project, failure = self.project(body["project"])
        if failure is not None:
            return failure
        if project is None:
            return 422, _error("invalid_project", "project", "project is invalid")
        try:
            migrated = migrate_v1_project(project)
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_project", "project", str(error))
        return 200, {"project": migrated, "project_hash": _hash(migrated)}

    def compile_project_v2(self, body: Any) -> tuple[int, dict[str, Any]]:
        path = f"{API_V2_PREFIX}/compile-project"
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request", path, "request body must contain exactly one project field"
            )
        try:
            compiled = compile_v2_project(body["project"])
        except (ConfigurationError, KeyError, TypeError) as error:
            return 422, _error("invalid_project", "project", str(error))
        return 200, {"issues": [], **compiled}

    def compile_project(self, body: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(body, dict) or set(body) != {"project"}:
            return 400, _error(
                "invalid_request",
                f"{API_PREFIX}/compile-project",
                "request body must contain exactly one project field",
            )
        project, failure = self.project(body["project"])
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
        return 200, {
            "artifact_filenames": [
                f"{profile_key}.project.json",
                f"{profile_key}.profile.json",
                f"{profile_key}.desired-state.json",
                f"{profile_key}.plan.json",
            ],
            "hashes": {
                "manifest": _hash(loaded["manifest"]),
                "plan": plan["plan_hash"],
                "profile": _hash(loaded["profile"]),
                "project": _hash(project),
            },
            "issues": [],
            "manifest": loaded["manifest"],
            "plan": plan,
            "profile": loaded["profile"],
            "project": project,
            "summary": summary,
        }

    def bundle(
        self, body: Any, path: str
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        if not isinstance(body, dict):
            return None, (400, _error("invalid_request", path, "JSON object required"))
        unknown = set(body) - {"profile", "manifest"}
        missing = {"profile", "manifest"} - set(body)
        if missing:
            return None, (
                400,
                _error("invalid_request", path, f"missing required field: {min(missing)}"),
            )
        if unknown:
            return None, (
                400,
                _error("invalid_request", path, f"unsupported field: {min(unknown)}"),
            )
        if not isinstance(body["profile"], dict):
            return None, (400, _error("invalid_request", "profile", "object required"))
        if not isinstance(body["manifest"], dict):
            return None, (400, _error("invalid_request", "manifest", "object required"))
        return {
            "profile": copy.deepcopy(body["profile"]),
            "manifest": copy.deepcopy(body["manifest"]),
        }, None

    def default_project(self, loaded: dict[str, Any]) -> dict[str, Any]:
        profile = loaded["profile"]
        manifest = loaded["manifest"]
        ownership = default_resource_ownership(profile, manifest)
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

    def project(
        self, project: Any
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        if not isinstance(project, dict):
            return None, (400, _error("invalid_project", "project", "object required"))
        failure = self.validate_metadata(project)
        if failure is not None:
            return None, failure
        loaded, failure = self._project_bundle(project)
        if failure is not None or loaded is None:
            return None, failure
        return self._validated_project(project, loaded)

    def _project_bundle(
        self, project: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        loaded, failure = self.bundle(
            {"profile": project["profile"], "manifest": project["manifest"]}, "project"
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
    def validate_metadata(project: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
        missing = PROJECT_FIELDS - set(project)
        unknown = set(project) - PROJECT_FIELDS
        if missing:
            return (
                400,
                _error(
                    "invalid_project", "project", f"missing required field: {min(missing)}"
                ),
            )
        if unknown:
            return (
                400,
                _error(
                    "invalid_project", "project", f"unsupported field: {min(unknown)}"
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
                return 400, _error("invalid_project", field, "non-empty string required")
        if PROJECT_ID.fullmatch(project["id"]) is None:
            return (
                400,
                _error("invalid_project", "id", "id must be a lowercase safe project key"),
            )
        return None
