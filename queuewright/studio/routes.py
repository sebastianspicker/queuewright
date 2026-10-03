"""Studio API routes: request-shape checks, error envelopes, and project adapters."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from ..contracts.json import canonical_sha256
from ..contracts.safety import SafeJsonError, validate_json_depth
from ..errors import ConfigurationError
from ..projects import (
    ProjectError,
    V1Snapshot,
    compile_v1_snapshot,
    compile_v2_project,
    compiled_v1_artifacts,
    is_v1_project,
    load_capabilities,
    load_feature_catalog,
    migrate_v1_snapshot,
    new_v1_project,
    validate_bundle,
    validate_v1_project,
)
from .representation import editor_representation

API_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"
STATUS_BY_KIND = {"malformed": 400, "unprocessable": 422}
WRAPPED_PROJECT_MESSAGE = "request body must contain exactly one project field"

Response = tuple[int, dict[str, Any]]


def error_envelope(code: str, path: str, message: str) -> dict[str, str]:
    """Return the JSON error body shared by every Studio failure response."""
    return {"code": code, "path": path, "message": message}


class _Rejected(Exception):
    """Stop handling a request with one error response."""

    def __init__(self, status: int, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.response: Response = (status, error_envelope(code, path, message))


def _request_bundle(body: Any, path: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _Rejected(400, "invalid_request", path, "JSON object required")
    missing = {"profile", "manifest"} - set(body)
    unknown = set(body) - {"profile", "manifest"}
    if missing:
        raise _Rejected(400, "invalid_request", path, f"missing required field: {min(missing)}")
    if unknown:
        raise _Rejected(400, "invalid_request", path, f"unsupported field: {min(unknown)}")
    for field in ("profile", "manifest"):
        if not isinstance(body[field], dict):
            raise _Rejected(400, "invalid_request", field, "object required")
    return {"profile": copy.deepcopy(body["profile"]), "manifest": copy.deepcopy(body["manifest"])}


def _wrapped_project(body: Any, path: str) -> Any:
    if not isinstance(body, dict) or set(body) != {"project"}:
        raise _Rejected(400, "invalid_request", path, WRAPPED_PROJECT_MESSAGE)
    return body["project"]


def _v1_snapshot(project: Any) -> V1Snapshot:
    """Validate a V1 project, reporting faults with their historical V1 status and path."""
    try:
        return validate_v1_project(project)
    except ProjectError as error:
        raise _Rejected(
            STATUS_BY_KIND[error.kind], "invalid_project", error.path, error.message
        ) from error


def _project_operation(operation: Callable[[Any], dict[str, Any]], value: Any) -> dict[str, Any]:
    """Run a project operation, flattening every fault to one whole-project 422."""
    try:
        return operation(value)
    except ConfigurationError as error:
        raise _Rejected(422, "invalid_project", "project", str(error)) from error


class StudioService:
    """Request dispatcher with no mutable filesystem or outbound network actions."""

    def __init__(self) -> None:
        # Fail fast on a corrupt packaged registry instead of on the first request.
        load_feature_catalog()
        load_capabilities()
        self._routes: dict[tuple[str, str], Callable[[Any], Response]] = {
            ("GET", f"{API_PREFIX}/health"): self._health,
            ("GET", f"{API_PREFIX}/catalog"): self._catalog,
            ("POST", f"{API_PREFIX}/import-bundle"): self._import_bundle,
            ("POST", f"{API_PREFIX}/compile-project"): self._compile_v1_project,
            ("POST", f"{API_V2_PREFIX}/migrate-project"): self._migrate_project,
            ("POST", f"{API_V2_PREFIX}/compile-project"): self._compile_project,
            ("POST", f"{API_V2_PREFIX}/compile"): self._compile,
            ("POST", f"{API_V2_PREFIX}/compile-editor"): self._compile_editor,
        }

    def dispatch(self, method: str, path: str, body: Any = None) -> Response:
        if method not in {"GET", "POST"}:
            return 404, error_envelope("not_found", path, "resource not found")
        if method == "POST":
            try:
                validate_json_depth(body, "body")
            except SafeJsonError as failure:
                return 400, error_envelope("invalid_json", failure.path, failure.message)
        handler = self._routes.get((method, path))
        if handler is None:
            if method == "POST" or path.startswith(API_PREFIX):
                return 404, error_envelope("not_found", path, "API endpoint not found")
            return 404, error_envelope("not_found", path, "resource not found")
        try:
            return handler(body)
        except _Rejected as rejection:
            return rejection.response

    @staticmethod
    def _health(_body: Any) -> Response:
        return 200, {"status": "ok", "service": "queuewright-studio", "offline_only": True}

    @staticmethod
    def _catalog(_body: Any) -> Response:
        return 200, load_feature_catalog()

    @staticmethod
    def _import_bundle(body: Any) -> Response:
        loaded = _request_bundle(body, f"{API_PREFIX}/import-bundle")
        try:
            summary = validate_bundle(loaded)
        except ProjectError as error:
            raise _Rejected(422, "invalid_bundle", "bundle", str(error)) from error
        project = new_v1_project(loaded)
        return 200, {
            "project": project,
            "project_hash": canonical_sha256(project),
            "summary": summary,
        }

    @staticmethod
    def _compile_v1_project(body: Any) -> Response:
        snapshot = _v1_snapshot(_wrapped_project(body, f"{API_PREFIX}/compile-project"))
        canonical = _project_operation(compile_v1_snapshot, snapshot)
        return 200, {"issues": [], **compiled_v1_artifacts(snapshot, canonical["plan"])}

    @staticmethod
    def _migrate_project(body: Any) -> Response:
        snapshot = _v1_snapshot(_wrapped_project(body, f"{API_V2_PREFIX}/migrate-project"))
        migrated = _project_operation(migrate_v1_snapshot, snapshot)
        return 200, {"project": migrated, "project_hash": canonical_sha256(migrated)}

    def _compile_project(self, body: Any) -> Response:
        return self._compile_canonical(_wrapped_project(body, f"{API_V2_PREFIX}/compile-project"))

    def _compile(self, body: Any) -> Response:
        """Compile a raw bundle, V1 project, or V2 draft into canonical V2."""
        if isinstance(body, dict) and set(body) == {"project"}:
            return self._compile_canonical(body["project"])
        loaded = _request_bundle(body, f"{API_V2_PREFIX}/compile")
        try:
            summary = validate_bundle(loaded)
            project = new_v1_project(loaded)
        except ConfigurationError as error:
            raise _Rejected(422, "invalid_bundle", "bundle", str(error)) from error
        snapshot = V1Snapshot(project, loaded, summary)
        return 200, {"issues": [], **_project_operation(compile_v1_snapshot, snapshot)}

    def _compile_editor(self, body: Any) -> Response:
        status, compiled = self._compile(body)
        return status, editor_representation(compiled)

    @staticmethod
    def _compile_canonical(project: Any) -> Response:
        if is_v1_project(project):
            snapshot = _v1_snapshot(project)
            return 200, {"issues": [], **_project_operation(compile_v1_snapshot, snapshot)}
        return 200, {"issues": [], **_project_operation(compile_v2_project, project)}
