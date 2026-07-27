#!/usr/bin/env python3
"""Dependency-free public-alpha consistency checks for Queuewright."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
STUDIO_CATALOG = ROOT / "studio/catalog/features.json"
STUDIO_CAPABILITY_CATALOG = ROOT / "studio/catalog/capabilities.json"
STUDIO_PACKAGE = ROOT / "studio-ui/package.json"
STUDIO_LOCK = ROOT / "studio-ui/package-lock.json"
STUDIO_API = ROOT / "studio-ui/src/api.ts"
STUDIO_VITE = ROOT / "studio-ui/vite.config.ts"
CONTROL_REQUIREMENTS = ROOT / "requirements-control.txt"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
SKIP_PATHS = {
    Path(".git"), Path(".agents"), Path(".claude"), Path(".codex"),
    Path(".cursor"), Path(".impeccable"), Path(".local"), Path(".serena"),
    Path("studio-ui/node_modules"), Path("studio-ui/dist"),
    Path("studio-ui/playwright-report"), Path("studio-ui/test-results"),
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
        lower.startswith("token") or lower.startswith(".env")
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


def check_files(files: list[Path], failures: list[str]) -> dict[Path, Any]:
    parsed_json: dict[Path, Any] = {}
    link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for path in files:
        text = read_text(path) if path.suffix.lower() in {
            ".html", ".md", ".py", ".ts", ".tsx"
        } else None
        if text is not None and "\N{EM DASH}" in text:
            failures.append(
                f"prohibited em dash remains: {path.relative_to(ROOT)}"
            )
        if path.suffix.lower() == ".json":
            try:
                parsed_json[path] = json.loads(read_text(path))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                failures.append(f"JSON parse failed: {path.relative_to(ROOT)}: {error}")
        if path.suffix.lower() == ".md":
            assert text is not None
            for match in re.finditer(r"\*\*([^*\n]+)\*\*", text):
                content = match.group(1).strip().strip("`")
                if content and not re.search(r"\s", content):
                    failures.append(
                        "single-word bold emphasis remains: "
                        f"{path.relative_to(ROOT)}: {content}"
                    )
            for match in link_re.finditer(text):
                target = local_link_target(path, match.group(1))
                if target is not None and not target.exists():
                    failures.append(f"missing local link: {path.relative_to(ROOT)} -> {match.group(1)}")
        if path.suffix.lower() == ".png":
            try:
                valid = path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            except OSError as error:
                failures.append(f"cannot read PNG: {path.relative_to(ROOT)}: {error}")
            else:
                if not valid:
                    failures.append(f"invalid PNG signature: {path.relative_to(ROOT)}")
    return parsed_json


def check_public_scope(failures: list[str]) -> None:
    for path in sorted(PUBLICLY_OBSOLETE_PATHS):
        if (ROOT / path).exists():
            failures.append(f"obsolete pre-alpha public lane remains: {path}")


def check_git_metadata(failures: list[str]) -> None:
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        failures.append(f"cannot inspect tracked filename metadata: {error}")
        return
    for name in filter(None, tracked):
        if is_forbidden_tracked_path(Path(name)):
            failures.append(f"tracked sensitive or excluded path: {name}")
    for probe in (
        "token", "token_full", "nested/token", "nested/token_full",
        ".local/verifier-probe", ".agents/session.json", ".claude/settings.local.json",
        ".codex/session.json", ".cursor/session.json", ".impeccable/design.json",
        ".serena/project.local.yml", ".aider.chat.history.md",
        "probe.secrets.json", "probe.p12",
        "id_ed25519", "studio-ui/.npmrc", ".pypirc", ".netrc",
        "sample.credentials.json", "coverage.xml", ".coverage",
        "htmlcov/index.html", "tests/__pycache__/probe.pyc",
        "studio-ui/test-results/failure.png",
        "studio-ui/playwright-report/index.html",
    ):
        if subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT).returncode != 0:
            failures.append(f"representative private path is not ignored by git: {probe}")
    for probe in (
        "token-policy.md", ".env.example", ".npmrc.example",
        "tests/test_probe.py", "studio-ui/src/probe.test.ts",
        "studio-ui/e2e/probe.spec.ts",
    ):
        if subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT).returncode == 0:
            failures.append(f"publishable path is over-broadly ignored by git: {probe}")


def check_studio_surface(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    catalog = parsed_json.get(STUDIO_CATALOG)
    capabilities = parsed_json.get(STUDIO_CAPABILITY_CATALOG)
    package = parsed_json.get(STUDIO_PACKAGE)
    lock = parsed_json.get(STUDIO_LOCK)
    feature_rows = catalog.get("features") if isinstance(catalog, dict) else None
    capability_rows = capabilities.get("capabilities") if isinstance(capabilities, dict) else None
    if not isinstance(feature_rows, list) or {row.get("id") for row in feature_rows if isinstance(row, dict)} != STUDIO_FEATURE_IDS:
        failures.append("Studio feature catalog must define the exact 14 feature IDs")
    if not isinstance(capability_rows, list) or {row.get("id") for row in capability_rows if isinstance(row, dict)} != STUDIO_CAPABILITY_IDS:
        failures.append("Studio capability catalog must define the exact 19 capability IDs")
    if not isinstance(package, dict) or package.get("version") != "0.1.0-alpha.1":
        failures.append("Studio package version must match alpha candidate 0.1.0-alpha.1")
    if not isinstance(lock, dict):
        failures.append("Studio package-lock.json is required for a reproducible alpha")
    elif lock.get("version") != "0.1.0-alpha.1":
        failures.append("Studio lockfile version must match alpha candidate 0.1.0-alpha.1")
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict) or not {"dev", "build", "test", "test:e2e"} <= set(scripts):
        failures.append("Studio package scripts are incomplete")
    api_text = read_text(STUDIO_API)
    vite_text = read_text(STUDIO_VITE)
    fetch_paths = set(re.findall(r"fetch\(['\"]([^'\"]+)", api_text))
    if fetch_paths != {
        "/api/v1/catalog", "/api/v1/import-bundle", "/api/v1/compile-project",
        "/api/v2/migrate-project", "/api/v2/compile-project",
    }:
        failures.append("Studio frontend fetch surface is not the exact local API")
    for path in (ROOT / "studio-ui/src").glob("**/*"):
        if path.suffix in {".ts", ".tsx"} and path != STUDIO_API and "fetch(" in read_text(path):
            failures.append(f"Studio fetch call is outside api.ts: {path.relative_to(ROOT)}")
    if "target: 'http://127.0.0.1:8765'" not in vite_text:
        failures.append("Studio Vite proxy must target the loopback compiler")
    if "host: '127.0.0.1'" not in vite_text or "strictPort: true" not in vite_text:
        failures.append("Studio Vite server must use a strict loopback binding")


def check_control_dependency(failures: list[str]) -> None:
    requirements = read_text(CONTROL_REQUIREMENTS).splitlines()
    active = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]
    if active != ["cryptography==49.0.0"]:
        failures.append("connected-mode cryptography dependency must be pinned")
    workflow = read_text(CI_WORKFLOW)
    if "python3 -m pip install --requirement requirements-control.txt" not in workflow:
        failures.append("CI must install the connected-mode test dependency")
    for action in ("actions/checkout", "actions/setup-python", "actions/setup-node"):
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
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
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
        "links, assets, public scope, Studio contracts, and Git ignore metadata verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
