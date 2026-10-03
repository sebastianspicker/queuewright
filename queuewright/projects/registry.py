"""The packaged feature catalog and capability registry, loaded once per process.

Both registries are read lazily on first use, validated once, and cached. The
cached documents are never handed out: every accessor returns a fresh deep
copy, so callers may embed or mutate results without aliasing shared state.
"""

from __future__ import annotations

import copy
import functools
import json
import re
from pathlib import Path
from typing import Any

from ..contracts.paths import catalog_path
from ..contracts.safety import SafeJsonError, validate_safe_json
from ..errors import ConfigurationError

FEATURE_CATALOG_PATH = catalog_path("features.json")
CAPABILITY_REGISTRY_PATH = catalog_path("capabilities.json")
CAPABILITY_FIELDS = {"id", "domain", "delivery", "default_completion", "risk", "dependencies"}
CAPABILITY_ID = re.compile(r"[a-z][a-z0-9-]*")
COMPLETIONS = frozenset({"decision_required", "ready", "applied", "verified", "blocked"})
DELIVERIES = frozenset({"automated", "guided_manual", "verify_only", "unsupported"})
RISKS = frozenset({"low", "medium", "high", "critical"})


def load_feature_catalog() -> dict[str, Any]:
    """Return a detached copy of the whole validated feature catalog document."""
    return copy.deepcopy(_feature_catalog())


def load_features() -> list[dict[str, Any]]:
    """Return a detached copy of the validated feature catalog entries."""
    return copy.deepcopy(_feature_catalog()["features"])


def load_capabilities() -> list[dict[str, Any]]:
    """Return a detached copy of the validated capability registry, sorted by ID."""
    return copy.deepcopy(_capabilities())


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot read {label}: {error}") from error


def _require_acyclic(dependencies_by_id: dict[str, set[str]], label: str) -> None:
    remaining = {key: set(dependencies) for key, dependencies in dependencies_by_id.items()}
    complete: set[str] = set()
    while remaining:
        ready = sorted(key for key, dependencies in remaining.items() if dependencies <= complete)
        if not ready:
            raise ConfigurationError(f"{label} dependencies contain a cycle: {min(remaining)}")
        for key in ready:
            complete.add(key)
            del remaining[key]


def _valid_dependency_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(set(value))
    )


@functools.cache
def _feature_catalog() -> dict[str, Any]:
    catalog = _read_json(FEATURE_CATALOG_PATH, "feature registry")
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema_version", "features"}
        or catalog.get("schema_version") != "1.0"
        or not isinstance(catalog.get("features"), list)
    ):
        raise ConfigurationError("feature registry has an invalid shape")
    _validate_features(catalog["features"])
    return catalog


def _validate_features(features: list[Any]) -> None:
    if not all(isinstance(feature, dict) for feature in features):
        raise ConfigurationError("feature registry features are invalid")
    feature_ids = [feature.get("id") for feature in features]
    if not (
        all(isinstance(feature_id, str) for feature_id in feature_ids)
        and len(feature_ids) == len(set(feature_ids))
        and all(
            feature.get("default_enabled").__class__ is bool
            and feature.get("locked").__class__ is bool
            and isinstance(feature.get("settings"), dict)
            for feature in features
        )
    ):
        raise ConfigurationError("feature registry features are invalid")
    known = set(feature_ids)
    dependencies_by_id: dict[str, set[str]] = {}
    for feature in features:
        try:
            validate_safe_json(feature["settings"], "catalog.settings")
        except SafeJsonError as error:
            raise ConfigurationError("feature registry feature settings are unsafe") from error
        dependencies = feature.get("dependencies")
        if not _valid_dependency_list(dependencies):
            raise ConfigurationError(
                f"feature registry feature {feature['id']} dependencies are invalid"
            )
        unknown = set(dependencies) - known
        if unknown:
            raise ConfigurationError(
                f"feature registry feature {feature['id']} has unknown dependency: {min(unknown)}"
            )
        dependencies_by_id[feature["id"]] = set(dependencies)
    _require_acyclic(dependencies_by_id, "feature registry feature")


@functools.cache
def _capabilities() -> list[dict[str, Any]]:
    registry = _read_json(CAPABILITY_REGISTRY_PATH, "capability registry")
    if (
        not isinstance(registry, dict)
        or set(registry) != {"capabilities"}
        or not isinstance(registry["capabilities"], list)
    ):
        raise ConfigurationError("capability registry must contain exactly a capabilities list")
    capabilities = registry["capabilities"]
    ids: set[str] = set()
    for index, capability in enumerate(capabilities):
        ids.add(_validate_capability(capability, index, ids))
    for capability in capabilities:
        unknown = set(capability["dependencies"]) - ids
        if unknown:
            raise ConfigurationError(
                f"capability registry entry {capability['id']} has unknown dependency: "
                f"{min(unknown)}"
            )
    _require_acyclic(
        {capability["id"]: set(capability["dependencies"]) for capability in capabilities},
        "capability registry",
    )
    return sorted(capabilities, key=lambda item: item["id"])


def _validate_capability(capability: Any, index: int, ids: set[str]) -> str:
    if not isinstance(capability, dict) or set(capability) != CAPABILITY_FIELDS:
        raise ConfigurationError(f"capability registry entry {index} has an invalid shape")
    capability_id = capability["id"]
    if (
        not isinstance(capability_id, str)
        or not CAPABILITY_ID.fullmatch(capability_id)
        or capability_id in ids
    ):
        raise ConfigurationError(f"capability registry entry {index} has an invalid id")
    if not isinstance(capability["domain"], str) or not capability["domain"]:
        raise ConfigurationError(
            f"capability registry entry {capability_id} has an invalid domain"
        )
    if (
        capability["delivery"] not in DELIVERIES
        or capability["default_completion"] not in COMPLETIONS
        or capability["risk"] not in RISKS
    ):
        raise ConfigurationError(f"capability registry entry {capability_id} has invalid metadata")
    if not _valid_dependency_list(capability["dependencies"]):
        raise ConfigurationError(
            f"capability registry entry {capability_id} has invalid dependencies"
        )
    if capability_id in capability["dependencies"]:
        raise ConfigurationError(f"capability registry entry {capability_id} depends on itself")
    if capability["delivery"] == "unsupported" and capability["default_completion"] != "blocked":
        raise ConfigurationError(f"unsupported capability {capability_id} must default to blocked")
    return capability_id
