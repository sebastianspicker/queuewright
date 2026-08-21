#!/usr/bin/env python3
"""Dependency-free public-alpha consistency checks for Queuewright."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
STUDIO_CATALOG = ROOT / "studio/catalog/features.json"
STUDIO_CAPABILITY_CATALOG = ROOT / "studio/catalog/capabilities.json"
STUDIO_PACKAGE = ROOT / "studio-ui/package.json"
STUDIO_LOCK = ROOT / "studio-ui/package-lock.json"
STUDIO_HTML = ROOT / "studio-ui/index.html"
STUDIO_API = ROOT / "studio-ui/src/api.ts"
STUDIO_VITE = ROOT / "studio-ui/vite.config.ts"
CONTROL_REQUIREMENTS = ROOT / "requirements-control.txt"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
SKIP_PATHS = {
    Path("AGENTS.md"),
    Path(".git"), Path(".agents"), Path(".claude"), Path(".codex"),
    Path(".cursor"), Path(".impeccable"), Path(".local"), Path(".serena"),
    Path("studio-ui/node_modules"), Path("studio-ui/dist"),
}
PUBLICLY_OBSOLETE_PATHS = {
    Path(".grok"), Path("archive"), Path("docs/agent"),
    Path("docs/archive"), Path("docs/design/mockups"), Path("docs/proposal"),
    Path("docs/ui/concepts"), Path("docs/z2"),
}
STUDIO_FEATURE_IDS = {
    "ticket_fields", "user_classification", "organization_classification",
    "group_classification", "overviews", "macros", "checklists", "triggers",
    "scheduled_reviews", "report_profiles", "cross_department_handoff",
    "sensitive_area_handling", "dummy_users_uat", "access_matrix",
}
STUDIO_CAPABILITY_IDS = {
    "organization", "service-topology", "organizations-customers", "roles-acl",
    "identity-security", "fields-core-workflows", "calendars-sla", "tags",
    "overviews-macros-templates-text-modules-checklists",
    "triggers-schedulers-report-profiles", "channels-postmaster-signatures",
    "webhooks-integrations", "knowledge-base", "time-accounting",
    "privacy-retention", "branding-ticket-settings", "ai", "uat-evidence",
    "platform-dr",
}


def is_sensitive_name(name: str) -> bool:
    lower = name.lower()
    return (
        lower in {"token", "token_full"} or lower.startswith(".env")
        or lower in {"id_rsa", "id_ed25519", "credentials.json"}
        or lower.endswith((".key", ".pem", ".p12", ".pfx", ".secrets.json"))
        or "secret" in lower
    )


def is_forbidden_tracked_path(path: Path) -> bool:
    return any(
        part.lower() != ".env.example" and is_sensitive_name(part)
        for part in path.parts
    ) or path == Path(".local") or Path(".local") in path.parents


def is_safe_path(path: Path) -> bool:
    if (
        "__pycache__" in path.parts
        or any(part.startswith(".aider") for part in path.parts)
        or any(is_sensitive_name(part) for part in path.parts)
    ):
        return False
    return not any(path == prefix or prefix in path.parents for prefix in SKIP_PATHS)


def active_files() -> Iterator[Path]:
    for directory, names, filenames in os.walk(ROOT, topdown=True):
        directory_path = Path(directory)
        names[:] = [
            name for name in names
            if is_safe_path((directory_path / name).relative_to(ROOT))
        ]
        for filename in filenames:
            path = directory_path / filename
            if is_safe_path(path.relative_to(ROOT)):
                yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_command(*arguments: str) -> list[str]:
    if GIT is None:
        raise OSError("git executable is not available")
    return [GIT, *arguments]


def local_link_target(source: Path, destination: str) -> Path | None:
    destination = destination.strip().strip("<>")
    if not destination or destination.startswith(("#", "mailto:", "http://", "https://", "tel:")):
        return None
    destination = destination.split("#", 1)[0].split("?", 1)[0]
    if not destination:
        return None
    target = ROOT / destination.lstrip("/") if destination.startswith("/") else source.parent / destination
    try:
        relative = target.resolve().relative_to(ROOT)
    except ValueError:
        return None
    return target if is_safe_path(relative) else None


def _check_markdown(path: Path, text: str, failures: list[str]) -> None:
    for match in re.finditer(r"\*\*([^*\n]+)\*\*", text):
        content = match.group(1).strip().strip("`")
        if content and not re.search(r"\s", content):
            failures.append(f"single-word bold emphasis remains: {path.relative_to(ROOT)}: {content}")
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        target = local_link_target(path, match.group(1))
        if target is not None and not target.exists():
            failures.append(f"missing local link: {path.relative_to(ROOT)} -> {match.group(1)}")


def _check_json(path: Path, parsed_json: dict[Path, Any], failures: list[str]) -> None:
    try:
        parsed_json[path] = json.loads(read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"JSON parse failed: {path.relative_to(ROOT)}: {error}")


def _check_png(path: Path, failures: list[str]) -> None:
    try:
        if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            failures.append(f"invalid PNG signature: {path.relative_to(ROOT)}")
    except OSError as error:
        failures.append(f"cannot read PNG: {path.relative_to(ROOT)}: {error}")


def _check_file(path: Path, parsed_json: dict[Path, Any], failures: list[str]) -> None:
    suffix = path.suffix.lower()
    text = read_text(path) if suffix in {".html", ".md", ".py", ".ts", ".tsx"} else None
    if text is not None and "\N{EM DASH}" in text:
        failures.append(f"prohibited em dash remains: {path.relative_to(ROOT)}")
    if suffix == ".json":
        _check_json(path, parsed_json, failures)
    elif suffix == ".md" and text is not None:
        _check_markdown(path, text, failures)
    elif suffix == ".png":
        _check_png(path, failures)


def check_files(files: list[Path], failures: list[str]) -> dict[Path, Any]:
    parsed_json: dict[Path, Any] = {}
    for path in files:
        _check_file(path, parsed_json, failures)
    return parsed_json


def check_public_scope(failures: list[str]) -> None:
    for path in sorted(PUBLICLY_OBSOLETE_PATHS):
        if (ROOT / path).exists():
            failures.append(f"obsolete pre-alpha public lane remains: {path}")


def check_git_metadata(failures: list[str]) -> None:
    try:
        tracked = subprocess.run(
            _git_command("ls-files", "-z"), cwd=ROOT, check=True, capture_output=True
        ).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        failures.append(f"cannot inspect tracked filename metadata: {error}")
        return
    for name in filter(None, tracked):
        if is_forbidden_tracked_path(Path(name)):
            failures.append(f"tracked sensitive or excluded path: {name}")


def _check_studio_catalogs(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    catalog = parsed_json.get(STUDIO_CATALOG)
    capabilities = parsed_json.get(STUDIO_CAPABILITY_CATALOG)
    _check_catalog_ids(catalog, "features", STUDIO_FEATURE_IDS, "feature", failures)
    _check_catalog_ids(capabilities, "capabilities", STUDIO_CAPABILITY_IDS, "capability", failures)


def _check_catalog_ids(catalog: Any, field: str, expected: set[str], name: str, failures: list[str]) -> None:
    rows = catalog.get(field) if isinstance(catalog, dict) else None
    if not isinstance(rows, list) or {row.get("id") for row in rows if isinstance(row, dict)} != expected:
        failures.append(f"Studio {name} catalog must define the exact {len(expected)} {name} IDs")


def _check_studio_package(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    package = parsed_json.get(STUDIO_PACKAGE)
    lock = parsed_json.get(STUDIO_LOCK)
    if not isinstance(package, dict) or package.get("version") != "0.1.0-alpha.1":
        failures.append("Studio package version must match alpha candidate 0.1.0-alpha.1")
    if not isinstance(lock, dict):
        failures.append("Studio package-lock.json is required for a reproducible alpha")
    elif lock.get("version") != "0.1.0-alpha.1":
        failures.append("Studio lockfile version must match alpha candidate 0.1.0-alpha.1")
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict) or not {"dev", "build"} <= set(scripts):
        failures.append("Studio package must provide dev and build scripts")


def _check_studio_network_surface(failures: list[str]) -> None:
    html_text = read_text(STUDIO_HTML)
    api_text = read_text(STUDIO_API)
    vite_text = read_text(STUDIO_VITE)
    if re.search(r"(?:src|href)=[\"']https?://", html_text):
        failures.append("Studio HTML must not load remote resources")
    _check_studio_fetch_surface(api_text, failures)
    _check_studio_vite_surface(vite_text, failures)


def _check_studio_fetch_surface(api_text: str, failures: list[str]) -> None:
    fetch_paths = set(re.findall(r"fetch\(['\"]([^'\"]+)", api_text))
    if fetch_paths != {
        "/api/v1/catalog", "/api/v1/import-bundle", "/api/v1/compile-project",
        "/api/v2/migrate-project", "/api/v2/compile-project",
    }:
        failures.append("Studio frontend fetch surface is not the exact local API")
    for path in (ROOT / "studio-ui/src").glob("**/*"):
        if path.suffix in {".ts", ".tsx"} and path != STUDIO_API and "fetch(" in read_text(path):
            failures.append(f"Studio fetch call is outside api.ts: {path.relative_to(ROOT)}")

def _check_studio_vite_surface(vite_text: str, failures: list[str]) -> None:
    if "target: 'http://127.0.0.1:8765'" not in vite_text:
        failures.append("Studio Vite proxy must target the loopback compiler")
    if "host: '127.0.0.1'" not in vite_text or "strictPort: true" not in vite_text:
        failures.append("Studio Vite server must use a strict loopback binding")


def check_studio_surface(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    _check_studio_catalogs(parsed_json, failures)
    _check_studio_package(parsed_json, failures)
    _check_studio_network_surface(failures)


def check_control_dependency(failures: list[str]) -> None:
    requirements = read_text(CONTROL_REQUIREMENTS).splitlines()
    active = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    if active != ["cryptography==50.0.0"]:
        failures.append("connected-mode cryptography dependency must be pinned")
    workflow = read_text(CI_WORKFLOW)
    if "python3 -m pip install --requirement requirements-control.txt" not in workflow:
        failures.append("CI must install the connected-mode test dependency")
    for action in ("actions/checkout", "actions/setup-python"):
        if not re.search(
            rf"uses: {re.escape(action)}@[0-9a-f]{{40}}\s+# v6", workflow
        ):
            failures.append(f"CI action must use a reviewed commit pin: {action}")


def check_reusable_config(failures: list[str]) -> None:
    commands = (
        ([sys.executable, "-m", "queuewright", "self-test"], "self-test: ok"),
        ([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], None),
    )
    for command, expected in commands:
        try:
            result = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            failures.append(f"repository check could not run: {error}")
            continue
        if result.returncode != 0:
            failures.append(f"repository check failed: {(result.stderr or result.stdout).strip()}")
        elif expected is not None and result.stdout.strip() != expected:
            failures.append(f"repository check returned unexpected output: {result.stdout.strip()!r}")


def main() -> int:
    failures: list[str] = []
    files = list(active_files())
    parsed_json = check_files(files, failures)
    check_public_scope(failures)
    check_git_metadata(failures)
    check_studio_surface(parsed_json, failures)
    check_control_dependency(failures)
    check_reusable_config(failures)
    if (ROOT / ".env.example").exists():
        print(
            "NOTE: .env.example content is excluded from automated inspection; "
            "manual owner review is required"
        )
    if failures:
        print(f"FAIL: {len(failures)} issue(s)")
        for failure in failures:
            print(f"- {failure}")
        return 1
    json_count = sum(path.suffix.lower() == ".json" for path in files)
    print(
        f"PASS: {len(files)} public-alpha files; {json_count} JSON documents; "
        "links, assets, public scope, Studio contracts, and tracked Git metadata verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
