"""Fail-closed, transport-injected primitives for a future connected mode.

This module deliberately contains no HTTP client.  It owns approval, ordering,
durable evidence, and local-session invariants; a versioned adapter must supply
all tenant I/O and resource-specific schemas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import stat
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

try:  # Importability is optional; constructing a ledger still fails closed.
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - unsupported installation only
    AESGCM = None  # type: ignore[assignment,misc]


SAFE_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,199}$")
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SENSITIVE_PARTS = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secret",
    "session",
    "token",
}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_METHODS = {"POST", "PUT", "PATCH"}
RESERVED_AUDIT_KINDS = {
    "intent",
    "operation_applied",
    "operation_not_applied",
    "operation_rolled_back",
    "rollback_intent",
    "state",
}


class ControlError(Exception):
    def __init__(
        self,
        code: str,
        path: str,
        message: str,
        run_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message
        self.run_id = run_id

    def public(self) -> dict[str, str]:
        result = {"code": self.code, "path": self.path, "message": self.message}
        if self.run_id:
            result["run_id"] = self.run_id
        return result


def _key_parts(key: str) -> set[str]:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return set(re.findall(r"[a-z0-9]+", snake_case.lower()))


def _strict_json(value: Any, path: str = "value") -> Any:
    """Return plain JSON values or reject non-deterministic/custom objects."""
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if value == value and value not in (float("inf"), -float("inf")):
            return value
        raise ControlError("invalid_json", path, "finite JSON number required")
    if isinstance(value, (list, tuple)):
        return [_strict_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ControlError("invalid_json", path, "JSON object keys must be strings")
            parts = _key_parts(key)
            if (
                parts & SENSITIVE_PARTS
                or {"api", "key"} <= parts
                or {"private", "key"} <= parts
            ):
                raise ControlError(
                    "sensitive_input",
                    f"{path}.{key}",
                    "credential-shaped fields are forbidden",
                )
            result[key] = _strict_json(item, f"{path}.{key}")
        return result
    raise ControlError("invalid_json", path, "only JSON values are accepted")


def _freeze(value: Any) -> Any:
    plain = _strict_json(value)
    if isinstance(plain, dict):
        return MappingProxyType({key: _freeze(item) for key, item in plain.items()})
    if isinstance(plain, list):
        return tuple(_freeze(item) for item in plain)
    return plain


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _plain(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    return _strict_json(value)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _canonical_origin(value: str) -> tuple[str, str]:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ControlError(
            "invalid_origin", "/connection/origin", "origin port or host is invalid"
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ControlError(
            "invalid_origin",
            "/connection/origin",
            "an explicit credential-free HTTPS origin is required",
        )
    if port == 0:
        raise ControlError(
            "invalid_origin", "/connection/origin", "origin port is invalid"
        )
    host = _canonical_host(parsed.hostname)
    rendered_host = f"[{host}]" if ":" in host else host
    origin = f"https://{rendered_host}{f':{port}' if port else ''}"
    return origin, host


def _canonical_host(value: str) -> str:
    host = value.lower().rstrip(".")
    if not host:
        raise ControlError(
            "invalid_origin", "/connection/origin", "origin host is invalid"
        )
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise ControlError(
                "invalid_origin", "/connection/origin", "origin host is invalid"
            ) from error
        labels = host.split(".")
        if (
            len(host) > 253
            or any(HOST_LABEL.fullmatch(label) is None for label in labels)
            or (len(labels) == 4 and all(label.isdigit() for label in labels))
        ):
            raise ControlError(
                "invalid_origin", "/connection/origin", "origin host is invalid"
            )
        return host


def _validate_addresses(
    host: str,
    addresses: Any,
    allow_private: bool,
) -> tuple[str, ...]:
    if not isinstance(addresses, list) or not addresses:
        raise ControlError(
            "identity_invalid",
            "/connection/resolved_addresses",
            "adapter must provide the pinned resolved address set",
        )
    normalized: list[str] = []
    for value in addresses:
        if not isinstance(value, str):
            raise ControlError(
                "identity_invalid",
                "/connection/resolved_addresses",
                "resolved addresses must be IP strings",
            )
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ControlError(
                "identity_invalid",
                "/connection/resolved_addresses",
                "resolved address is invalid",
            ) from error
        if not allow_private and not address.is_global:
            raise ControlError(
                "origin_forbidden",
                "/connection/origin",
                "private, loopback, link-local, and reserved origins require an explicit on-prem policy",
            )
        normalized.append(address.compressed)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and literal.compressed not in normalized:
        raise ControlError(
            "identity_invalid",
            "/connection/resolved_addresses",
            "literal origin and pinned address do not match",
        )
    return tuple(sorted(set(normalized)))


class MasterKeyProvider(Protocol):
    def get_key(self) -> bytes: ...

    def get_audit_anchor(self) -> tuple[int, str] | None: ...

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool: ...


class InMemoryKeyProvider:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or secrets.token_bytes(32)
        self._audit_anchor: tuple[int, str] | None = None

    def get_key(self) -> bytes:
        return self._key

    def get_audit_anchor(self) -> tuple[int, str] | None:
        return self._audit_anchor

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool:
        if self._audit_anchor != expected:
            return False
        self._audit_anchor = replacement
        return True


class MacOSKeychainProvider:
    """Fail-closed seam; the host application must provide a platform binding."""

    def get_key(self) -> bytes:
        raise ControlError(
            "key_unavailable",
            "/ledger/key",
            "macOS Keychain provider is unavailable",
        )

    def get_audit_anchor(self) -> tuple[int, str] | None:
        raise ControlError(
            "key_unavailable",
            "/ledger/audit-anchor",
            "macOS Keychain provider is unavailable",
        )

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool:
        raise ControlError(
            "key_unavailable",
            "/ledger/audit-anchor",
            "macOS Keychain provider is unavailable",
        )


class EphemeralCredential:
    """A redacted, expiring in-memory credential handle for adapter use only."""

    def __init__(self, token: str, expires_at: float) -> None:
        if (
            not isinstance(token, str)
            or not token
            or any(character.isspace() for character in token)
        ):
            raise ControlError(
                "credential_invalid", "/connection/credential", "credential is required"
            )
        if expires_at <= time.time():
            raise ControlError(
                "credential_expired", "/connection/credential", "credential has expired"
            )
        self._value = bytearray(token.encode("utf-8"))
        self.expires_at = expires_at
        self.closed = False

    def reveal(self) -> str:
        if self.closed or time.time() >= self.expires_at:
            raise ControlError(
                "credential_expired", "/connection/credential", "credential has expired"
            )
        return self._value.decode("utf-8")

    def close(self) -> None:
        for index in range(len(self._value)):
            self._value[index] = 0
        self.closed = True

    def __repr__(self) -> str:
        return "<EphemeralCredential redacted>"


@dataclass(frozen=True)
class Connection:
    id: str
    origin: str
    tenant_fingerprint: str
    actor: str
    permissions: tuple[str, ...]
    version: str
    pinned_addresses: tuple[str, ...]
    allow_private_origin: bool


@dataclass(frozen=True)
class Capability:
    support: str
    delivery: str
    complete: bool
    items: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.support not in {
            "supported",
            "permission_blocked",
            "plan_unsupported",
            "version_unsupported",
            "unknown",
        }:
            raise ValueError("invalid support status")
        if self.delivery not in {
            "automated",
            "guided_manual",
            "verify_only",
            "unsupported",
        }:
            raise ValueError("invalid delivery status")
        object.__setattr__(
            self,
            "items",
            tuple(_freeze(dict(item)) for item in self.items),
        )


class CapabilityDiscovery:
    """Bounded pagination where ambiguity never becomes absence."""

    @staticmethod
    def pages(
        fetch: Callable[[int], tuple[int, Sequence[Mapping[str, Any]]]],
        *,
        max_pages: int = 100,
        page_size: int = 100,
    ) -> Capability:
        seen: set[str] = set()
        items: list[Mapping[str, Any]] = []
        for page in range(1, max_pages + 1):
            status, batch = fetch(page)
            try:
                normalized = tuple(
                    _strict_json(dict(item), f"page[{page}]") for item in batch
                )
            except (TypeError, ValueError, ControlError):
                return Capability("unknown", "unsupported", False, tuple(items))
            signature = _hash(normalized)
            if status == 403:
                return Capability(
                    "permission_blocked", "unsupported", False, tuple(items)
                )
            if status == 404 or not 200 <= status < 300:
                return Capability("unknown", "unsupported", False, tuple(items))
            if signature in seen:
                return Capability("supported", "verify_only", False, tuple(items))
            seen.add(signature)
            if not normalized:
                return Capability("supported", "automated", True, tuple(items))
            items.extend(normalized)
            if len(normalized) < page_size:
                return Capability("supported", "automated", True, tuple(items))
        return Capability("supported", "verify_only", False, tuple(items))


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
        for name, value in {
            "id": self.id,
            "path_class": self.path_class,
            "target": self.target,
            "precondition": self.precondition,
            "postcondition": self.postcondition,
        }.items():
            if not isinstance(value, str) or SAFE_KEY.fullmatch(value) is None:
                raise ControlError(
                    "operation_invalid",
                    f"/operations/{name}",
                    f"{name} must be a safe opaque identifier",
                )
        if self.method not in READ_METHODS | WRITE_METHODS | {"DELETE"}:
            raise ControlError(
                "operation_invalid", "/operations/method", "method is invalid"
            )
        if not all(SAFE_KEY.fullmatch(item) for item in self.depends_on):
            raise ControlError(
                "operation_invalid",
                "/operations/depends_on",
                "dependencies must be safe operation IDs",
            )
        if not all(SAFE_KEY.fullmatch(item) for item in self.required_permissions):
            raise ControlError(
                "operation_invalid",
                "/operations/required_permissions",
                "permissions must be safe identifiers",
            )
        rollback = _strict_json(self.rollback, "/operations/rollback")
        if not isinstance(rollback, dict):
            raise ControlError(
                "operation_invalid", "/operations/rollback", "rollback must be an object"
            )
        postcondition = rollback.get("postcondition")
        if postcondition is not None and (
            not isinstance(postcondition, str)
            or SAFE_KEY.fullmatch(postcondition) is None
        ):
            raise ControlError(
                "operation_invalid",
                "/operations/rollback/postcondition",
                "rollback postcondition must be a safe hash identifier",
            )
        object.__setattr__(self, "body", _freeze(self.body))
        object.__setattr__(self, "rollback", _freeze(rollback))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        object.__setattr__(
            self,
            "required_permissions",
            tuple(sorted(set(self.required_permissions))),
        )


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
        normalized: dict[str, tuple[str, ...]] = {}
        for path_class, methods in self.allowed.items():
            if SAFE_KEY.fullmatch(path_class) is None:
                raise ControlError(
                    "policy_invalid", "/policy/allowed", "path class is invalid"
                )
            normalized[path_class] = tuple(sorted(set(methods)))
        object.__setattr__(self, "allowed", _freeze(normalized))
        object.__setattr__(self, "risks", frozenset(self.risks))
        normalized_fields: dict[str, tuple[str, ...]] = {}
        for path_class, names in self.body_fields.items():
            if path_class not in normalized or not all(
                isinstance(name, str) and SAFE_KEY.fullmatch(name) for name in names
            ):
                raise ControlError(
                    "policy_invalid", "/policy/body_fields", "body field policy is invalid"
                )
            normalized_fields[path_class] = tuple(sorted(set(names)))
        object.__setattr__(self, "body_fields", _freeze(normalized_fields))
        normalized_permissions: dict[str, tuple[str, ...]] = {}
        for path_class, permissions in self.required_permissions.items():
            if path_class not in normalized or not all(
                isinstance(permission, str) and SAFE_KEY.fullmatch(permission)
                for permission in permissions
            ):
                raise ControlError(
                    "policy_invalid",
                    "/policy/required_permissions",
                    "permission policy is invalid",
                )
            normalized_permissions[path_class] = tuple(sorted(set(permissions)))
        for path_class, methods in normalized.items():
            if set(methods) & WRITE_METHODS and not normalized_permissions.get(path_class):
                raise ControlError(
                    "policy_invalid",
                    "/policy/required_permissions",
                    f"write path class requires policy-owned permissions: {path_class}",
                )
        if (
            type(self.call_timeout_seconds) is not int
            or type(self.lease_seconds) is not int
            or self.call_timeout_seconds < 1
            or self.lease_seconds < self.call_timeout_seconds * 3
        ):
            raise ControlError(
                "policy_invalid",
                "/policy/timeouts",
                "lease must be at least three times the positive call timeout",
            )
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
    try:
        data = _strict_json(json.loads(value.decode("utf-8")), "preview")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlError(
            "preview_invalid", "/preview", "stored preview is invalid"
        ) from error
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
        raise ControlError(
            "preview_invalid", "/preview", "stored preview shape is invalid"
        )
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
    preview = Preview(
        **{
            **data,
            "permissions": tuple(data["permissions"]),
            "operations": tuple(operations),
            "rollback_limitations": tuple(data["rollback_limitations"]),
        }
    )
    if preview.hash != _hash(_preview_material(preview)):
        raise ControlError(
            "preview_invalid", "/preview", "stored preview hash is invalid"
        )
    return preview


def _topological_operations(operations: Sequence[Operation]) -> tuple[Operation, ...]:
    by_id: dict[str, Operation] = {}
    for operation in operations:
        if operation.id in by_id:
            raise ControlError(
                "operation_graph_invalid", "/operations", "operation IDs must be unique"
            )
        by_id[operation.id] = operation
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
    remaining = {
        operation.id: set(operation.depends_on) for operation in by_id.values()
    }
    complete: set[str] = set()
    ordered: list[Operation] = []
    while remaining:
        ready = sorted(
            operation_id
            for operation_id, dependencies in remaining.items()
            if dependencies <= complete
        )
        if not ready:
            raise ControlError(
                "operation_graph_invalid", "/operations", "operation graph has a cycle"
            )
        for operation_id in ready:
            ordered.append(by_id[operation_id])
            complete.add(operation_id)
            del remaining[operation_id]
    return tuple(ordered)


class Ledger:
    """Owner-private SQLite ledger with encrypted blobs and a keyed audit chain."""

    def __init__(self, path: str | Path, key_provider: MasterKeyProvider) -> None:
        if AESGCM is None:
            raise ControlError(
                "encryption_unavailable", "/ledger", "AES-GCM support is unavailable"
            )
        self.path = str(path)
        self._key_provider = key_provider
        self._key = key_provider.get_key()
        if len(self._key) not in (16, 24, 32):
            raise ControlError(
                "invalid_key", "/ledger/key", "AES-GCM key must be 128, 192, or 256 bits"
            )
        self._audit_key = hashlib.sha256(self._key + b"queuewright-control-audit").digest()
        self._prepare_path(Path(self.path))
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                preview_hash TEXT NOT NULL,
                tenant_fingerprint TEXT NOT NULL,
                project_id TEXT NOT NULL,
                updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intents (
                run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                operation_hash TEXT NOT NULL,
                created REAL NOT NULL,
                PRIMARY KEY(run_id, operation_id),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                postimage_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                created REAL NOT NULL,
                PRIMARY KEY(run_id, operation_id),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                sequence INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                metadata TEXT NOT NULL,
                previous_mac TEXT NOT NULL,
                entry_mac TEXT NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blobs (
                name TEXT PRIMARY KEY,
                ciphertext BLOB NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS locks (
                project TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                preview_hash TEXT NOT NULL,
                fence TEXT NOT NULL,
                expires REAL NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rollback_intents (
                run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                expected_hash TEXT NOT NULL,
                created REAL NOT NULL,
                PRIMARY KEY(run_id, operation_id),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS intent_resolutions (
                run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                resolution TEXT NOT NULL,
                proven_hash TEXT NOT NULL,
                created REAL NOT NULL,
                PRIMARY KEY(run_id, operation_id),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            """
        )
        if self.path != ":memory:":
            os.chmod(self.path, 0o600)
        self._synchronize_anchor()
        self._verify_operational_integrity()

    @staticmethod
    def _prepare_path(path: Path) -> None:
        if str(path) == ":memory:":
            return
        parent = path.parent
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ControlError("ledger_unsafe", "/ledger", "ledger parent is unsafe")
        parent_details = parent.stat()
        if (
            parent_details.st_uid != os.geteuid()
            or stat.S_IMODE(parent_details.st_mode) & 0o022
        ):
            raise ControlError(
                "ledger_unsafe",
                "/ledger",
                "ledger parent must be owner-controlled and not writable by group or others",
            )
        if path.exists() or path.is_symlink():
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                raise ControlError(
                    "ledger_unsafe", "/ledger", "ledger must be a regular file"
                )
            os.chmod(path, 0o600)
            return
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)

    def close(self) -> None:
        self.db.close()

    def _begin(self) -> None:
        self._synchronize_anchor()
        self._verify_operational_integrity()
        self.db.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self.db.execute("COMMIT")
        self._synchronize_anchor()
        self._verify_operational_integrity()

    def _rollback(self) -> None:
        if self.db.in_transaction:
            self.db.execute("ROLLBACK")

    def _audit_locked(
        self,
        run_id: str,
        kind: str,
        metadata: Mapping[str, Any],
        created: float | None = None,
    ) -> None:
        safe = _strict_json(metadata, "audit.metadata")
        last = self.db.execute(
            "SELECT sequence, entry_mac FROM audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = (last[0] + 1) if last else 1
        previous = last[1] if last else "0" * 64
        timestamp = created if created is not None else time.time()
        material = {
            "sequence": sequence,
            "run_id": run_id,
            "kind": kind,
            "metadata": safe,
            "previous_mac": previous,
            "created": timestamp,
        }
        entry = hmac.new(
            self._audit_key, _canonical_bytes(material), hashlib.sha256
        ).hexdigest()
        self.db.execute(
            "INSERT INTO audit VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                run_id,
                kind,
                json.dumps(safe, sort_keys=True, separators=(",", ":")),
                previous,
                entry,
                timestamp,
            ),
        )

    def audit(self, run_id: str, kind: str, metadata: Mapping[str, Any]) -> None:
        if kind in RESERVED_AUDIT_KINDS:
            raise ControlError(
                "audit_invalid",
                "/ledger/audit",
                "reserved operational audit kinds are internal only",
            )
        self._begin()
        try:
            self._audit_locked(run_id, kind, metadata)
            self._commit()
        except Exception:
            self._rollback()
            raise

    def _audit_chain(self) -> tuple[tuple[int, str] | None, dict[int, str]]:
        previous = "0" * 64
        expected_sequence = 1
        entries: dict[int, str] = {}
        for sequence, run_id, kind, metadata, prior, entry, created in self.db.execute(
            "SELECT sequence,run_id,kind,metadata,previous_mac,entry_mac,created "
            "FROM audit ORDER BY sequence"
        ):
            material = {
                "sequence": sequence,
                "run_id": run_id,
                "kind": kind,
                "metadata": json.loads(metadata),
                "previous_mac": prior,
                "created": created,
            }
            expected = hmac.new(
                self._audit_key, _canonical_bytes(material), hashlib.sha256
            ).hexdigest()
            if (
                sequence != expected_sequence
                or prior != previous
                or not hmac.compare_digest(entry, expected)
            ):
                raise ControlError(
                    "audit_invalid",
                    "/ledger/audit",
                    "audit chain authentication failed",
                )
            entries[int(sequence)] = str(entry)
            previous = entry
            expected_sequence += 1
        if not entries:
            return None, entries
        head_sequence = expected_sequence - 1
        return (head_sequence, entries[head_sequence]), entries

    def verify_audit_chain(self) -> bool:
        try:
            head, _ = self._audit_chain()
        except (ControlError, json.JSONDecodeError, TypeError, ValueError):
            return False
        anchor = self._key_provider.get_audit_anchor()
        return anchor == head

    def _synchronize_anchor(self) -> None:
        """Authenticate the chain and recover a committed extension via CAS."""
        head, entries = self._audit_chain()
        anchor = self._key_provider.get_audit_anchor()
        if head is None:
            if anchor is None:
                return
            raise ControlError(
                "audit_anchor_mismatch",
                "/ledger/audit",
                "protected audit anchor has no matching ledger chain",
            )
        if anchor == head:
            return
        if anchor is not None:
            sequence, entry_mac = anchor
            if sequence not in entries or not hmac.compare_digest(
                entries[sequence], entry_mac
            ):
                raise ControlError(
                    "audit_anchor_mismatch",
                    "/ledger/audit",
                    "ledger is not an authenticated extension of the protected anchor",
                )
        if not self._key_provider.compare_and_set_audit_anchor(anchor, head):
            if self._key_provider.get_audit_anchor() == head:
                return
            raise ControlError(
                "audit_anchor_update_failed",
                "/ledger/audit-anchor",
                "protected audit anchor could not be advanced",
            )

    def _verify_operational_integrity(self) -> None:
        """Cross-check every recovery-authorizing row against anchored audit facts."""
        if not self.verify_audit_chain():
            raise ControlError(
                "ledger_integrity",
                "/ledger/audit",
                "audit chain or protected head is invalid",
            )
        expected_runs: dict[str, tuple[str, str, str, str]] = {}
        expected_intents: dict[tuple[str, str], str] = {}
        expected_outcomes: dict[tuple[str, str], tuple[str, str]] = {}
        expected_resolutions: dict[tuple[str, str], tuple[str, str]] = {}
        expected_rollbacks: dict[tuple[str, str], str] = {}
        try:
            audit_rows = self.db.execute(
                "SELECT run_id,kind,metadata FROM audit ORDER BY sequence"
            )
            for run_id, kind, encoded in audit_rows:
                metadata = json.loads(encoded)
                if kind == "state":
                    required = {
                        "state",
                        "preview_hash",
                        "tenant_fingerprint",
                        "project_id",
                    }
                    if not isinstance(metadata, dict) or set(metadata) != required:
                        raise ValueError("state audit shape")
                    expected_runs[str(run_id)] = (
                        str(metadata["state"]),
                        str(metadata["preview_hash"]),
                        str(metadata["tenant_fingerprint"]),
                        str(metadata["project_id"]),
                    )
                elif kind == "intent":
                    if not isinstance(metadata, dict) or set(metadata) != {
                        "operation_id",
                        "operation_hash",
                    }:
                        raise ValueError("intent audit shape")
                    expected_intents[(str(run_id), str(metadata["operation_id"]))] = str(
                        metadata["operation_hash"]
                    )
                elif kind == "operation_applied":
                    if not isinstance(metadata, dict) or set(metadata) != {
                        "operation_id",
                        "postimage_hash",
                    }:
                        raise ValueError("outcome audit shape")
                    expected_outcomes[(str(run_id), str(metadata["operation_id"]))] = (
                        str(metadata["postimage_hash"]),
                        "applied",
                    )
                elif kind == "operation_rolled_back":
                    if not isinstance(metadata, dict) or set(metadata) != {
                        "operation_id"
                    }:
                        raise ValueError("rolled-back audit shape")
                    key = (str(run_id), str(metadata["operation_id"]))
                    previous = expected_outcomes.get(key)
                    if previous is None:
                        raise ValueError("rollback without applied outcome")
                    expected_outcomes[key] = (previous[0], "rolled_back")
                elif kind == "operation_not_applied":
                    if not isinstance(metadata, dict) or set(metadata) != {
                        "operation_id",
                        "proven_hash",
                    }:
                        raise ValueError("resolution audit shape")
                    expected_resolutions[
                        (str(run_id), str(metadata["operation_id"]))
                    ] = ("not_applied", str(metadata["proven_hash"]))
                elif kind == "rollback_intent":
                    if not isinstance(metadata, dict) or set(metadata) != {
                        "operation_id",
                        "expected_hash",
                    }:
                        raise ValueError("rollback intent audit shape")
                    expected_rollbacks[
                        (str(run_id), str(metadata["operation_id"]))
                    ] = str(metadata["expected_hash"])

            actual_runs = {
                str(run_id): (str(state), str(preview), str(tenant), str(project))
                for run_id, state, preview, tenant, project in self.db.execute(
                    "SELECT run_id,state,preview_hash,tenant_fingerprint,project_id FROM runs"
                )
            }
            actual_intents = {
                (str(run_id), str(operation_id)): str(operation_hash)
                for run_id, operation_id, operation_hash in self.db.execute(
                    "SELECT run_id,operation_id,operation_hash FROM intents"
                )
            }
            actual_outcomes = {
                (str(run_id), str(operation_id)): (str(postimage), str(state))
                for run_id, operation_id, postimage, state in self.db.execute(
                    "SELECT run_id,operation_id,postimage_hash,state FROM outcomes"
                )
            }
            actual_resolutions = {
                (str(run_id), str(operation_id)): (str(resolution), str(proven_hash))
                for run_id, operation_id, resolution, proven_hash in self.db.execute(
                    "SELECT run_id,operation_id,resolution,proven_hash "
                    "FROM intent_resolutions"
                )
            }
            actual_rollbacks = {
                (str(run_id), str(operation_id)): str(expected_hash)
                for run_id, operation_id, expected_hash in self.db.execute(
                    "SELECT run_id,operation_id,expected_hash FROM rollback_intents"
                )
            }
        except (json.JSONDecodeError, TypeError, ValueError, sqlite3.DatabaseError) as error:
            raise ControlError(
                "ledger_integrity",
                "/ledger",
                "operational ledger evidence is malformed",
            ) from error
        if (
            actual_runs != expected_runs
            or actual_intents != expected_intents
            or actual_outcomes != expected_outcomes
            or actual_resolutions != expected_resolutions
            or actual_rollbacks != expected_rollbacks
        ):
            raise ControlError(
                "ledger_integrity",
                "/ledger",
                "operational rows do not match the authenticated audit record",
            )

    def begin_run(
        self,
        run_id: str,
        preview_hash: str,
        tenant_fingerprint: str,
        project_id: str,
    ) -> None:
        self._begin()
        try:
            self.db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    "applying",
                    preview_hash,
                    tenant_fingerprint,
                    project_id,
                    time.time(),
                ),
            )
            self._audit_locked(
                run_id,
                "state",
                {
                    "state": "applying",
                    "preview_hash": preview_hash,
                    "tenant_fingerprint": tenant_fingerprint,
                    "project_id": project_id,
                },
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "run_exists", "/runs", "run ID has already been used", run_id
            ) from error
        except Exception:
            self._rollback()
            raise

    def set_state(self, run_id: str, state: str) -> None:
        self._begin()
        try:
            run = self.db.execute(
                "SELECT preview_hash,tenant_fingerprint,project_id FROM runs "
                "WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ControlError("run_missing", "/runs", "run does not exist", run_id)
            result = self.db.execute(
                "UPDATE runs SET state=?, updated=? WHERE run_id=?",
                (state, time.time(), run_id),
            )
            if result.rowcount != 1:
                raise ControlError("run_missing", "/runs", "run does not exist", run_id)
            self._audit_locked(
                run_id,
                "state",
                {
                    "state": state,
                    "preview_hash": run[0],
                    "tenant_fingerprint": run[1],
                    "project_id": run[2],
                },
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def run(self, run_id: str) -> dict[str, Any] | None:
        self._verify_operational_integrity()
        row = self.db.execute(
            "SELECT state,preview_hash,tenant_fingerprint,project_id,updated "
            "FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "state": row[0],
            "preview_hash": row[1],
            "tenant_fingerprint": row[2],
            "project_id": row[3],
            "updated": row[4],
        }

    def state(self, run_id: str) -> str | None:
        run = self.run(run_id)
        return str(run["state"]) if run else None

    def intent(self, run_id: str, operation: Operation) -> None:
        self._begin()
        try:
            operation_hash = _hash(operation)
            self.db.execute(
                "INSERT INTO intents VALUES (?, ?, ?, ?)",
                (run_id, operation.id, operation_hash, time.time()),
            )
            self._audit_locked(
                run_id,
                "intent",
                {
                    "operation_id": operation.id,
                    "operation_hash": operation_hash,
                },
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "intent_exists",
                "/apply",
                "operation intent already exists",
                run_id,
            ) from error
        except Exception:
            self._rollback()
            raise

    def outcome(self, run_id: str, operation_id: str, postimage_hash: str) -> None:
        self._begin()
        try:
            self.db.execute(
                "INSERT INTO outcomes VALUES (?, ?, ?, ?, ?)",
                (run_id, operation_id, postimage_hash, "applied", time.time()),
            )
            self._audit_locked(
                run_id,
                "operation_applied",
                {"operation_id": operation_id, "postimage_hash": postimage_hash},
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def outcomes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: postimage_hash
            for operation_id, postimage_hash in self.db.execute(
                "SELECT operation_id,postimage_hash FROM outcomes "
                "WHERE run_id=? AND state='applied'",
                (run_id,),
            )
        }

    def intent_hashes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: operation_hash
            for operation_id, operation_hash in self.db.execute(
                "SELECT operation_id,operation_hash FROM intents WHERE run_id=?",
                (run_id,),
            )
        }

    def intents(self, run_id: str) -> set[str]:
        return set(self.intent_hashes(run_id))

    def resolve_not_applied(
        self, run_id: str, operation_id: str, proven_hash: str
    ) -> None:
        self._begin()
        try:
            if self.db.execute(
                "SELECT 1 FROM intents WHERE run_id=? AND operation_id=?",
                (run_id, operation_id),
            ).fetchone() is None:
                raise ControlError(
                    "intent_missing",
                    "/reconcile",
                    "operation has no durable intent",
                    run_id,
                )
            self.db.execute(
                "INSERT INTO intent_resolutions VALUES (?, ?, 'not_applied', ?, ?)",
                (run_id, operation_id, proven_hash, time.time()),
            )
            self._audit_locked(
                run_id,
                "operation_not_applied",
                {"operation_id": operation_id, "proven_hash": proven_hash},
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "intent_resolved",
                "/reconcile",
                "operation intent was already resolved",
                run_id,
            ) from error
        except Exception:
            self._rollback()
            raise

    def not_applied_hashes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: proven_hash
            for operation_id, proven_hash in self.db.execute(
                "SELECT operation_id,proven_hash FROM intent_resolutions "
                "WHERE run_id=? AND resolution='not_applied'",
                (run_id,),
            )
        }

    def not_applied(self, run_id: str) -> set[str]:
        return set(self.not_applied_hashes(run_id))

    def unresolved_intents(self, run_id: str) -> set[str]:
        return self.intents(run_id) - set(self.outcomes(run_id)) - self.not_applied(run_id)

    def mark_rolled_back(self, run_id: str, operation_id: str) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "UPDATE outcomes SET state='rolled_back' "
                "WHERE run_id=? AND operation_id=? AND state='applied'",
                (run_id, operation_id),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "rollback_invalid",
                    "/rollback",
                    "operation was not applied by this run",
                    run_id,
                )
            self._audit_locked(
                run_id, "operation_rolled_back", {"operation_id": operation_id}
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def rollback_intent(
        self, run_id: str, operation_id: str, expected_hash: str
    ) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "INSERT OR IGNORE INTO rollback_intents VALUES (?, ?, ?, ?)",
                (run_id, operation_id, expected_hash, time.time()),
            )
            if result.rowcount == 1:
                self._audit_locked(
                    run_id,
                    "rollback_intent",
                    {"operation_id": operation_id, "expected_hash": expected_hash},
                )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def rollback_intents(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: expected_hash
            for operation_id, expected_hash in self.db.execute(
                "SELECT operation_id,expected_hash FROM rollback_intents WHERE run_id=?",
                (run_id,),
            )
        }

    def put_blob(self, name: str, value: bytes, run_id: str = "system") -> None:
        if SAFE_KEY.fullmatch(name) is None:
            raise ControlError("evidence_invalid", "/ledger/blobs", "invalid blob name")
        nonce = secrets.token_bytes(12)
        ciphertext = nonce + AESGCM(self._key).encrypt(nonce, value, name.encode())
        self._begin()
        try:
            replaced = self.db.execute(
                "SELECT 1 FROM blobs WHERE name=?", (name,)
            ).fetchone() is not None
            self.db.execute(
                "INSERT INTO blobs VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "ciphertext=excluded.ciphertext, created=excluded.created",
                (name, ciphertext, time.time()),
            )
            self._audit_locked(
                run_id,
                "evidence_replaced" if replaced else "evidence_stored",
                {"name_hash": hashlib.sha256(name.encode()).hexdigest()},
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def get_blob(self, name: str) -> bytes | None:
        row = self.db.execute(
            "SELECT ciphertext FROM blobs WHERE name=?", (name,)
        ).fetchone()
        if not row:
            return None
        value = row[0]
        return AESGCM(self._key).decrypt(value[:12], value[12:], name.encode())

    def load_preview(self, preview_hash: str) -> Preview:
        value = self.get_blob(f"preview:{preview_hash}")
        if value is None:
            raise ControlError(
                "preview_missing", "/ledger/blobs", "stored preview is unavailable"
            )
        return _preview_from_bytes(value)

    def incomplete_runs(self) -> list[dict[str, Any]]:
        self._verify_operational_integrity()
        terminal = ("verified", "rolled_back")
        return [
            {
                "run_id": row[0],
                "state": row[1],
                "preview_hash": row[2],
                "tenant_fingerprint": row[3],
                "project_id": row[4],
                "updated": row[5],
            }
            for row in self.db.execute(
                "SELECT run_id,state,preview_hash,tenant_fingerprint,project_id,updated "
                "FROM runs WHERE state NOT IN (?, ?) ORDER BY updated",
                terminal,
            )
        ]

    def purge_evidence(self, before: float | None = None) -> int:
        cutoff = before if before is not None else time.time() - 90 * 86400
        self._begin()
        try:
            result = self.db.execute(
                "DELETE FROM blobs WHERE created < ? AND name NOT IN ("
                "SELECT 'preview:' || preview_hash FROM runs "
                "WHERE state NOT IN ('verified', 'rolled_back'))",
                (cutoff,),
            )
            self._audit_locked(
                "system", "evidence_purged", {"count": result.rowcount}
            )
            self._commit()
            return result.rowcount
        except Exception:
            self._rollback()
            raise

    def acquire_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        now = time.time()
        fence = secrets.token_urlsafe(24)
        self._begin()
        try:
            blocking = self.db.execute(
                "SELECT run_id,state FROM runs WHERE project_id=? "
                "AND state NOT IN ('verified','rolled_back') AND run_id<>? "
                "ORDER BY updated LIMIT 1",
                (project, owner),
            ).fetchone()
            if blocking:
                raise ControlError(
                    "run_recovery_required",
                    "/locks",
                    "an incomplete run must be recovered before this project can change again",
                    str(blocking[0]),
                )
            self.db.execute("DELETE FROM locks WHERE expires < ?", (now,))
            self.db.execute(
                "INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?)",
                (project, owner, preview_hash, fence, now + lease_seconds, now),
            )
            self._audit_locked(
                owner,
                "lock_acquired",
                {"project_hash": _hash(project), "preview_hash": preview_hash},
            )
            self._commit()
            return fence
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError("lock_held", "/locks", "project is already locked") from error
        except Exception:
            self._rollback()
            raise

    def assert_lock(self, project: str, owner: str, preview_hash: str) -> str:
        row = self.db.execute(
            "SELECT owner,preview_hash,fence,expires FROM locks WHERE project=?", (project,)
        ).fetchone()
        if (
            not row
            or row[0] != owner
            or row[1] != preview_hash
            or row[3] <= time.time()
        ):
            raise ControlError("lock_lost", "/locks", "run no longer owns the lock", owner)
        return str(row[2])

    def renew_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        self._begin()
        try:
            result = self.db.execute(
                "UPDATE locks SET expires=? WHERE project=? AND owner=? "
                "AND preview_hash=? AND expires>?",
                (
                    time.time() + lease_seconds,
                    project,
                    owner,
                    preview_hash,
                    time.time(),
                ),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "lock_lost", "/locks", "run no longer owns the lock", owner
                )
            fence = self.db.execute(
                "SELECT fence FROM locks WHERE project=?", (project,)
            ).fetchone()[0]
            self._commit()
            return str(fence)
        except Exception:
            self._rollback()
            raise

    def ensure_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        """Renew this run's lease or safely reacquire it after expiry."""
        now = time.time()
        self._begin()
        try:
            row = self.db.execute(
                "SELECT owner,preview_hash,fence,expires FROM locks WHERE project=?",
                (project,),
            ).fetchone()
            if row and row[3] > now:
                if row[0] != owner or row[1] != preview_hash:
                    raise ControlError(
                        "lock_held", "/locks", "project has a competing live lease"
                    )
                self.db.execute(
                    "UPDATE locks SET expires=? WHERE project=?",
                    (now + lease_seconds, project),
                )
                fence = str(row[2])
            else:
                self.db.execute("DELETE FROM locks WHERE project=?", (project,))
                fence = secrets.token_urlsafe(24)
                self.db.execute(
                    "INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        project,
                        owner,
                        preview_hash,
                        fence,
                        now + lease_seconds,
                        now,
                    ),
                )
                self._audit_locked(
                    owner,
                    "lock_reacquired",
                    {"project_hash": _hash(project), "preview_hash": preview_hash},
                )
            self._commit()
            return fence
        except Exception:
            self._rollback()
            raise

    def release_lock(self, project: str, owner: str, preview_hash: str) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "DELETE FROM locks WHERE project=? AND owner=? AND preview_hash=?",
                (project, owner, preview_hash),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "lock_lost", "/locks", "lock ownership does not match", owner
                )
            self._audit_locked(
                owner, "lock_released", {"project_hash": _hash(project)}
            )
            self._commit()
        except Exception:
            self._rollback()
            raise


class ControlPlane:
    STATES = {
        "disconnected",
        "connected",
        "discovered",
        "previewed",
        "approved",
        "applying",
        "applied",
        "verified",
        "drift_detected",
        "outcome_ambiguous",
        "partially_applied",
        "rolling_back",
        "rolled_back",
        "manual_recovery",
    }

    def __init__(
        self,
        ledger: Ledger,
        policy: AdapterPolicy,
        transport: Callable[..., Any],
        resolver: Callable[[str], Sequence[str]] | None = None,
    ) -> None:
        self.ledger = ledger
        self.policy = policy
        self.transport = transport
        self.resolver = resolver
        self.connection: Connection | None = None
        self._credential: EphemeralCredential | None = None
        self.preview: Preview | None = None
        self._approved_hash: str | None = None
        self.session_state = "disconnected"

    def connect(
        self,
        origin: str,
        token: str,
        *,
        credential_ttl_seconds: int = 900,
        allow_private_origin: bool = False,
    ) -> Connection:
        canonical_origin, host = _canonical_origin(origin)
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            resolved = [literal.compressed]
        elif self.resolver is not None:
            try:
                resolved = list(self.resolver(host))
            except Exception as error:
                raise ControlError(
                    "resolution_failed",
                    "/connection/origin",
                    "origin could not be resolved by the DNS-only resolver",
                ) from error
        else:
            raise ControlError(
                "resolution_required",
                "/connection/origin",
                "a DNS-only resolver is required before identity transport",
            )
        pinned = _validate_addresses(host, resolved, allow_private_origin)
        credential = EphemeralCredential(
            token, time.time() + credential_ttl_seconds
        )
        try:
            identity = self.transport(
                "identity",
                origin=canonical_origin,
                pinned_addresses=pinned,
                redirects=False,
                credential=credential,
            )
            required = {
                "canonical_origin",
                "tenant_fingerprint",
                "actor",
                "permissions",
                "version",
                "resolved_addresses",
                "redirected",
            }
            if not isinstance(identity, Mapping) or set(identity) != required:
                raise ControlError(
                    "identity_invalid", "/connection", "identity response shape is invalid"
                )
            if (
                identity["canonical_origin"] != canonical_origin
                or identity["redirected"] is not False
            ):
                raise ControlError(
                    "identity_invalid",
                    "/connection/origin",
                    "redirected or off-origin identity response is forbidden",
                )
            identity_addresses = _validate_addresses(
                host, identity["resolved_addresses"], allow_private_origin
            )
            if identity_addresses != pinned:
                raise ControlError(
                    "identity_invalid",
                    "/connection/resolved_addresses",
                    "identity transport did not use the pinned address set",
                )
            permissions = identity["permissions"]
            if (
                not isinstance(permissions, list)
                or not all(
                    isinstance(item, str) and SAFE_KEY.fullmatch(item)
                    for item in permissions
                )
                or "admin" in permissions
            ):
                raise ControlError(
                    "identity_invalid",
                    "/connection/permissions",
                    "permissions are invalid",
                )
            claims = [
                identity[field]
                for field in ("tenant_fingerprint", "actor", "version")
            ]
            if not all(isinstance(value, str) and value for value in claims):
                raise ControlError(
                    "identity_invalid", "/connection", "identity claims are incomplete"
                )
        except Exception:
            credential.close()
            raise
        self.disconnect()
        self._credential = credential
        self.connection = Connection(
            secrets.token_urlsafe(24),
            canonical_origin,
            identity["tenant_fingerprint"],
            identity["actor"],
            tuple(sorted(set(permissions))),
            identity["version"],
            pinned,
            allow_private_origin,
        )
        self.preview = None
        self._approved_hash = None
        self.session_state = "connected"
        return self.connection

    def disconnect(self) -> None:
        if self._credential:
            self._credential.close()
        self._credential = None
        self.connection = None
        self.preview = None
        self._approved_hash = None
        self.session_state = "disconnected"

    def discover(
        self,
        fetch: Callable[[int], tuple[int, Sequence[Mapping[str, Any]]]],
    ) -> Capability:
        self._require_connection()
        capability = CapabilityDiscovery.pages(fetch)
        self.preview = None
        self._approved_hash = None
        self.session_state = "discovered"
        return capability

    def recoverable_runs(self) -> list[dict[str, Any]]:
        connection, _ = self._require_connection()
        return [
            run
            for run in self.ledger.incomplete_runs()
            if run["tenant_fingerprint"] == connection.tenant_fingerprint
        ]

    def resume_run(self, run_id: str) -> Preview:
        """Restore a protected preview for an incomplete durable run."""
        connection, _ = self._require_connection()
        run = self.ledger.run(run_id)
        if not run or run["state"] in {"verified", "rolled_back"}:
            raise ControlError(
                "run_invalid", "/runs", "run is not recoverable", run_id
            )
        preview = self.ledger.load_preview(str(run["preview_hash"]))
        if (
            preview.tenant_fingerprint != connection.tenant_fingerprint
            or preview.actor != connection.actor
            or preview.permissions != connection.permissions
            or preview.policy_hash != self.policy.digest
            or preview.project_id != run["project_id"]
        ):
            raise ControlError(
                "run_invalid",
                "/runs",
                "stored run does not match the current tenant, actor, permissions, or policy",
                run_id,
            )
        for operation in preview.operations:
            self.policy.validate(operation, connection.permissions)
        self.preview = preview
        self._approved_hash = None
        self.session_state = str(run["state"])
        return preview

    def make_preview(
        self,
        baseline: Any,
        project: Any,
        operations: Sequence[Operation],
        rollback_limitations: Sequence[str] = (),
        *,
        project_id: str = "project",
        ttl_seconds: int = 600,
    ) -> Preview:
        connection, _ = self._require_connection()
        if SAFE_KEY.fullmatch(project_id) is None:
            raise ControlError(
                "preview_invalid", "/preview/project_id", "safe project ID required"
            )
        ordered = _topological_operations(operations)
        for operation in ordered:
            self.policy.validate(operation, connection.permissions)
        if not all(isinstance(item, str) for item in rollback_limitations):
            raise ControlError(
                "preview_invalid",
                "/preview/rollback_limitations",
                "rollback limitations must be text",
            )
        material = {
            "connection_id": connection.id,
            "tenant_fingerprint": connection.tenant_fingerprint,
            "actor": connection.actor,
            "permissions": connection.permissions,
            "baseline_hash": _hash(baseline),
            "project_hash": _hash(project),
            "project_id": project_id,
            "policy_version": self.policy.version,
            "policy_hash": self.policy.digest,
            "operations": ordered,
            "rollback_limitations": tuple(rollback_limitations),
            "nonce": secrets.token_urlsafe(24),
            "expires_at": time.time() + ttl_seconds,
        }
        preview = Preview(**material, hash=_hash(material))
        self.preview = preview
        self._approved_hash = None
        self.session_state = "previewed"
        self.ledger.put_blob(
            f"preview:{preview.hash}", _canonical_bytes(preview), "preview"
        )
        return preview

    def approve(self, preview_hash: str) -> None:
        preview = self.preview
        if (
            not preview
            or preview.expires_at <= time.time()
            or not secrets.compare_digest(preview.hash, preview_hash)
            or not secrets.compare_digest(preview.hash, _hash(_preview_material(preview)))
        ):
            raise ControlError(
                "preview_invalid", "/approval", "preview is absent, expired, or changed"
            )
        self._approved_hash = preview_hash
        self.session_state = "approved"

    def apply(self, run_id: str, baseline: Any, project: Any) -> None:
        preview = self._valid_preview(baseline, project)
        connection, credential = self._require_connection()
        if SAFE_KEY.fullmatch(run_id) is None:
            raise ControlError("run_invalid", "/runs", "safe run ID required")
        self._approved_hash = None  # one-time approval is consumed before mutation.
        fence = self.ledger.acquire_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        try:
            self.ledger.begin_run(
                run_id,
                preview.hash,
                connection.tenant_fingerprint,
                preview.project_id,
            )
        except Exception:
            self.ledger.release_lock(preview.project_id, run_id, preview.hash)
            raise
        self.session_state = "applying"
        for operation in preview.operations:
            try:
                fence = self.ledger.ensure_lock(
                    preview.project_id,
                    run_id,
                    preview.hash,
                    self.policy.lease_seconds,
                )
                self._reauthorize(operation, fence)
                self._assert_run_fence(preview, run_id, fence)
                preimage = self._transport(
                    "precondition",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                self._assert_run_fence(preview, run_id, fence)
                if not isinstance(preimage, Mapping) or preimage.get("hash") != operation.precondition:
                    self.ledger.set_state(run_id, "drift_detected")
                    self.session_state = "drift_detected"
                    raise ControlError(
                        "precondition_failed",
                        "/apply",
                        "fresh precondition does not match the approved baseline",
                        run_id,
                    )
                self.ledger.intent(run_id, operation)
                started = time.monotonic()
                response = self._transport(
                    "write",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                try:
                    current_fence = self.ledger.assert_lock(
                        preview.project_id, run_id, preview.hash
                    )
                except ControlError:
                    current_fence = None
                if (
                    time.monotonic() - started > self.policy.call_timeout_seconds
                    or current_fence != fence
                ):
                    self.ledger.set_state(run_id, "outcome_ambiguous")
                    self.session_state = "outcome_ambiguous"
                    raise ControlError(
                        "outcome_ambiguous",
                        "/apply",
                        "write exceeded its approved time or fencing boundary",
                        run_id,
                    )
                if operation.method in WRITE_METHODS and (
                    not isinstance(response, Mapping) or response.get("ambiguous") is True
                ):
                    self.ledger.set_state(run_id, "outcome_ambiguous")
                    self.session_state = "outcome_ambiguous"
                    response = self._transport(
                        "reconcile",
                        connection,
                        credential,
                        operation=operation,
                        fencing_token=fence,
                    )
                    self._assert_run_fence(preview, run_id, fence)
                    if not isinstance(response, Mapping) or response.get("matched") is not True:
                        raise ControlError(
                            "outcome_ambiguous",
                            "/apply",
                            "write outcome could not be reconciled",
                            run_id,
                        )
                readback = self._transport(
                    "readback",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                self._assert_run_fence(preview, run_id, fence)
                if not isinstance(readback, Mapping) or readback.get("hash") != operation.postcondition:
                    self.ledger.set_state(run_id, "outcome_ambiguous")
                    self.session_state = "outcome_ambiguous"
                    raise ControlError(
                        "readback_failed",
                        "/apply",
                        "authoritative readback does not match the approved postcondition",
                        run_id,
                    )
                self.ledger.outcome(run_id, operation.id, operation.postcondition)
            except ControlError:
                self._classify_apply_failure(run_id)
                raise
            except Exception as error:
                self._classify_apply_failure(run_id)
                raise ControlError(
                    "transport_failed",
                    "/apply",
                    "adapter failed; reconciliation is required",
                    run_id,
                ) from error
        try:
            self._assert_run_fence(preview, run_id, fence)
            self.ledger.set_state(run_id, "applied")
        except ControlError:
            self._classify_apply_failure(run_id)
            raise
        self.session_state = "applied"

    def verify(self, run_id: str) -> None:
        preview = self._run_preview(run_id, {"applied"})
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        outcomes = self.ledger.outcomes(run_id)
        if set(outcomes) != {operation.id for operation in preview.operations}:
            self.ledger.set_state(run_id, "manual_recovery")
            self.session_state = "manual_recovery"
            raise ControlError(
                "verification_incomplete",
                "/verify",
                "durable applied-operation evidence is incomplete",
                run_id,
            )
        for operation in preview.operations:
            self._reauthorize(operation, fence)
            self._assert_run_fence(preview, run_id, fence)
            evidence = self._transport(
                "verify",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            if not isinstance(evidence, Mapping) or evidence.get("hash") != outcomes[operation.id]:
                self.ledger.set_state(run_id, "drift_detected")
                self.session_state = "drift_detected"
                raise ControlError(
                    "verification_failed",
                    "/verify",
                    "fresh verification found drift or incomplete evidence",
                    run_id,
                )
        self._assert_run_fence(preview, run_id, fence)
        self.ledger.set_state(run_id, "verified")
        self.session_state = "verified"
        self.ledger.release_lock(preview.project_id, run_id, preview.hash)

    def reconcile(self, run_id: str) -> None:
        """Resolve every durable intent whose write outcome is still unknown."""
        preview = self._run_preview(run_id, {"outcome_ambiguous"})
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        outcomes = self.ledger.outcomes(run_id)
        by_id = {operation.id: operation for operation in preview.operations}
        for operation_id in sorted(self.ledger.unresolved_intents(run_id)):
            operation = by_id.get(operation_id)
            if operation is None:
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/reconcile",
                    "durable intent is absent from the protected preview",
                    run_id,
                )
            self._reauthorize(operation, fence)
            self._assert_run_fence(preview, run_id, fence)
            reconciled = self._transport(
                "reconcile",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            if not isinstance(reconciled, Mapping):
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/reconcile",
                    "ambiguous write could not be proven",
                    run_id,
                )
            if (
                reconciled.get("matched") is False
                and reconciled.get("hash") == operation.precondition
            ):
                self.ledger.resolve_not_applied(
                    run_id, operation.id, operation.precondition
                )
                continue
            if not (
                reconciled.get("matched") is True
                and reconciled.get("hash") == operation.postcondition
            ):
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/reconcile",
                    "ambiguous write matched neither approved preimage nor postimage",
                    run_id,
                )
            readback = self._transport(
                "readback",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            if not isinstance(readback, Mapping) or readback.get("hash") != operation.postcondition:
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/reconcile",
                    "reconciled write failed authoritative readback",
                    run_id,
                )
            self.ledger.outcome(run_id, operation.id, operation.postcondition)
        outcomes = self.ledger.outcomes(run_id)
        self._assert_run_fence(preview, run_id, fence)
        if set(outcomes) == {operation.id for operation in preview.operations}:
            self.ledger.set_state(run_id, "applied")
            self.session_state = "applied"
        else:
            self.ledger.set_state(run_id, "partially_applied")
            self.session_state = "partially_applied"

    def detect_drift(self, run_id: str, current_baseline: Any) -> bool:
        preview = self.preview
        if not preview or _hash(current_baseline) == preview.baseline_hash:
            return False
        if self.ledger.run(run_id):
            self.ledger.set_state(run_id, "drift_detected")
        self.session_state = "drift_detected"
        return True

    def rollback(self, run_id: str) -> None:
        preview = self._run_preview(
            run_id,
            {
                "applied",
                "verified",
                "drift_detected",
                "outcome_ambiguous",
                "partially_applied",
                "rolling_back",
                "manual_recovery",
            },
        )
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        outcomes = self.ledger.outcomes(run_id)
        unresolved = self.ledger.unresolved_intents(run_id)
        if unresolved:
            raise ControlError(
                "outcome_ambiguous",
                "/rollback",
                "ambiguous writes must be reconciled before rollback",
                run_id,
            )
        if not outcomes:
            self._assert_run_fence(preview, run_id, fence)
            self.ledger.set_state(run_id, "rolled_back")
            self.session_state = "rolled_back"
            self.ledger.release_lock(preview.project_id, run_id, preview.hash)
            return
        self.ledger.set_state(run_id, "rolling_back")
        self.session_state = "rolling_back"
        rollback_intents = self.ledger.rollback_intents(run_id)
        for operation in reversed(preview.operations):
            if operation.id not in outcomes:
                continue
            fence = self.ledger.ensure_lock(
                preview.project_id,
                run_id,
                preview.hash,
                self.policy.lease_seconds,
            )
            self._reauthorize(operation, fence)
            self._assert_run_fence(preview, run_id, fence)
            current = self._transport(
                "current_hash",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            expected = operation.rollback.get("postcondition", operation.precondition)
            if (
                isinstance(current, Mapping)
                and current.get("hash") == expected
                and rollback_intents.get(operation.id) == expected
            ):
                self.ledger.mark_rolled_back(run_id, operation.id)
                continue
            if (
                not isinstance(current, Mapping)
                or current.get("hash") != outcomes[operation.id]
            ):
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/rollback",
                    "resource changed after apply; automatic rollback stopped",
                    run_id,
                )
            action = "deactivate" if operation.rollback.get("created") is True else "restore"
            if action == "restore" and operation.rollback.get("preimage") is None:
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/rollback",
                    "operation has no approved inverse",
                    run_id,
                )
            self.ledger.rollback_intent(run_id, operation.id, str(expected))
            try:
                result = self._transport(
                    "rollback",
                    connection,
                    credential,
                    operation=operation,
                    action=action,
                    fencing_token=fence,
                )
            except Exception as error:
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/rollback",
                    "rollback outcome is ambiguous and must be reconciled",
                    run_id,
                ) from error
            self._assert_run_fence(preview, run_id, fence)
            readback = self._transport(
                "current_hash",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            if (
                not isinstance(result, Mapping)
                or result.get("hash") != expected
                or not isinstance(readback, Mapping)
                or readback.get("hash") != expected
            ):
                self.ledger.set_state(run_id, "manual_recovery")
                self.session_state = "manual_recovery"
                raise ControlError(
                    "manual_recovery",
                    "/rollback",
                    "rollback readback failed",
                    run_id,
                )
            self.ledger.mark_rolled_back(run_id, operation.id)
        self._assert_run_fence(preview, run_id, fence)
        self.ledger.set_state(run_id, "rolled_back")
        self.session_state = "rolled_back"
        self.ledger.release_lock(preview.project_id, run_id, preview.hash)

    def _transport(
        self,
        kind: str,
        connection: Connection,
        credential: EphemeralCredential,
        **kwargs: Any,
    ) -> Any:
        return self.transport(
            kind,
            connection=connection,
            credential=credential,
            timeout_seconds=self.policy.call_timeout_seconds,
            **kwargs,
        )

    def _assert_run_fence(
        self, preview: Preview, run_id: str, expected_fence: str
    ) -> None:
        current_fence = self.ledger.assert_lock(
            preview.project_id, run_id, preview.hash
        )
        if not secrets.compare_digest(current_fence, expected_fence):
            raise ControlError(
                "lock_lost",
                "/locks",
                "run fencing token changed during adapter work",
                run_id,
            )

    def _classify_apply_failure(self, run_id: str) -> None:
        """Give every post-begin apply exit a durable recovery state."""
        if self.ledger.state(run_id) != "applying":
            return
        state = (
            "outcome_ambiguous"
            if self.ledger.unresolved_intents(run_id)
            else "partially_applied"
        )
        self.ledger.set_state(run_id, state)
        self.session_state = state

    def _reauthorize(
        self, operation: Operation, fencing_token: str | None = None
    ) -> None:
        connection, credential = self._require_connection()
        credential.reveal()
        self.policy.validate(operation, connection.permissions)
        identity = self._transport(
            "reauthorize",
            connection,
            credential,
            fencing_token=fencing_token,
        )
        if (
            not isinstance(identity, Mapping)
            or identity.get("tenant_fingerprint") != connection.tenant_fingerprint
            or identity.get("actor") != connection.actor
            or tuple(sorted(identity.get("permissions", ()))) != connection.permissions
            or tuple(sorted(identity.get("resolved_addresses", ())))
            != connection.pinned_addresses
            or identity.get("canonical_origin") != connection.origin
            or identity.get("version") != connection.version
        ):
            raise ControlError(
                "authorization_changed",
                "/connection",
                "tenant, actor, permission, or address binding changed",
            )

    def _require_connection(self) -> tuple[Connection, EphemeralCredential]:
        if not self.connection or not self._credential:
            raise ControlError(
                "disconnected", "/connection", "session connection is required"
            )
        self._credential.reveal()
        return self.connection, self._credential

    def _valid_preview(self, baseline: Any, project: Any) -> Preview:
        connection, _ = self._require_connection()
        preview = self.preview
        if (
            not preview
            or not self._approved_hash
            or preview.expires_at <= time.time()
            or not secrets.compare_digest(self._approved_hash, preview.hash)
            or not secrets.compare_digest(preview.hash, _hash(_preview_material(preview)))
            or preview.connection_id != connection.id
            or preview.tenant_fingerprint != connection.tenant_fingerprint
            or preview.actor != connection.actor
            or preview.permissions != connection.permissions
            or preview.policy_hash != self.policy.digest
            or preview.baseline_hash != _hash(baseline)
            or preview.project_hash != _hash(project)
        ):
            raise ControlError(
                "approval_invalidated",
                "/apply",
                "preview approval is absent, expired, changed, or rebound",
            )
        return preview

    def _run_preview(self, run_id: str, allowed_states: set[str]) -> Preview:
        connection, _ = self._require_connection()
        run = self.ledger.run(run_id)
        preview = self.preview
        if (
            not run
            or run["state"] not in allowed_states
            or not preview
            or run["preview_hash"] != preview.hash
            or run["tenant_fingerprint"] != connection.tenant_fingerprint
            or run["project_id"] != preview.project_id
            or preview.hash != _hash(_preview_material(preview))
            or preview.actor != connection.actor
            or preview.permissions != connection.permissions
            or preview.policy_hash != self.policy.digest
        ):
            raise ControlError(
                "run_invalid",
                "/runs",
                "run is not bound to this preview, tenant, and state",
                run_id,
            )
        by_id = {operation.id: operation for operation in preview.operations}
        intent_hashes = self.ledger.intent_hashes(run_id)
        outcomes = self.ledger.outcomes(run_id)
        not_applied = self.ledger.not_applied_hashes(run_id)
        rollback_intents = self.ledger.rollback_intents(run_id)
        evidence_valid = (
            (set(outcomes) | set(not_applied) | set(rollback_intents))
            <= set(intent_hashes)
            and set(outcomes).isdisjoint(not_applied)
            and all(
                operation_id in by_id
                and operation_hash == _hash(by_id[operation_id])
                for operation_id, operation_hash in intent_hashes.items()
            )
            and all(
                operation_id in by_id
                and postimage_hash == by_id[operation_id].postcondition
                for operation_id, postimage_hash in outcomes.items()
            )
            and all(
                operation_id in by_id
                and proven_hash == by_id[operation_id].precondition
                for operation_id, proven_hash in not_applied.items()
            )
            and all(
                operation_id in by_id
                and expected_hash
                == by_id[operation_id].rollback.get(
                    "postcondition", by_id[operation_id].precondition
                )
                for operation_id, expected_hash in rollback_intents.items()
            )
        )
        if not evidence_valid:
            raise ControlError(
                "ledger_integrity",
                "/ledger",
                "authenticated operational evidence does not match the protected preview",
                run_id,
            )
        return preview


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: Mapping[str, str]
    body: Any = None


@dataclass(frozen=True)
class Response:
    status: int
    body: Mapping[str, Any]


class LocalDispatcher:
    """Pure loopback dispatcher with one-time bootstrap and expiring CSRF sessions."""

    def __init__(
        self,
        host: str,
        origin: str,
        bootstrap_secret: str,
        routes: Mapping[str, tuple[str, ...]],
        *,
        session_ttl_seconds: int = 900,
        max_sessions: int = 4,
    ) -> None:
        if not re.fullmatch(r"127\.0\.0\.1(?::[0-9]{1,5})?", host):
            raise ControlError(
                "host_invalid", "/dispatcher", "dispatcher must use numeric loopback"
            )
        if origin != f"http://{host}":
            raise ControlError(
                "origin_invalid", "/dispatcher", "origin must match loopback host"
            )
        if not isinstance(bootstrap_secret, str) or len(bootstrap_secret) < 32:
            raise ControlError(
                "bootstrap_invalid",
                "/dispatcher",
                "launcher bootstrap secret must contain at least 32 characters",
            )
        self.host = host
        self.origin = origin
        self._bootstrap_hash = hashlib.sha256(bootstrap_secret.encode()).digest()
        self._bootstrap_available = True
        self._sessions: dict[str, tuple[str, float]] = {}
        self._routes = {
            path: tuple(sorted(set(methods))) for path, methods in routes.items()
        }
        self.session_ttl_seconds = session_ttl_seconds
        self.max_sessions = max_sessions

    def dispatch(
        self,
        request: Request,
        handler: Callable[[Request, str], Mapping[str, Any]],
    ) -> Response:
        if (
            request.headers.get("Host") != self.host
            or request.headers.get("Origin") != self.origin
        ):
            return Response(
                403,
                ControlError(
                    "origin_forbidden", request.path, "Host and Origin must match"
                ).public(),
            )
        self._expire_sessions()
        if request.path == "/bootstrap" and request.method == "POST":
            supplied = request.headers.get("X-Bootstrap-Token", "")
            supplied_hash = hashlib.sha256(supplied.encode()).digest()
            if (
                not self._bootstrap_available
                or not hmac.compare_digest(supplied_hash, self._bootstrap_hash)
                or len(self._sessions) >= self.max_sessions
            ):
                return Response(
                    401,
                    ControlError(
                        "bootstrap_denied",
                        request.path,
                        "one-time launcher bootstrap is required",
                    ).public(),
                )
            self._bootstrap_available = False
            session_id = secrets.token_urlsafe(24)
            csrf = secrets.token_urlsafe(24)
            self._sessions[session_id] = (
                csrf,
                time.time() + self.session_ttl_seconds,
            )
            return Response(201, {"session_id": session_id, "csrf": csrf})
        allowed = self._routes.get(request.path, ())
        if request.method not in allowed:
            return Response(
                404,
                ControlError("route_not_found", request.path, "route is unavailable").public(),
            )
        session_id = request.headers.get("X-Session")
        session = self._sessions.get(session_id or "")
        if not session:
            return Response(
                401,
                ControlError(
                    "session_required", request.path, "bootstrap session required"
                ).public(),
            )
        if (
            request.method not in READ_METHODS
            and request.headers.get("X-CSRF-Token") != session[0]
        ):
            return Response(
                403,
                ControlError(
                    "csrf_invalid", request.path, "valid CSRF token required"
                ).public(),
            )
        try:
            body = _strict_json(handler(request, session_id), "response")
        except ControlError as error:
            return Response(400, error.public())
        return Response(200, body)

    def revoke_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _expire_sessions(self) -> None:
        now = time.time()
        self._sessions = {
            session_id: session
            for session_id, session in self._sessions.items()
            if session[1] > now
        }
