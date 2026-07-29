"""Operation, policy, preview, and dependency-graph models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .model_protocol import (
    ControlError,
    READ_METHODS,
    SAFE_KEY,
    WRITE_METHODS,
    _freeze,
    _hash,
    _strict_json,
)

@dataclass(frozen=True)
class Operation:
    id: str
    method: str
    path_class: str
    target: str
    body: Mapping[str, Any]
    risk: str
    precondition: str
    postcondition: str
    depends_on: tuple[str, ...] = ()
    rollback: Mapping[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_safe_operation_values({
            "id": self.id,
            "path_class": self.path_class,
            "target": self.target,
            "precondition": self.precondition,
            "postcondition": self.postcondition,
        })
        if self.method not in READ_METHODS | WRITE_METHODS | {"DELETE"}:
            raise ControlError(
                "operation_invalid", "/operations/method", "method is invalid"
            )
        _require_safe_operation_identifiers(self.depends_on, "/operations/depends_on", "dependencies must be safe operation IDs")
        _require_safe_operation_identifiers(self.required_permissions, "/operations/required_permissions", "permissions must be safe identifiers")
        rollback = _validated_rollback(self.rollback)
        object.__setattr__(self, "body", _freeze(self.body))
        object.__setattr__(self, "rollback", _freeze(rollback))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        object.__setattr__(
            self,
            "required_permissions",
            tuple(sorted(set(self.required_permissions))),
        )


def _require_safe_operation_values(values: Mapping[str, Any]) -> None:
    for name, value in values.items():
        if not isinstance(value, str) or SAFE_KEY.fullmatch(value) is None:
            raise ControlError("operation_invalid", f"/operations/{name}", f"{name} must be a safe opaque identifier")


def _require_safe_operation_identifiers(values: Sequence[str], path: str, message: str) -> None:
    if not all(SAFE_KEY.fullmatch(item) for item in values):
        raise ControlError("operation_invalid", path, message)


def _validated_rollback(value: Mapping[str, Any]) -> dict[str, Any]:
    rollback = _strict_json(value, "/operations/rollback")
    if not isinstance(rollback, dict):
        raise ControlError("operation_invalid", "/operations/rollback", "rollback must be an object")
    postcondition = rollback.get("postcondition")
    if postcondition is not None and (not isinstance(postcondition, str) or SAFE_KEY.fullmatch(postcondition) is None):
        raise ControlError("operation_invalid", "/operations/rollback/postcondition", "rollback postcondition must be a safe hash identifier")
    return rollback


@dataclass(frozen=True)
class AdapterPolicy:
    version: str
    allowed: Mapping[str, tuple[str, ...]]
    risks: frozenset[str] = frozenset({"low", "medium", "high"})
    body_fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    required_permissions: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    call_timeout_seconds: int = 30
    lease_seconds: int = 900

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or SAFE_KEY.fullmatch(self.version) is None:
            raise ControlError(
                "policy_invalid", "/policy/version", "safe policy version required"
            )
        normalized = _normalized_allowed(self.allowed)
        object.__setattr__(self, "allowed", _freeze(normalized))
        object.__setattr__(self, "risks", frozenset(self.risks))
        normalized_fields = _normalized_policy_values(self.body_fields, normalized, "/policy/body_fields", "body field policy is invalid")
        object.__setattr__(self, "body_fields", _freeze(normalized_fields))
        normalized_permissions = _normalized_policy_values(self.required_permissions, normalized, "/policy/required_permissions", "permission policy is invalid")
        _require_write_permissions(normalized, normalized_permissions)
        _require_policy_timeouts(self.call_timeout_seconds, self.lease_seconds)
        object.__setattr__(
            self, "required_permissions", _freeze(normalized_permissions)
        )


    @property
    def digest(self) -> str:
        return _hash(
            {
                "version": self.version,
                "allowed": self.allowed,
                "risks": sorted(self.risks),
                "body_fields": self.body_fields,
                "required_permissions": self.required_permissions,
                "call_timeout_seconds": self.call_timeout_seconds,
                "lease_seconds": self.lease_seconds,
            }
        )

    def validate(self, operation: Operation, permissions: Sequence[str]) -> None:
        if operation.method not in self.allowed.get(operation.path_class, ()):
            raise ControlError(
                "operation_not_allowed",
                "/operations",
                "method and path class are not adapter-approved",
            )
        if operation.risk not in self.risks:
            raise ControlError(
                "operation_not_allowed",
                "/operations",
                "risk is not adapter-approved",
            )
        if operation.method == "DELETE":
            raise ControlError(
                "operation_not_allowed",
                "/operations",
                "DELETE is unavailable to normal apply and rollback",
            )
        unknown_fields = set(operation.body) - set(
            self.body_fields.get(operation.path_class, ())
        )
        if unknown_fields:
            raise ControlError(
                "operation_not_allowed",
                "/operations/body",
                f"body field is not adapter-approved: {sorted(unknown_fields)[0]}",
            )
        required = tuple(self.required_permissions.get(operation.path_class, ()))
        if operation.required_permissions and operation.required_permissions != required:
            raise ControlError(
                "operation_not_allowed",
                "/operations/required_permissions",
                "operation permission declaration differs from adapter policy",
            )
        missing = set(required) - set(permissions)
        if missing:
            raise ControlError(
                "permission_incomplete",
                "/operations",
                f"missing required permission: {sorted(missing)[0]}",
            )


def _normalized_allowed(allowed: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    if not all(SAFE_KEY.fullmatch(path_class) for path_class in allowed):
        raise ControlError("policy_invalid", "/policy/allowed", "path class is invalid")
    return {path_class: tuple(sorted(set(methods))) for path_class, methods in allowed.items()}


def _normalized_policy_values(values: Mapping[str, tuple[str, ...]], allowed: Mapping[str, tuple[str, ...]], path: str, message: str) -> dict[str, tuple[str, ...]]:
    if any(path_class not in allowed or not all(isinstance(value, str) and SAFE_KEY.fullmatch(value) for value in names) for path_class, names in values.items()):
        raise ControlError("policy_invalid", path, message)
    return {path_class: tuple(sorted(set(names))) for path_class, names in values.items()}


def _require_write_permissions(allowed: Mapping[str, tuple[str, ...]], permissions: Mapping[str, tuple[str, ...]]) -> None:
    missing = next((path_class for path_class, methods in allowed.items() if set(methods) & WRITE_METHODS and not permissions.get(path_class)), None)
    if missing:
        raise ControlError("policy_invalid", "/policy/required_permissions", f"write path class requires policy-owned permissions: {missing}")


def _require_policy_timeouts(timeout: int, lease: int) -> None:
    if timeout.__class__ is not int or lease.__class__ is not int or timeout < 1 or lease < timeout * 3:
        raise ControlError("policy_invalid", "/policy/timeouts", "lease must be at least three times the positive call timeout")


@dataclass(frozen=True)
class Preview:
    connection_id: str
    tenant_fingerprint: str
    actor: str
    permissions: tuple[str, ...]
    baseline_hash: str
    project_hash: str
    project_id: str
    policy_version: str
    policy_hash: str
    operations: tuple[Operation, ...]
    rollback_limitations: tuple[str, ...]
    nonce: str
    expires_at: float
    hash: str


@dataclass
class OperationalFacts:
    runs: dict[str, tuple[str, str, str, str]]
    intents: dict[tuple[str, str], str]
    outcomes: dict[tuple[str, str], tuple[str, str]]
    resolutions: dict[tuple[str, str], tuple[str, str]]
    rollbacks: dict[tuple[str, str], str]


def _preview_material(preview: Preview) -> dict[str, Any]:
    return {
        "connection_id": preview.connection_id,
        "tenant_fingerprint": preview.tenant_fingerprint,
        "actor": preview.actor,
        "permissions": preview.permissions,
        "baseline_hash": preview.baseline_hash,
        "project_hash": preview.project_hash,
        "project_id": preview.project_id,
        "policy_version": preview.policy_version,
        "policy_hash": preview.policy_hash,
        "operations": preview.operations,
        "rollback_limitations": preview.rollback_limitations,
        "nonce": preview.nonce,
        "expires_at": preview.expires_at,
    }


def _preview_from_bytes(value: bytes) -> Preview:
    data = _preview_data(value)
    operations = _preview_operations(data)
    preview = Preview(**{**data, "permissions": tuple(data["permissions"]), "operations": operations, "rollback_limitations": tuple(data["rollback_limitations"])})
    _require_preview_hash(preview)
    return preview


def _preview_data(value: bytes) -> dict[str, Any]:
    try:
        data = _strict_json(json.loads(value.decode("utf-8")), "preview")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlError("preview_invalid", "/preview", "stored preview is invalid") from error
    fields = {
        "connection_id",
        "tenant_fingerprint",
        "actor",
        "permissions",
        "baseline_hash",
        "project_hash",
        "project_id",
        "policy_version",
        "policy_hash",
        "operations",
        "rollback_limitations",
        "nonce",
        "expires_at",
        "hash",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ControlError("preview_invalid", "/preview", "stored preview shape is invalid")
    return data


def _preview_operations(data: Mapping[str, Any]) -> tuple[Operation, ...]:
    operation_fields = {
        "id",
        "method",
        "path_class",
        "target",
        "body",
        "risk",
        "precondition",
        "postcondition",
        "depends_on",
        "rollback",
        "required_permissions",
    }
    operations: list[Operation] = []
    for item in data["operations"]:
        if not isinstance(item, dict) or set(item) != operation_fields:
            raise ControlError(
                "preview_invalid", "/preview/operations", "stored operation is invalid"
            )
        operations.append(
            Operation(
                **{
                    **item,
                    "depends_on": tuple(item["depends_on"]),
                    "required_permissions": tuple(item["required_permissions"]),
                }
            )
        )
    return tuple(operations)


def _require_preview_hash(preview: Preview) -> None:
    if preview.hash != _hash(_preview_material(preview)):
        raise ControlError(
            "preview_invalid", "/preview", "stored preview hash is invalid"
        )


def _topological_operations(operations: Sequence[Operation]) -> tuple[Operation, ...]:
    by_id = _operation_index(operations)
    _validate_operation_dependencies(by_id)
    remaining = {operation.id: set(operation.depends_on) for operation in by_id.values()}
    complete: set[str] = set()
    ordered: list[Operation] = []
    while remaining:
        ready = sorted(operation_id for operation_id, dependencies in remaining.items() if dependencies <= complete)
        if not ready:
            raise ControlError("operation_graph_invalid", "/operations", "operation graph has a cycle")
        for operation_id in ready:
            ordered.append(by_id[operation_id])
            complete.add(operation_id)
            del remaining[operation_id]
    return tuple(ordered)


def _operation_index(operations: Sequence[Operation]) -> dict[str, Operation]:
    by_id: dict[str, Operation] = {}
    for operation in operations:
        if operation.id in by_id:
            raise ControlError(
                "operation_graph_invalid", "/operations", "operation IDs must be unique"
            )
        by_id[operation.id] = operation
    return by_id


def _validate_operation_dependencies(by_id: Mapping[str, Operation]) -> None:
    for operation in by_id.values():
        unknown = set(operation.depends_on) - set(by_id)
        if unknown:
            raise ControlError(
                "operation_graph_invalid",
                "/operations",
                f"unknown dependency: {sorted(unknown)[0]}",
            )
        if operation.id in operation.depends_on:
            raise ControlError(
                "operation_graph_invalid", "/operations", "self dependency is forbidden"
            )
