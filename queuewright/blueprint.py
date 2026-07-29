"""Offline Studio V2 blueprint migration and deterministic graph compilation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .compiler import compile_loaded_profile
from .errors import ConfigurationError
from .profile import validate_loaded_profile
from .studio_project import StudioContractError, validate_studio_state


PROJECT_SCHEMA_VERSION = "2.0"
V1_PROJECT_SCHEMA_VERSION = "1.0"
PROJECT_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
V2_FIELDS = {"project_schema_version", "id", "name", "target_schema_version", "workbook", "extensions", "bundle"}
WORKBOOK_FIELDS = {"organization", "services", "policies", "capability_decisions", "uat"}
BUNDLE_FIELDS = {"profile", "manifest", "resource_ownership", "feature_state"}
V1_FIELDS = {"project_schema_version", "id", "name", "target_schema_version", *BUNDLE_FIELDS}
SENSITIVE_WORDS = {"authorization", "cookie", "credential", "credentials", "env", "password", "secret", "session", "token"}
COMPLETIONS = {"decision_required", "ready", "applied", "verified", "blocked"}
DELIVERIES = {"automated", "guided_manual", "verify_only", "unsupported"}
RISKS = {"low", "medium", "high", "critical"}
CATALOG_PATH = Path(__file__).resolve().parents[1] / "studio" / "catalog" / "capabilities.json"
FEATURE_CATALOG_PATH = Path(__file__).resolve().parents[1] / "studio" / "catalog" / "features.json"
RESOURCE_CAPABILITIES = {
    "agents": "uat-evidence",
    "checklist_templates": "overviews-macros-templates-text-modules-checklists",
    "core_workflows": "fields-core-workflows",
    "customers": "uat-evidence",
    "groups": "service-topology",
    "jobs": "triggers-schedulers-report-profiles",
    "macros": "overviews-macros-templates-text-modules-checklists",
    "object_manager_fields": "fields-core-workflows",
    "organizations": "organizations-customers",
    "overviews": "overviews-macros-templates-text-modules-checklists",
    "report_profiles": "triggers-schedulers-report-profiles",
    "roles": "roles-acl",
    "tags": "tags",
    "triggers": "triggers-schedulers-report-profiles",
    "uat_scenarios": "uat-evidence",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fail(message: str) -> None:
    raise ConfigurationError(message)


def _key_parts(key: str) -> set[str]:
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return set(re.findall(r"[a-z0-9]+", key.lower()))


def _safe_scalar(value: Any, path: str) -> bool:
    if value is None or value.__class__ in {bool, int}:
        return True
    if value.__class__ is float:
        if value == value and value not in (float("inf"), -float("inf")):
            return True
        _fail(f"{path} must contain finite JSON numbers")
    if isinstance(value, str):
        if "://" in value:
            _fail(f"{path} must not contain URLs")
        return True
    return False


def _safe_mapping(value: dict[Any, Any], path: str) -> None:
    for key, child in value.items():
        if not isinstance(key, str):
            _fail(f"{path} object keys must be strings")
        parts = _key_parts(key)
        if parts & SENSITIVE_WORDS or {"api", "key"} <= parts or {"private", "key"} <= parts:
            _fail(f"{path}.{key} has a forbidden sensitive key name")
        _safe(child, f"{path}.{key}")


def _safe(value: Any, path: str) -> None:
    if _safe_scalar(value, path):
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _safe(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        _safe_mapping(value, path)
        return
    _fail(f"{path} must contain only JSON values")


def _read_capability_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"cannot read capability registry: {error}")
    if not isinstance(catalog, dict) or set(catalog) != {"capabilities"} or not isinstance(catalog["capabilities"], list):
        _fail("capability registry must contain exactly a capabilities list")
    return catalog["capabilities"]


def _capability_id(capability: Any, index: int, ids: set[str]) -> str:
    expected = {"id", "domain", "delivery", "default_completion", "risk", "dependencies"}
    if not isinstance(capability, dict) or set(capability) != expected:
        _fail(f"capability registry entry {index} has an invalid shape")
    capability_id = capability.get("id")
    if not isinstance(capability_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", capability_id) or capability_id in ids:
        _fail(f"capability registry entry {index} has an invalid id")
    return capability_id


def _validate_capability_metadata(capability: dict[str, Any], capability_id: str) -> None:
    if not isinstance(capability["domain"], str) or not capability["domain"]:
        _fail(f"capability registry entry {capability_id} has an invalid domain")
    if capability["delivery"] not in DELIVERIES or capability["default_completion"] not in COMPLETIONS or capability["risk"] not in RISKS:
        _fail(f"capability registry entry {capability_id} has invalid metadata")

def _validate_capability_dependencies(capability: dict[str, Any], capability_id: str) -> None:
    if not isinstance(capability["dependencies"], list) or not all(isinstance(item, str) for item in capability["dependencies"]) or len(capability["dependencies"]) != len(set(capability["dependencies"])):
        _fail(f"capability registry entry {capability_id} has invalid dependencies")
    if capability_id in capability["dependencies"]:
        _fail(f"capability registry entry {capability_id} depends on itself")
    if capability["delivery"] == "unsupported" and capability["default_completion"] != "blocked":
        _fail(f"unsupported capability {capability_id} must default to blocked")


def _validate_capability(capability: Any, index: int, ids: set[str]) -> None:
    capability_id = _capability_id(capability, index, ids)
    _validate_capability_metadata(capability, capability_id)
    _validate_capability_dependencies(capability, capability_id)
    ids.add(capability_id)


def load_capabilities(path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    """Load and validate the static, offline Cloud capability registry."""
    capabilities = _read_capability_catalog(path)
    ids: set[str] = set()
    for index, capability in enumerate(capabilities):
        _validate_capability(capability, index, ids)
    _validate_capability_dependencies_graph(capabilities, ids)
    return sorted(copy.deepcopy(capabilities), key=lambda item: item["id"])


def _validate_capability_dependencies_graph(capabilities: list[dict[str, Any]], ids: set[str]) -> None:
    _validate_known_capability_dependencies(capabilities, ids)
    _validate_capability_dependency_cycles(capabilities)


def _validate_known_capability_dependencies(capabilities: list[dict[str, Any]], ids: set[str]) -> None:
    for capability in capabilities:
        unknown = set(capability["dependencies"]) - ids
        if unknown:
            _fail(f"capability registry entry {capability['id']} has unknown dependency: {sorted(unknown)[0]}")


def _validate_capability_dependency_cycles(capabilities: list[dict[str, Any]]) -> None:
    remaining = {
        capability["id"]: set(capability["dependencies"])
        for capability in capabilities
    }
    complete: set[str] = set()
    while remaining:
        ready = sorted(
            capability_id
            for capability_id, dependencies in remaining.items()
            if dependencies <= complete
        )
        if not ready:
            _fail(
                "capability registry dependencies contain a cycle: "
                f"{sorted(remaining)[0]}"
            )
        for capability_id in ready:
            complete.add(capability_id)
            del remaining[capability_id]


def _load_feature_catalog(path: Path = FEATURE_CATALOG_PATH) -> list[dict[str, Any]]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"cannot read feature registry: {error}")
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema_version", "features"}
        or catalog.get("schema_version") != "1.0"
        or not isinstance(catalog.get("features"), list)
    ):
        _fail("feature registry has an invalid shape")
    return copy.deepcopy(catalog["features"])


def _validate_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_FIELDS:
        _fail("bundle must contain exactly profile, manifest, resource_ownership, and feature_state")
    _validate_bundle_profile(bundle)
    ownership, feature_state = _validate_bundle_studio_state(bundle)
    bundle = copy.deepcopy(bundle)
    bundle["resource_ownership"] = ownership
    bundle["feature_state"] = feature_state
    return copy.deepcopy(bundle)


def _validate_bundle_profile(bundle: dict[str, Any]) -> None:
    if not isinstance(bundle["profile"], dict) or not isinstance(bundle["manifest"], dict):
        _fail("bundle profile and manifest must be objects")
    try:
        validate_loaded_profile({"profile": bundle["profile"], "manifest": bundle["manifest"]})
    except (KeyError, TypeError, ConfigurationError) as error:
        _fail(str(error))


def _validate_bundle_studio_state(bundle: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    if not isinstance(bundle["resource_ownership"], dict) or not isinstance(bundle["feature_state"], dict):
        _fail("bundle resource_ownership and feature_state must be objects")
    try:
        ownership, feature_state = validate_studio_state(
            bundle["profile"],
            bundle["manifest"],
            bundle["resource_ownership"],
            bundle["feature_state"],
            _load_feature_catalog(),
        )
    except StudioContractError as error:
        _fail(f"{error.path}: {error.message}")
    return ownership, feature_state


def _validate_header(project: dict[str, Any], version: str) -> None:
    if project.get("project_schema_version") != version:
        _fail(f"project_schema_version must be {version}")
    for field in ("id", "name", "target_schema_version"):
        if not isinstance(project.get(field), str) or not project[field].strip():
            _fail(f"{field} must be a non-empty string")
    if PROJECT_ID.fullmatch(project["id"]) is None:
        _fail("id must be a lowercase safe project key")


def _workflow_entry_groups(workflow: dict[str, Any], group_keys: set[str]) -> set[str]:
    match = workflow.get("match")
    if not isinstance(match, str):
        return set()
    parsed = re.fullmatch(r"^authenticated customer and group in \[([a-z0-9_, -]+)\]$", match)
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


def _derived_services(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = bundle["manifest"]
    profile = bundle["profile"]
    entry_points = _customer_entry_points(manifest)
    roles_by_key = {role["key"]: role for role in manifest["roles"]}

    def role_access(group_key: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for role in manifest["roles"]:
            level = next(
                (
                    permission
                    for permission in (
                        "full",
                        "change",
                        "create",
                        "read_change_overview",
                        "read",
                        "overview",
                    )
                    if group_key in role["acl"].get(permission, [])
                ),
                None,
            )
            if level:
                result.append({"role": role["key"], "permission": level})
        return sorted(result, key=lambda item: item["role"])

    return [
        {
            "key": group["key"],
            "name": group["name"],
            "kind": group["kind"],
            "parent": group.get("parent"),
            "service_code": group.get("service_code"),
            "restricted": group.get("restricted", False),
            "customer_entry_point": group["key"] in entry_points,
            "role_access": role_access(group["key"]),
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


def _derived_policies(bundle: dict[str, Any]) -> dict[str, Any]:
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


def _capability_enabled(capability_id: str, bundle: dict[str, Any]) -> bool:
    manifest = bundle["manifest"]
    mapping = {
        "organization": bool(bundle["name"]), "service-topology": bool(manifest["groups"]),
        "organizations-customers": bool(manifest["organizations"] or manifest["users"]["customers"]),
        "roles-acl": bool(manifest["roles"]), "fields-core-workflows": bool(manifest["object_manager"]["core_workflows"] or any(manifest["object_manager"][field] for field in ("ticket_fields", "user_fields", "organization_fields", "group_fields"))),
        "tags": bool(manifest["tags"]), "overviews-macros-templates-text-modules-checklists": bool(manifest["overviews"] or manifest["macros"] or manifest["checklist_templates"]),
        "triggers-schedulers-report-profiles": bool(manifest["triggers"] or manifest["jobs"] or manifest["report_profiles"]),
        "uat-evidence": bool(bundle["profile"]["uat"]["scenarios"]),
    }
    return mapping.get(capability_id, False)


def _decision_state(capability: dict[str, Any], current: Any, bundle: dict[str, Any]) -> tuple[bool, str]:
    current = current if isinstance(current, dict) else {}
    enabled = current.get("enabled", _capability_enabled(capability["id"], bundle))
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


def _decisions(bundle: dict[str, Any], previous: Any = None) -> dict[str, dict[str, Any]]:
    existing = previous if isinstance(previous, dict) else {}
    decisions: dict[str, dict[str, Any]] = {}
    for capability in load_capabilities():
        enabled, completion = _decision_state(capability, existing.get(capability["id"]), bundle)
        decisions[capability["id"]] = {"completion": completion, "delivery": capability["delivery"], "risk": capability["risk"], "dependencies": capability["dependencies"], "enabled": enabled}
    return decisions


def _validate_workbook_decisions(decisions: Any, bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected = {item["id"] for item in load_capabilities()}
    if not isinstance(decisions, dict) or set(decisions) != expected:
        _fail("workbook.capability_decisions must define every capability exactly")
    normalized = _decisions(bundle, decisions)
    _validate_decision_entries(decisions, normalized)
    _validate_enabled_decision_dependencies(normalized)
    return normalized


def _validate_decision_entries(decisions: dict[str, dict[str, Any]], normalized: dict[str, dict[str, Any]]) -> None:
    for capability_id, decision in decisions.items():
        if not isinstance(decision, dict) or set(decision) != {"completion", "delivery", "risk", "dependencies", "enabled"}:
            _fail(f"workbook.capability_decisions.{capability_id} has an invalid shape")
        if decision["completion"] not in COMPLETIONS or decision["enabled"].__class__ is not bool:
            _fail(f"workbook.capability_decisions.{capability_id} has invalid editable values")
        if decision["completion"] in {"applied", "verified"}:
            _fail(f"workbook.capability_decisions.{capability_id} cannot claim applied or verified in an offline project")
        if decision != normalized[capability_id]:
            _fail(f"workbook.capability_decisions.{capability_id} must use registry delivery, risk, and dependencies")


def _validate_enabled_decision_dependencies(normalized: dict[str, dict[str, Any]]) -> None:
    for capability_id, decision in normalized.items():
        if not decision["enabled"]:
            continue
        missing = [dependency for dependency in decision["dependencies"] if not normalized[dependency]["enabled"]]
        if missing:
            _fail(f"workbook.capability_decisions.{capability_id} requires enabled dependency {missing[0]}")


def _derived_workbook_sections(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    return _derived_services(bundle), _derived_policies(bundle), copy.deepcopy(bundle["profile"]["uat"])


def _validate_derived_workbook_sections(workbook: dict[str, Any], sections: tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]) -> None:
    services, policies, uat = sections
    if workbook["services"] != services:
        _fail("workbook.services is compiler-derived and must match bundle.manifest")
    if workbook["policies"] != policies:
        _fail("workbook.policies is compiler-derived and must match bundle.manifest")
    if workbook["uat"] != uat:
        _fail("workbook.uat is compiler-derived and must match bundle.profile")


def _validate_workbook(workbook: Any, bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(workbook, dict) or set(workbook) != WORKBOOK_FIELDS:
        _fail("workbook must contain exactly organization, services, policies, capability_decisions, and uat")
    if not isinstance(workbook["organization"], dict):
        _fail("workbook.organization must be an object")
    _safe(workbook["organization"], "workbook.organization")
    normalized = _validate_workbook_decisions(workbook["capability_decisions"], bundle)
    if not isinstance(workbook["services"], list) or not isinstance(workbook["policies"], dict) or not isinstance(workbook["uat"], dict):
        _fail("workbook services, policies, and uat have invalid shapes")
    _safe(workbook["services"], "workbook.services")
    _safe(workbook["policies"], "workbook.policies")
    _safe(workbook["uat"], "workbook.uat")
    derived_services, derived_policies, derived_uat = _derived_workbook_sections(bundle)
    _validate_derived_workbook_sections(workbook, (derived_services, derived_policies, derived_uat))
    return {
        "organization": copy.deepcopy(workbook["organization"]),
        "services": derived_services,
        "policies": derived_policies,
        "capability_decisions": normalized,
        "uat": derived_uat,
    }


def validate_v2_project(project: Any) -> dict[str, Any]:
    if not isinstance(project, dict) or set(project) != V2_FIELDS:
        _fail("project must contain exactly project_schema_version, id, name, target_schema_version, workbook, extensions, and bundle")
    _validate_header(project, PROJECT_SCHEMA_VERSION)
    bundle = _validate_bundle(project["bundle"])
    if project["target_schema_version"] != bundle["profile"]["schema_version"] or project["target_schema_version"] != bundle["manifest"]["schema_version"]:
        _fail("project metadata must match its profile and manifest")
    if not isinstance(project["extensions"], dict):
        _fail("extensions must be an object")
    _safe(project["extensions"], "extensions")
    workbook = _validate_workbook(project["workbook"], {**bundle, "name": project["name"]})
    return {"project_schema_version": PROJECT_SCHEMA_VERSION, "id": project["id"], "name": project["name"], "target_schema_version": project["target_schema_version"], "workbook": workbook, "extensions": copy.deepcopy(project["extensions"]), "bundle": bundle}


def migrate_v1_project(project: Any) -> dict[str, Any]:
    """Losslessly wrap an already-valid V1 Studio project in the V2 contract."""
    if not isinstance(project, dict) or set(project) != V1_FIELDS:
        _fail("V1 project must contain exactly the canonical V1 project fields")
    _validate_header(project, V1_PROJECT_SCHEMA_VERSION)
    bundle = _validate_bundle({field: project[field] for field in BUNDLE_FIELDS})
    if project["target_schema_version"] != bundle["profile"]["schema_version"] or project["target_schema_version"] != bundle["manifest"]["schema_version"]:
        _fail("project metadata must match its profile and manifest")
    enriched = {**bundle, "name": project["name"]}
    return {"project_schema_version": PROJECT_SCHEMA_VERSION, "id": project["id"], "name": project["name"], "target_schema_version": project["target_schema_version"], "workbook": {"organization": {"name": project["name"]}, "services": _derived_services(bundle), "policies": _derived_policies(bundle), "capability_decisions": _decisions(enriched), "uat": copy.deepcopy(bundle["profile"]["uat"])}, "extensions": {}, "bundle": bundle}


def _capability_nodes(decisions: dict[str, dict[str, Any]], owner: Any) -> list[dict[str, Any]]:
    if not isinstance(owner, str) or not owner:
        owner = "unassigned"
    return [
        {
            "id": f"capability:{capability_id}",
            "resource_kind": "capability_gate",
            "logical_key": capability_id,
            "desired": {
                "enabled": decision["enabled"],
                "completion": decision["completion"],
            },
            "dependencies": [
                f"capability:{dependency}"
                for dependency in decision["dependencies"]
            ],
            "delivery": decision["delivery"],
            "risk": decision["risk"],
            "owner": owner,
            "verification": {
                "mode": "decision_evidence",
                "required": decision["enabled"],
            },
            "rollback": {
                "strategy": "no_tenant_mutation",
                "destructive": False,
            },
        }
        for capability_id, decision in sorted(decisions.items())
    ]

def _operation_nodes(plan: dict[str, Any], bundle: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for operation in plan["operations"]:
        owner = bundle["resource_ownership"].get(operation["id"], "core")
        capability = RESOURCE_CAPABILITIES.get(operation["resource"])
        if capability is None:
            _fail(
                "configuration graph has no capability mapping for resource "
                f"{operation['resource']}"
            )
        decision = decisions[capability]
        if not decision["enabled"]:
            _fail(
                f"configuration graph requires enabled capability {capability} "
                f"for operation {operation['id']}"
            )
        automated = decision["delivery"] == "automated"
        rollback_strategy = (
            "retain_and_review"
            if operation["action"] == "ensure_present"
            else "deactivate_created_resource"
            if automated
            else "manual_recovery_plan"
        )
        nodes.append(
            {
                "id": operation["id"],
                "resource_kind": operation["resource"],
                "logical_key": operation["key"],
                "desired": operation["desired_state"],
                "dependencies": [
                    f"capability:{capability}",
                    *operation["depends_on"],
                ],
                "delivery": decision["delivery"],
                "risk": decision["risk"],
                "owner": owner,
                "verification": {
                    "mode": "compiled_postcondition" if automated else "guided_evidence",
                    "desired_hash": _hash(operation["desired_state"]),
                },
                "rollback": {
                    "strategy": rollback_strategy,
                    "destructive": False,
                },
            }
        )
    return nodes


def _compiled_v2_response(normalized: dict[str, Any], bundle: dict[str, Any], plan: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    graph = {"nodes": nodes}
    graph["graph_hash"] = _hash(graph)
    return {"project": normalized, "bundle": copy.deepcopy(bundle), "plan": plan, "graph": graph, "hashes": {"profile": plan["source_hashes"]["profile"], "manifest": plan["source_hashes"]["manifest"], "plan": plan["plan_hash"], "project": _hash(normalized), "graph": graph["graph_hash"]}}


def compile_v2_project(project: Any) -> dict[str, Any]:
    """Validate V2 and compile its unchanged V1 bundle plus an inert graph."""
    normalized = validate_v2_project(project)
    bundle = normalized["bundle"]
    plan = compile_loaded_profile({"profile": bundle["profile"], "manifest": bundle["manifest"]})
    decisions = normalized["workbook"]["capability_decisions"]
    nodes = _capability_nodes(decisions, normalized["workbook"]["organization"].get("service_owner_role", "unassigned"))
    nodes.extend(_operation_nodes(plan, bundle, decisions))
    return _compiled_v2_response(normalized, bundle, plan, nodes)
