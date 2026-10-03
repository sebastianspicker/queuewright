"""The canonical Blueprint V2 model: workbook derivation, decisions, validation, migration."""

from __future__ import annotations

import copy
import re
from typing import Any, NamedTuple

from ..configuration import FIELD_COLLECTIONS
from ..contracts.safety import SafeJsonError, validate_safe_json
from .bundle import (
    BUNDLE_FIELDS,
    PROJECT_FIELDS,
    header_violation,
    require_matching_versions,
    validate_bundle,
)
from .errors import ProjectError
from .registry import COMPLETIONS, load_capabilities, load_features
from .state import normalize_draft_state, validate_studio_state
from .v1 import PROJECT_SCHEMA_VERSION as V1_PROJECT_SCHEMA_VERSION
from .v1 import V1Snapshot

PROJECT_SCHEMA_VERSION = "2.0"
V2_FIELDS = {
    "project_schema_version", "id", "name", "target_schema_version", "workbook", "extensions",
    "bundle",
}
WORKBOOK_FIELDS = {"organization", "services", "policies", "capability_decisions", "uat"}
EDITABLE_WORKBOOK_FIELDS = {"organization", "capability_decisions"}
DECISION_FIELDS = {"completion", "delivery", "risk", "dependencies", "enabled"}
EDITABLE_DECISION_FIELDS = {"completion", "enabled"}
ROLE_PERMISSIONS = ("full", "change", "create", "read_change_overview", "read", "overview")
CUSTOMER_ENTRY_MATCH = re.compile(r"^authenticated customer and group in \[([a-z0-9_, -]+)\]$")


class ValidatedV2Project(NamedTuple):
    """A normalized V2 project with the summary of its validated bundle."""

    project: dict[str, Any]
    profile_summary: dict[str, Any]


def _safe(value: Any, path: str) -> None:
    try:
        validate_safe_json(value, path)
    except SafeJsonError as error:
        raise ProjectError(f"{error.path} {error.message}") from error


def _validate_header(project: dict[str, Any], version: str) -> None:
    violation = header_violation(project, version)
    if violation is None:
        return
    field, rule = violation
    if rule == "version":
        raise ProjectError(f"project_schema_version must be {version}")
    if rule == "text":
        raise ProjectError(f"{field} must be a non-empty string")
    raise ProjectError("id must be a lowercase safe project key")


def _validate_bundle(
    bundle: Any,
    features: list[dict[str, Any]],
    *,
    normalize_studio_state: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_FIELDS:
        raise ProjectError(
            "bundle must contain exactly profile, manifest, resource_ownership, and feature_state"
        )
    profile, manifest = bundle["profile"], bundle["manifest"]
    if not isinstance(profile, dict) or not isinstance(manifest, dict):
        raise ProjectError("bundle profile and manifest must be objects")
    summary = validate_bundle({"profile": profile, "manifest": manifest})
    if normalize_studio_state:
        validate_state = normalize_draft_state
    else:
        if not isinstance(bundle["resource_ownership"], dict) or not isinstance(
            bundle["feature_state"], dict
        ):
            raise ProjectError("bundle resource_ownership and feature_state must be objects")
        validate_state = validate_studio_state
    ownership, feature_state = validate_state(
        profile, manifest, bundle["resource_ownership"], bundle["feature_state"], features
    )
    return {
        "profile": copy.deepcopy(profile),
        "manifest": copy.deepcopy(manifest),
        "resource_ownership": ownership,
        "feature_state": feature_state,
    }, summary


def _workflow_entry_groups(workflow: dict[str, Any], group_keys: set[str]) -> set[str]:
    match = workflow.get("match")
    if not isinstance(match, str):
        return set()
    parsed = CUSTOMER_ENTRY_MATCH.fullmatch(match)
    if parsed is None:
        return set()
    return {item.strip() for item in parsed.group(1).split(",") if item.strip() in group_keys}


def _customer_entry_points(manifest: dict[str, Any]) -> set[str]:
    group_keys = {group["key"] for group in manifest["groups"]}
    entry_points: set[str] = set()
    workflows = (
        workflow for workflow in manifest["object_manager"]["core_workflows"]
        if workflow.get("context") == "customer_create"
    )
    for workflow in workflows:
        entry_points.update(_workflow_entry_groups(workflow, group_keys))
    return entry_points


def _role_access(manifest: dict[str, Any], group_key: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for role in manifest["roles"]:
        level = next(
            (
                permission
                for permission in ROLE_PERMISSIONS
                if group_key in role["acl"].get(permission, [])
            ),
            None,
        )
        if level:
            result.append({"role": role["key"], "permission": level})
    return sorted(result, key=lambda item: item["role"])


def derived_services(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the service workbook section from a validated bundle."""
    manifest = bundle["manifest"]
    profile = bundle["profile"]
    entry_points = _customer_entry_points(manifest)
    roles_by_key = {role["key"]: role for role in manifest["roles"]}
    return [
        {
            "key": group["key"],
            "name": group["name"],
            "kind": group["kind"],
            "parent": group.get("parent"),
            "service_code": group.get("service_code"),
            "restricted": group.get("restricted", False),
            "customer_entry_point": group["key"] in entry_points,
            "role_access": _role_access(manifest, group["key"]),
            "synthetic_agents": sorted(
                agent["key"]
                for agent in manifest["users"]["agents"]
                if any(
                    group["key"] in group_acl
                    for group_acl in roles_by_key[agent["role"]]["acl"].values()
                )
            ),
            "uat_scenarios": sorted(
                scenario["key"]
                for scenario in profile["uat"]["scenarios"]
                if scenario["group"] == group["key"]
            ),
        }
        for group in manifest["groups"]
    ]


def derived_policies(bundle: dict[str, Any]) -> dict[str, Any]:
    """Derive the policy workbook section from a validated bundle."""
    manifest = bundle["manifest"]
    return {
        "safety_contract": copy.deepcopy(manifest["safety_contract"]),
        "offline_only": bundle["profile"]["offline_only"],
        "managed_prefix": manifest["managed_prefix"],
        "technical_namespace": manifest["technical_namespace"],
        "feature_selection": {
            feature_id: state["enabled"]
            for feature_id, state in sorted(bundle["feature_state"].items())
        },
        "role_access": {
            role["key"]: copy.deepcopy(role["acl"])
            for role in manifest["roles"]
        },
    }


def _capability_enabled(capability_id: str, bundle: dict[str, Any], name: str) -> bool:
    manifest = bundle["manifest"]
    object_manager = manifest["object_manager"]
    mapping = {
        "organization": bool(name),
        "service-topology": bool(manifest["groups"]),
        "organizations-customers": bool(
            manifest["organizations"] or manifest["users"]["customers"]
        ),
        "roles-acl": bool(manifest["roles"]),
        "fields-core-workflows": bool(
            object_manager["core_workflows"]
            or any(object_manager[collection] for collection in FIELD_COLLECTIONS)
        ),
        "tags": bool(manifest["tags"]),
        "overviews-macros-templates-text-modules-checklists": bool(
            manifest["overviews"] or manifest["macros"] or manifest["checklist_templates"]
        ),
        "triggers-schedulers-report-profiles": bool(
            manifest["triggers"] or manifest["jobs"] or manifest["report_profiles"]
        ),
        "uat-evidence": bool(bundle["profile"]["uat"]["scenarios"]),
    }
    return mapping.get(capability_id, False)


def _decision_state(
    capability: dict[str, Any], current: Any, bundle: dict[str, Any], name: str
) -> tuple[bool, str]:
    current = current if isinstance(current, dict) else {}
    enabled = current.get("enabled", _capability_enabled(capability["id"], bundle, name))
    completion = current.get("completion")
    if capability["delivery"] == "unsupported":
        enabled = False
        completion = "blocked"
    elif not enabled:
        completion = "decision_required"
    elif completion not in COMPLETIONS:
        completion = (
            "ready"
            if capability["delivery"] == "automated" and enabled
            else capability["default_completion"]
        )
    return enabled, completion


def decisions(
    bundle: dict[str, Any],
    name: str,
    capabilities: list[dict[str, Any]],
    previous: Any = None,
) -> dict[str, dict[str, Any]]:
    """Materialize one capability decision per registry entry for a bundle."""
    existing = previous if isinstance(previous, dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for capability in capabilities:
        enabled, completion = _decision_state(
            capability, existing.get(capability["id"]), bundle, name
        )
        result[capability["id"]] = {
            "completion": completion,
            "delivery": capability["delivery"],
            "risk": capability["risk"],
            "dependencies": list(capability["dependencies"]),
            "enabled": enabled,
        }
    return result


def _validate_workbook_decisions(
    previous: Any,
    bundle: dict[str, Any],
    name: str,
    capabilities: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    expected = {item["id"] for item in capabilities}
    if not isinstance(previous, dict) or set(previous) != expected:
        raise ProjectError("workbook.capability_decisions must define every capability exactly")
    _validate_decision_entries(previous)
    normalized = decisions(bundle, name, capabilities, previous)
    require_enabled_decision_dependencies(normalized)
    return normalized


def _validate_decision_entries(previous: dict[str, Any]) -> None:
    for capability_id, decision in previous.items():
        path = f"workbook.capability_decisions.{capability_id}"
        if (
            not isinstance(decision, dict)
            or not EDITABLE_DECISION_FIELDS <= set(decision)
            or set(decision) - DECISION_FIELDS
        ):
            raise ProjectError(f"{path} has an invalid shape")
        if decision["completion"] not in COMPLETIONS or decision["enabled"].__class__ is not bool:
            raise ProjectError(f"{path} has invalid editable values")
        if decision["completion"] in {"applied", "verified"}:
            raise ProjectError(f"{path} cannot claim applied or verified in an offline project")


def require_enabled_decision_dependencies(normalized: dict[str, dict[str, Any]]) -> None:
    """Reject enabled capability decisions whose dependencies are disabled."""
    for capability_id, decision in normalized.items():
        if not decision["enabled"]:
            continue
        missing = [
            dependency
            for dependency in decision["dependencies"]
            if not normalized[dependency]["enabled"]
        ]
        if missing:
            raise ProjectError(
                f"workbook.capability_decisions.{capability_id} requires enabled dependency "
                f"{missing[0]}"
            )


def _validate_tolerated_derived_workbook_sections(workbook: dict[str, Any]) -> None:
    """Keep optional exported mirrors safe while treating them as non-input."""
    shapes = {"services": list, "policies": dict, "uat": dict}
    for field, expected_type in shapes.items():
        if field not in workbook:
            continue
        if not isinstance(workbook[field], expected_type):
            raise ProjectError(f"workbook.{field} has an invalid compiler-derived shape")
        _safe(workbook[field], f"workbook.{field}")


def _validate_workbook(
    workbook: Any,
    bundle: dict[str, Any],
    name: str,
    capabilities: list[dict[str, Any]],
) -> dict[str, Any]:
    if (
        not isinstance(workbook, dict)
        or not EDITABLE_WORKBOOK_FIELDS <= set(workbook)
        or set(workbook) - WORKBOOK_FIELDS
    ):
        raise ProjectError(
            "workbook must contain organization and capability_decisions "
            "with only known derived fields"
        )
    if not isinstance(workbook["organization"], dict):
        raise ProjectError("workbook.organization must be an object")
    _safe(workbook["organization"], "workbook.organization")
    normalized = _validate_workbook_decisions(
        workbook["capability_decisions"], bundle, name, capabilities
    )
    _validate_tolerated_derived_workbook_sections(workbook)
    return {
        "organization": copy.deepcopy(workbook["organization"]),
        "services": derived_services(bundle),
        "policies": derived_policies(bundle),
        "capability_decisions": normalized,
        "uat": copy.deepcopy(bundle["profile"]["uat"]),
    }


def validate_v2_snapshot(project: Any) -> ValidatedV2Project:
    """Validate V2 draft input and materialize every compiler-owned mirror.

    The bundle, organization workbook section, and decision enabled/completion
    values are authored input. Services, policies, UAT, and registry metadata
    are tolerated when a previously exported project is re-submitted, but are
    deliberately never trusted as input.
    """
    if not isinstance(project, dict) or set(project) != V2_FIELDS:
        raise ProjectError(
            "project must contain exactly project_schema_version, id, name, "
            "target_schema_version, workbook, extensions, and bundle"
        )
    _validate_header(project, PROJECT_SCHEMA_VERSION)
    bundle, summary = _validate_bundle(
        project["bundle"], load_features(), normalize_studio_state=True
    )
    require_matching_versions(
        project["target_schema_version"], bundle["profile"], bundle["manifest"]
    )
    if not isinstance(project["extensions"], dict):
        raise ProjectError("extensions must be an object")
    _safe(project["extensions"], "extensions")
    workbook = _validate_workbook(
        project["workbook"], bundle, project["name"], load_capabilities()
    )
    normalized = {
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "id": project["id"],
        "name": project["name"],
        "target_schema_version": project["target_schema_version"],
        "workbook": workbook,
        "extensions": copy.deepcopy(project["extensions"]),
        "bundle": bundle,
    }
    return ValidatedV2Project(normalized, summary)


def validate_v2_project(project: Any) -> dict[str, Any]:
    """Validate V2 draft input and materialize every compiler-owned mirror.

    The bundle, organization workbook section, and decision enabled/completion
    values are authored input. Services, policies, UAT, and registry metadata
    are tolerated when a previously exported project is re-submitted, but are
    deliberately never trusted as input.
    """
    return validate_v2_snapshot(project).project


def validate_exported_v2_project(project: Any) -> dict[str, Any]:
    """Reject a V2 artifact whose compiler-owned fields are no longer canonical."""
    normalized = validate_v2_project(project)
    if project != normalized:
        raise ProjectError(
            "exported V2 project must match compiler-derived workbook fields and registry metadata"
        )
    return normalized


def migrate_v1_project(project: Any) -> dict[str, Any]:
    """Losslessly wrap an already-valid V1 Studio project in the V2 contract."""
    if not isinstance(project, dict) or set(project) != PROJECT_FIELDS:
        raise ProjectError("V1 project must contain exactly the canonical V1 project fields")
    _validate_header(project, V1_PROJECT_SCHEMA_VERSION)
    bundle, _summary = _validate_bundle(
        {field: project[field] for field in BUNDLE_FIELDS}, load_features()
    )
    require_matching_versions(
        project["target_schema_version"], bundle["profile"], bundle["manifest"]
    )
    return _migrated(project, bundle, load_capabilities())


def migrate_v1_snapshot(snapshot: V1Snapshot) -> dict[str, Any]:
    """Wrap an already validated V1 snapshot in the V2 contract without revalidating."""
    project = snapshot.project
    bundle = {field: project[field] for field in BUNDLE_FIELDS}
    return _migrated(project, bundle, load_capabilities())


def _migrated(
    project: dict[str, Any], bundle: dict[str, Any], capabilities: list[dict[str, Any]]
) -> dict[str, Any]:
    name = project["name"]
    return {
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "id": project["id"],
        "name": name,
        "target_schema_version": project["target_schema_version"],
        "workbook": {
            "organization": {"name": name},
            "services": derived_services(bundle),
            "policies": derived_policies(bundle),
            "capability_decisions": decisions(bundle, name, capabilities),
            "uat": copy.deepcopy(bundle["profile"]["uat"]),
        },
        "extensions": {},
        "bundle": bundle,
    }
