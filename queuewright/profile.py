"""Strict, local-only JSON profile loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .profile_automation import (
    _validate_automation,
    _validate_object_manager,
    _validate_reports,
)
from .profile_catalog import (
    _validate_checklists,
    _validate_groups,
    _validate_identity,
    _validate_macros,
    _validate_organizations,
    _validate_overviews,
    _validate_roles,
    _validate_users,
)
from .profile_support import (
    FIELD_COLLECTIONS,
    MANIFEST_FIELDS,
    MANIFEST_KEY,
    NAMESPACE,
    PROFILE_FIELDS,
    PROFILE_KEY,
    RESOURCE_KEY,
    SAFETY_ALLOWED_FIELDS,
    SAFETY_REQUIRED_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS,
    _canonical_hash,
    _fail,
    _json,
    _keyed_items,
    _reject_url_values,
    _repo_root,
    _sensitive_path,
    _shape,
    is_forbidden_local_path,
)
from .profile_uat import _validate_uat


__all__ = ["is_forbidden_local_path", "load_profile", "validate_loaded_profile", "validate_profile"]


def _profile_path(profile: str | Path) -> Path:
    supplied = Path(profile)
    profile_path = (supplied / "profile.json" if supplied.is_dir() else supplied).resolve()
    if profile_path.suffix.lower() != ".json" or _sensitive_path(profile_path):
        _fail("profile path must be a non-sensitive JSON file")
    return profile_path


def _manifest_name(bundle: dict[str, Any]) -> str:
    manifest_name = bundle.get("manifest")
    if (
        not isinstance(manifest_name, str)
        or not manifest_name
        or Path(manifest_name).is_absolute()
        or Path(manifest_name).suffix.lower() != ".json"
    ):
        _fail("profile manifest must be a non-empty relative JSON path")
    return manifest_name


def _manifest_path(profile_path: Path, manifest_name: str) -> Path:
    manifest_path = (profile_path.parent / manifest_name).resolve()
    if manifest_path == profile_path or _sensitive_path(manifest_path):
        _fail("manifest path is forbidden")
    allowed_root = (_repo_root(profile_path.parent) or profile_path.parent).resolve()
    try:
        manifest_path.relative_to(allowed_root)
    except ValueError:
        _fail("manifest path escapes its allowed root")
    return manifest_path


def load_profile(profile: str | Path) -> dict[str, Any]:
    """Load only an explicit local profile and its local JSON manifest."""
    profile_path = _profile_path(profile)
    bundle = _json(profile_path)
    manifest_path = _manifest_path(profile_path, _manifest_name(bundle))
    return {
        "profile": bundle,
        "manifest": _json(manifest_path),
        "profile_path": profile_path,
        "manifest_path": manifest_path,
    }


def _validate_schema_versions(bundle: dict[str, Any], manifest: dict[str, Any]) -> str:
    schema_version = bundle.get("schema_version")
    if (
        schema_version not in SUPPORTED_SCHEMA_VERSIONS
        or manifest.get("schema_version") != schema_version
    ):
        _fail("profile and manifest schema_version must match 1.0 or 1.1")
    return schema_version


def _validate_profile_identifier(bundle: dict[str, Any]) -> None:
    if (
        not isinstance(bundle.get("profile_key"), str)
        or PROFILE_KEY.fullmatch(bundle["profile_key"]) is None
    ):
        _fail("invalid profile_key")


def _validate_manifest_identifier(manifest: dict[str, Any]) -> None:
    if (
        not isinstance(manifest.get("manifest_key"), str)
        or MANIFEST_KEY.fullmatch(manifest["manifest_key"]) is None
    ):
        _fail("invalid manifest_key")


def _validate_profile_metadata(bundle: dict[str, Any], manifest: dict[str, Any]) -> None:
    _validate_profile_identifier(bundle)
    _validate_manifest_identifier(manifest)
    if (
        not isinstance(bundle.get("display_name"), str)
        or not bundle["display_name"].strip()
        or bundle.get("offline_only") is not True
    ):
        _fail("profile requires display_name and offline_only true")


def _validate_profile_structure(
    bundle: dict[str, Any], manifest: dict[str, Any]
) -> str:
    if set(bundle) != PROFILE_FIELDS:
        _fail("profile must contain exactly the supported fields")
    if set(manifest) != MANIFEST_FIELDS:
        _fail("manifest must contain exactly the supported fields")
    _reject_url_values(bundle, "profile")
    _reject_url_values(manifest, "manifest")
    return _validate_schema_versions(bundle, manifest)


def _validate_profile_namespace(manifest: dict[str, Any]) -> tuple[str, str]:
    prefix = manifest.get("managed_prefix")
    namespace = manifest.get("technical_namespace")
    if (
        not isinstance(prefix, str)
        or len(prefix) < 2
        or not isinstance(namespace, str)
        or NAMESPACE.fullmatch(namespace) is None
    ):
        _fail("invalid managed prefix or technical namespace")
    return prefix, namespace


def _validate_safety_required_values(safety: dict[str, Any]) -> None:
    if (
        safety.get("allow_existing_object_writes") is not False
        or safety.get("allow_delete") is not False
        or safety.get("production_group_reference") != "forbidden"
        or safety.get("activation_strategy")
        != "create_inactive_then_readback_collision_scan_then_activate"
    ):
        _fail("invalid safety contract")


def _validate_safety_optional_values(safety: dict[str, Any]) -> None:
    surfaces = safety.get("global_surfaces_accepted")
    if (
        surfaces is not None
        and (
            not isinstance(surfaces, list)
            or not all(
                isinstance(value, str) and value.strip() for value in surfaces
            )
        )
    ):
        _fail("safety_contract.global_surfaces_accepted must be a string list")
    _validate_safety_text_values(safety)


def _validate_safety_text_values(safety: dict[str, Any]) -> None:
    for text_field in (
        "identity_resolution",
        "object_manager",
        "production_impact_claim",
    ):
        if text_field in safety and (
            not isinstance(safety[text_field], str) or not safety[text_field].strip()
        ):
            _fail(f"safety_contract.{text_field} must be non-empty text")


def _validate_safety_contract(manifest: dict[str, Any]) -> None:
    safety = _shape(
        manifest.get("safety_contract"),
        "safety_contract",
        required=SAFETY_REQUIRED_FIELDS,
        allowed=SAFETY_ALLOWED_FIELDS,
    )
    _validate_safety_required_values(safety)
    _validate_safety_optional_values(safety)


def _validate_reference_set_shape(reference_sets: Any) -> dict[str, Any]:
    if not isinstance(reference_sets, dict) or set(reference_sets) != {"H", "O", "R", "S"}:
        _fail("reference set descriptors are invalid or S does not match restricted leaves")
    return reference_sets


def _validate_reference_set_descriptors(reference_sets: dict[str, Any]) -> None:
    if (
        reference_sets.get("H") != "all managed ticket-bearing group keys"
        or reference_sets.get("O") != "all managed organization keys"
        or reference_sets.get("R") != "all managed role keys"
    ):
        _fail("reference set descriptors are invalid or S does not match restricted leaves")


def _validate_restricted_reference_set(
    reference_sets: dict[str, Any], restricted: set[str]
) -> None:
    values = reference_sets["S"]
    if (
        not isinstance(values, list)
        or not all(
            isinstance(value, str) and RESOURCE_KEY.fullmatch(value) is not None
            for value in values
        )
        or set(values) != restricted
        or len(values) != len(set(values))
    ):
        _fail("reference set descriptors are invalid or S does not match restricted leaves")


def _validate_reference_sets(reference_sets: Any, restricted: set[str]) -> None:
    validated = _validate_reference_set_shape(reference_sets)
    _validate_reference_set_descriptors(validated)
    _validate_restricted_reference_set(validated, restricted)


def _manifest_collections(
    manifest: dict[str, Any], namespace: str
) -> dict[str, Any]:
    collections = {
        "overviews": _keyed_items(manifest.get("overviews"), "overviews"),
        "macros": _keyed_items(manifest.get("macros"), "macros"),
        "checklists": _keyed_items(
            manifest.get("checklist_templates"), "checklist templates"
        ),
        "triggers": _keyed_items(manifest.get("triggers"), "triggers"),
        "jobs": _keyed_items(manifest.get("jobs"), "jobs"),
        "reports": _keyed_items(manifest.get("report_profiles"), "report profiles"),
    }
    tags = manifest.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or not all(
            isinstance(tag, str) and tag.startswith(namespace.removesuffix("_") + "/")
            for tag in tags
        )
        or len(tags) != len(set(tags))
    ):
        _fail("tags must be unique and namespaced")
    collections["tags"] = tags
    collections["tag_set"] = set(tags)
    return collections


def _validate_collection_contracts(
    collections: dict[str, Any], prefix: str, leaf_keys: set[str]
) -> None:
    _validate_overviews(collections["overviews"], prefix)
    _validate_macros(collections["macros"], prefix, leaf_keys, collections["tag_set"])
    _validate_checklists(collections["checklists"], prefix)
    _validate_automation(collections["triggers"], "trigger", prefix, collections["tag_set"])
    _validate_automation(collections["jobs"], "job", prefix, collections["tag_set"])
    _validate_reports(collections["reports"], prefix)


def _validate_profile_resources(
    bundle: dict[str, Any],
    manifest: dict[str, Any],
    prefix: str,
    namespace: str,
    leaf_keys: set[str],
) -> dict[str, Any]:
    organizations = _validate_organizations(manifest.get("organizations"), prefix)
    roles = _validate_roles(manifest.get("roles"), prefix, leaf_keys)
    users = manifest.get("users")
    agents, customers = _validate_users(users, roles, organizations)
    _validate_identity(bundle.get("identity"), users, bundle["profile_key"])
    resources = _manifest_collections(manifest, namespace)
    _validate_collection_contracts(resources, prefix, leaf_keys)
    ticket_options = _validate_object_manager(
        manifest.get("object_manager"),
        bundle.get("presentation"),
        namespace,
        prefix,
    )
    scenarios, seed_keys = _validate_uat(
        bundle.get("uat"),
        manifest.get("uat"),
        leaf_keys,
        agents,
        customers,
        resources["tag_set"],
        resources["jobs"],
        ticket_options,
    )
    resources.update(
        {
            "agents": agents,
            "customers": customers,
            "organizations": organizations,
            "roles": roles,
            "scenarios": scenarios,
            "seed_keys": seed_keys,
        }
    )
    return resources


def validate_loaded_profile(loaded: dict[str, Any]) -> dict[str, Any]:
    """Validate one already-loaded profile/manifest snapshot."""
    bundle = loaded["profile"]
    manifest = loaded["manifest"]
    schema_version = _validate_profile_structure(bundle, manifest)
    _validate_profile_metadata(bundle, manifest)
    prefix, namespace = _validate_profile_namespace(manifest)
    _validate_safety_contract(manifest)
    groups, leaf_keys, restricted = _validate_groups(
        manifest.get("groups"), prefix, schema_version
    )
    _validate_reference_sets(manifest.get("reference_sets"), restricted)
    resources = _validate_profile_resources(
        bundle, manifest, prefix, namespace, leaf_keys
    )

    object_manager = manifest["object_manager"]
    field_count = sum(len(object_manager[name]) for name in FIELD_COLLECTIONS)
    counts = {
        "access_matrix_checks": len(resources["agents"]) * len(resources["seed_keys"]),
        "agents": len(resources["agents"]),
        "checklist_templates": len(resources["checklists"]),
        "containers": len(groups) - len(leaf_keys),
        "core_workflows": len(object_manager["core_workflows"]),
        "customers": len(resources["customers"]),
        "groups": len(groups),
        "jobs": len(resources["jobs"]),
        "leaf_groups": len(leaf_keys),
        "macros": len(resources["macros"]),
        "object_manager_fields": field_count,
        "organizations": len(resources["organizations"]),
        "overviews": len(resources["overviews"]),
        "report_profiles": len(resources["reports"]),
        "roles": len(resources["roles"]),
        "tags": len(resources["tags"]),
        "triggers": len(resources["triggers"]),
        "uat_scenarios": len(resources["scenarios"]),
    }
    return {
        "counts": counts,
        "display_name": bundle["display_name"],
        "manifest_key": manifest["manifest_key"],
        "profile_hash": _canonical_hash(bundle),
        "profile_key": bundle["profile_key"],
        "source_hash": _canonical_hash(manifest),
    }


def validate_profile(profile: str | Path) -> dict[str, Any]:
    """Load and fail closed on one local configuration snapshot."""
    return validate_loaded_profile(load_profile(profile))
