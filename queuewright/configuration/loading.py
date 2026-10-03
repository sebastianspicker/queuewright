"""Strict, local-only profile and manifest loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts.safety import SafeJsonError, validate_json_depth
from .rules import _fail

SENSITIVE_FILENAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "token",
    "token_full",
}
SENSITIVE_SUFFIXES = (".key", ".p12", ".pem", ".pfx", ".secrets.json")


def _is_relative_json_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and Path(value).suffix.lower() == ".json"
    )


def _profile_path(profile: str | Path) -> Path:
    supplied = Path(profile)
    profile_path = (supplied / "profile.json" if supplied.is_dir() else supplied).resolve()
    if profile_path.suffix.lower() != ".json" or _sensitive_path(profile_path):
        _fail("profile path must be a non-sensitive JSON file")
    return profile_path


def _manifest_name(bundle: dict[str, Any]) -> str:
    manifest_name = bundle.get("manifest")
    if not _is_relative_json_path(manifest_name):
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


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        _fail(f"cannot read JSON {path}: {error}")
    if not isinstance(value, dict):
        _fail(f"JSON object required: {path}")
    try:
        validate_json_depth(value, str(path))
    except SafeJsonError as error:
        _fail(f"cannot read JSON {path}: {error.message}")
    return value


def _repo_root(path: Path) -> Path | None:
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return None


def _sensitive_path(path: Path) -> bool:
    for part in path.parts:
        lowered = part.lower()
        if (
            lowered == ".local"
            or lowered in SENSITIVE_FILENAMES
            or lowered.startswith(".env.")
            or lowered.endswith(SENSITIVE_SUFFIXES)
        ):
            return True
    return False


def is_forbidden_local_path(path: str | Path) -> bool:
    """Return whether a path crosses the package's no-secret/no-run-data fence."""
    return _sensitive_path(Path(path).resolve())
