"""Shared protocol, JSON, and origin validation primitives."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import urllib.parse
from types import MappingProxyType
from typing import Any, Mapping, Sequence

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

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, state TEXT NOT NULL, preview_hash TEXT NOT NULL, tenant_fingerprint TEXT NOT NULL, project_id TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS intents (run_id TEXT NOT NULL, operation_id TEXT NOT NULL, operation_hash TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));
CREATE TABLE IF NOT EXISTS outcomes (run_id TEXT NOT NULL, operation_id TEXT NOT NULL, postimage_hash TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));
CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, metadata TEXT NOT NULL, previous_mac TEXT NOT NULL, entry_mac TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS blobs (name TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS locks (project TEXT PRIMARY KEY, owner TEXT NOT NULL, preview_hash TEXT NOT NULL, fence TEXT NOT NULL, expires REAL NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rollback_intents (run_id TEXT NOT NULL, operation_id TEXT NOT NULL, expected_hash TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));
CREATE TABLE IF NOT EXISTS intent_resolutions (run_id TEXT NOT NULL, operation_id TEXT NOT NULL, resolution TEXT NOT NULL, proven_hash TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));
"""


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


def _sensitive_key(key: str) -> bool:
    parts = _key_parts(key)
    return bool(
        parts & SENSITIVE_PARTS
        or {"api", "key"} <= parts
        or {"private", "key"} <= parts
    )


def _strict_number(value: Any, path: str) -> float:
    if value == value and value not in (float("inf"), -float("inf")):
        return value
    raise ControlError("invalid_json", path, "finite JSON number required")


def _strict_mapping(value: Mapping[Any, Any], path: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ControlError("invalid_json", path, "JSON object keys must be strings")
        if _sensitive_key(key):
            raise ControlError(
                "sensitive_input", f"{path}.{key}", "credential-shaped fields are forbidden"
            )
        result[key] = _strict_json(item, f"{path}.{key}")
    return result


def _strict_json(value: Any, path: str = "value") -> Any:
    """Return plain JSON values or reject non-deterministic/custom objects."""
    if value is None or value.__class__ in {bool, int, str}:
        return value
    if value.__class__ is float:
        return _strict_number(value, path)
    if isinstance(value, (list, tuple)):
        return [_strict_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return _strict_mapping(value, path)
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


def _invalid_origin_parts(parsed: urllib.parse.SplitResult) -> bool:
    return (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query or parsed.fragment)
        or parsed.path not in ("", "/")
    )


def _canonical_origin(value: str) -> tuple[str, str]:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ControlError(
            "invalid_origin", "/connection/origin", "origin port or host is invalid"
        ) from error
    if _invalid_origin_parts(parsed):
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
        return _canonical_dns_host(host)


def _canonical_dns_host(host: str) -> str:
    try:
        canonical = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ControlError("invalid_origin", "/connection/origin", "origin host is invalid") from error
    labels = canonical.split(".")
    invalid = len(canonical) > 253 or any(HOST_LABEL.fullmatch(label) is None for label in labels)
    numeric_quad = len(labels) == 4 and all(label.isdigit() for label in labels)
    if invalid or numeric_quad:
        raise ControlError("invalid_origin", "/connection/origin", "origin host is invalid")
    return canonical


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
    normalized = [_validated_address(value, allow_private) for value in addresses]
    _require_literal_address(host, normalized)
    return tuple(sorted(set(normalized)))


def _validated_address(value: Any, allow_private: bool) -> str:
    if not isinstance(value, str):
        raise ControlError("identity_invalid", "/connection/resolved_addresses", "resolved addresses must be IP strings")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ControlError("identity_invalid", "/connection/resolved_addresses", "resolved address is invalid") from error
    if not allow_private and not address.is_global:
        raise ControlError("origin_forbidden", "/connection/origin", "private, loopback, link-local, and reserved origins require an explicit on-prem policy")
    return address.compressed


def _require_literal_address(host: str, addresses: Sequence[str]) -> None:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and literal.compressed not in addresses:
        raise ControlError(
            "identity_invalid",
            "/connection/resolved_addresses",
            "literal origin and pinned address do not match",
        )
