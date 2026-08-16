"""Canonical, deterministic manifest resource inventories."""

from __future__ import annotations

from typing import Any

from .profile_support import FIELD_COLLECTIONS


def manifest_inventory(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Return the resource keys shared by validation summaries and plans."""
    return {
        "checklist_templates": sorted(item["key"] for item in manifest["checklist_templates"]),
        "containers": sorted(
            group["key"] for group in manifest["groups"] if group["kind"] == "container"
        ),
        "core_workflows": sorted(
            item["key"] for item in manifest["object_manager"]["core_workflows"]
        ),
        "groups": sorted(item["key"] for item in manifest["groups"]),
        "jobs": sorted(item["key"] for item in manifest["jobs"]),
        "leaf_groups": sorted(
            group["key"] for group in manifest["groups"] if group["kind"] == "leaf"
        ),
        "macros": sorted(item["key"] for item in manifest["macros"]),
        "object_manager_fields": sorted(
            field["name"]
            for collection in FIELD_COLLECTIONS
            for field in manifest["object_manager"][collection]
        ),
        "organizations": sorted(item["key"] for item in manifest["organizations"]),
        "overviews": sorted(item["key"] for item in manifest["overviews"]),
        "report_profiles": sorted(item["key"] for item in manifest["report_profiles"]),
        "roles": sorted(item["key"] for item in manifest["roles"]),
        "tags": sorted(manifest["tags"]),
        "triggers": sorted(item["key"] for item in manifest["triggers"]),
    }
