"""Dependency-free structural and publication-policy checks for Queuewright."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
PYPROJECT = ROOT / "pyproject.toml"
STUDIO_ROOT = ROOT / "studio-ui"
STUDIO_PACKAGE = STUDIO_ROOT / "package.json"
STUDIO_LOCK = STUDIO_ROOT / "package-lock.json"
STUDIO_HTML = STUDIO_ROOT / "index.html"
STUDIO_VITE = STUDIO_ROOT / "vite.config.ts"
CONTROL_ROOT = ROOT / "experimental" / "connected_control"
ROOT_CONNECTION_SCHEMA = ROOT / "queuewright" / "contracts" / "schemas" / "zammad-connection.schema.json"
CONTROL_CONNECTION_SCHEMA = (
    CONTROL_ROOT / "queuewright_control" / "schemas" / "zammad-connection.schema.json"
)
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
SKIP_PATHS = {
    Path(".git"), Path(".agents"), Path(".claude"), Path(".codex"), Path(".cursor"),
    Path(".impeccable"), Path(".local"), Path(".serena"), Path("studio-ui/node_modules"),
    Path("studio-ui/dist"), Path("build"), Path("dist"),
}
AGENT_DIRECTORY_NAMES = {".agent", ".agents", ".ai", ".claude", ".codex", ".cursor"}
AGENT_FILE_NAMES = {
    ".cursorrules", "agent.md", "agents.md", "claude.md", "codex.md", "gemini.md",
    "copilot-instructions.md",
}
PROCESS_FILE_NAMES = {
    ".history-maintenance-provenance", "tasks.md", "plan.md", "progress.md", "scratchpad.md",
    "worklog.md", "work-log.md", "devlog.md", "development-log.md",
    "implementation-notes.md", "handoff.md", "handover.md",
}
REQUIRED_PATHS = {
    Path("experimental/connected_control/pyproject.toml"),
    Path("experimental/connected_control/tests"),
    Path("scripts/check_architecture.py"),
    Path("scripts/verify"),
}
STALE_PUBLIC_PATHS = (
    "profiles/example/", "studio/templates/", "studio/catalog/", "schemas/queuewright-",
    "requirements-control.txt", "RELEASE_STATUS.md",
)


def is_sensitive_name(name: str) -> bool:
    lower = name.lower()
    return (
        lower in {"token", "token_full"} or lower.startswith(".env")
        or lower in {"id_rsa", "id_ed25519", "credentials.json"}
        or lower.endswith((".key", ".pem", ".p12", ".pfx", ".secrets.json"))
        or "secret" in lower
    )


def is_forbidden_tracked_path(path: Path) -> bool:
    lower_parts = tuple(part.lower() for part in path.parts)
    lower_name = path.name.lower()
    process_artifact = len(path.parts) == 1 and (
        lower_name in PROCESS_FILE_NAMES
        or lower_name.endswith(("-ledger.md", "_ledger.md"))
        or lower_name.startswith(
            (
                "agent-notes", "agent-output", "agent-report", "agent-context",
                "agent-memory", "ai_notes", "ai_report", "ai_audit", "ai_summary",
                "llm_notes", "gpt_notes", "chatgpt_notes", "claude_notes", "codex_notes",
            )
        )
    )
    return (
        any(part in AGENT_DIRECTORY_NAMES for part in lower_parts)
        or lower_name in AGENT_FILE_NAMES
        or process_artifact
        or any(
            part.lower() != ".env.example" and is_sensitive_name(part)
            for part in path.parts
        )
        or path == Path(".local")
        or Path(".local") in path.parents
    )


def is_safe_path(path: Path) -> bool:
    if "__pycache__" in path.parts or any(part.startswith(".aider") for part in path.parts):
        return False
    return not any(path == prefix or prefix in path.parents for prefix in SKIP_PATHS)


def active_files() -> Iterator[Path]:
    if GIT is not None:
        try:
            names = subprocess.run(
                [GIT, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout.decode().split("\0")
        except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
            pass
        else:
            for name in filter(None, names):
                path = ROOT / name
                if path.is_file():
                    yield path
            return
    for directory, names, filenames in os.walk(ROOT, topdown=True):
        directory_path = Path(directory)
        names[:] = [
            name for name in names if is_safe_path((directory_path / name).relative_to(ROOT))
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
    target = (
        ROOT / destination.lstrip("/")
        if destination.startswith("/")
        else source.parent / destination
    )
    try:
        relative = target.resolve().relative_to(ROOT)
    except ValueError:
        return None
    return target if is_safe_path(relative) else None


def check_markdown(path: Path, text: str, failures: list[str]) -> None:
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        target = local_link_target(path, match.group(1))
        if target is not None and not target.exists():
            failures.append(f"missing local link: {path.relative_to(ROOT)} -> {match.group(1)}")
    for stale in STALE_PUBLIC_PATHS:
        if stale in text:
            failures.append(f"stale public path in {path.relative_to(ROOT)}: {stale}")


def check_file(path: Path, parsed_json: dict[Path, Any], failures: list[str]) -> None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            parsed_json[path] = json.loads(read_text(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            failures.append(f"JSON parse failed: {path.relative_to(ROOT)}: {error}")
        return
    if suffix == ".png":
        try:
            if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                failures.append(f"invalid PNG signature: {path.relative_to(ROOT)}")
        except OSError as error:
            failures.append(f"cannot read PNG: {path.relative_to(ROOT)}: {error}")
        return
    if suffix not in {".html", ".md", ".py", ".ts", ".tsx", ".yml", ".yaml"}:
        return
    text = read_text(path)
    if "\N{EM DASH}" in text:
        failures.append(f"prohibited em dash remains: {path.relative_to(ROOT)}")
    if suffix == ".md":
        check_markdown(path, text, failures)


def check_files(files: list[Path], failures: list[str]) -> dict[Path, Any]:
    parsed_json: dict[Path, Any] = {}
    for path in files:
        check_file(path, parsed_json, failures)
    return parsed_json


def check_required_paths(failures: list[str]) -> None:
    for path in sorted(REQUIRED_PATHS):
        if not (ROOT / path).exists():
            failures.append(f"required repository path is missing: {path}")
    for path in (
        Path("RELEASE_STATUS.md"), Path("src/__init__.py"),
        Path("queuewright/profile.py"), Path("queuewright/compiler.py"),
        Path("queuewright/blueprint.py"), Path("queuewright_studio/service.py"),
    ):
        if (ROOT / path).exists():
            failures.append(f"obsolete repository path remains: {path}")


def check_git_metadata(failures: list[str]) -> None:
    if GIT is None:
        failures.append("git executable is not available")
        return
    try:
        tracked = subprocess.run(
            [GIT, "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        failures.append(f"cannot inspect tracked filename metadata: {error}")
        return
    for name in filter(None, tracked):
        if (ROOT / name).exists() and is_forbidden_tracked_path(Path(name)):
            failures.append(f"tracked sensitive or excluded path: {name}")


def check_package(failures: list[str]) -> None:
    try:
        project = tomllib.loads(read_text(PYPROJECT))
    except (OSError, tomllib.TOMLDecodeError) as error:
        failures.append(f"cannot read pyproject.toml: {error}")
        return
    scripts = project.get("project", {}).get("scripts", {})
    build_system = project.get("build-system", {})
    package_data = project.get("tool", {}).get("setuptools", {}).get("package-data", {})
    contract_data = (
        package_data.get("queuewright.contracts", []) if isinstance(package_data, dict) else []
    )
    if scripts.get("queuewright") != "queuewright.cli:main":
        failures.append("pyproject.toml must expose the queuewright console script")
    if build_system.get("build-backend") != "setuptools.build_meta":
        failures.append("pyproject.toml must use the setuptools build backend")
    if not {"catalogs/*.json", "schemas/*.json", "schemas/README.md"} <= set(contract_data):
        failures.append("pyproject.toml must package contract JSON and schema README data")
    if ROOT_CONNECTION_SCHEMA.exists():
        failures.append("active Queuewright wheel must not contain the connected-control schema")


def python_release_version() -> str:
    """The pyproject version is the single source of release identity."""
    return str(tomllib.loads(read_text(PYPROJECT)).get("project", {}).get("version", ""))


def semver_release_version(python_version: str) -> str:
    """Map a PEP 440 pre-release (0.1.0a1) to its npm/SemVer spelling (0.1.0-alpha.1)."""
    labels = {"a": "alpha", "b": "beta", "rc": "rc"}
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?", python_version)
    if match is None:
        return ""
    base, label, number = match.groups()
    return base if label is None else f"{base}-{labels[label]}.{number}"


def check_release_identity(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    python_version = python_release_version()
    release_version = semver_release_version(python_version)
    if not release_version:
        failures.append(f"pyproject.toml version is not a supported release: {python_version!r}")
        return
    package = parsed_json.get(STUDIO_PACKAGE)
    lock = parsed_json.get(STUDIO_LOCK)
    release_notes = ROOT / "docs" / "releases" / f"{release_version}.md"
    if not isinstance(package, dict) or package.get("version") != release_version:
        failures.append(f"Studio package version must match pyproject ({release_version})")
    if not isinstance(lock, dict) or lock.get("version") != release_version:
        failures.append(f"Studio lockfile version must match pyproject ({release_version})")
    try:
        if f"# Queuewright `{release_version}`" not in read_text(release_notes):
            failures.append(f"release identity is missing from {release_notes.relative_to(ROOT)}")
    except OSError as error:
        failures.append(f"cannot read release identity from {release_notes.relative_to(ROOT)}: {error}")


def check_studio_surface(parsed_json: dict[Path, Any], failures: list[str]) -> None:
    package = parsed_json.get(STUDIO_PACKAGE)
    lock = parsed_json.get(STUDIO_LOCK)
    if not isinstance(package, dict) or not isinstance(lock, dict):
        failures.append("Studio package and lockfile must be valid JSON")
    else:
        scripts = package.get("scripts")
        if not isinstance(scripts, dict) or not {
            "dev", "test", "build", "build:demo"
        } <= set(scripts):
            failures.append("Studio package must expose dev, test, build, and build:demo scripts")
        if package.get("version") != lock.get("version"):
            failures.append("Studio package and lockfile versions must match")
    try:
        html = read_text(STUDIO_HTML)
        vite = read_text(STUDIO_VITE)
    except OSError as error:
        failures.append(f"cannot inspect Studio surface: {error}")
        return
    if re.search(r"(?:src|href)=[\"']https?://", html):
        failures.append("Studio HTML must not load remote resources")
    if "host: '127.0.0.1'" not in vite or "strictPort: true" not in vite:
        failures.append("Studio Vite server must use strict loopback binding")
    if "'/api/v1'" not in vite or "'/api/v2'" not in vite:
        failures.append("Studio Vite configuration must proxy both API versions")


def check_workflows(failures: list[str]) -> None:
    for workflow in (CI_WORKFLOW, PAGES_WORKFLOW):
        try:
            text = read_text(workflow)
        except OSError as error:
            failures.append(f"cannot inspect workflow {workflow.relative_to(ROOT)}: {error}")
            continue
        for action, revision in re.findall(r"uses:\s+([^\s@]+)@([^\s#]+)", text):
            if action.startswith("actions/") and not re.fullmatch(r"[0-9a-f]{40}", revision):
                failures.append(
                    f"workflow action is not commit pinned: {workflow.relative_to(ROOT)} -> {action}"
                )


def check_control_layout(failures: list[str]) -> None:
    try:
        control = tomllib.loads(read_text(CONTROL_ROOT / "pyproject.toml"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        failures.append(f"cannot read isolated control package metadata: {error}")
        return
    if control.get("project", {}).get("version") != python_release_version():
        failures.append("isolated control package version must match pyproject.toml")
    package_data = control.get("tool", {}).get("setuptools", {}).get("package-data", {})
    control_data = package_data.get("queuewright_control", []) if isinstance(package_data, dict) else []
    if "schemas/*.json" not in control_data or not CONTROL_CONNECTION_SCHEMA.is_file():
        failures.append("isolated control package must own and package the connection schema")


def main() -> int:
    failures: list[str] = []
    files = list(active_files())
    parsed_json = check_files(files, failures)
    check_required_paths(failures)
    check_git_metadata(failures)
    check_package(failures)
    check_release_identity(parsed_json, failures)
    check_studio_surface(parsed_json, failures)
    check_workflows(failures)
    check_control_layout(failures)
    if failures:
        print(f"FAIL: {len(failures)} issue(s)")
        print(*(f"- {failure}" for failure in failures), sep="\n")
        return 1
    print(
        f"PASS: {len(files)} files; structural policy, packaged contracts, Studio surface, "
        "and Git metadata verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
