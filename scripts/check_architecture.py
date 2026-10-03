"""Enforce the small set of dependency directions that define Queuewright."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_LAYERS = ("contracts", "configuration", "planning", "projects", "studio")
LAYER_DEPENDENCIES = {
    "contracts": {"contracts"},
    "configuration": {"contracts", "configuration"},
    "planning": {"contracts", "configuration", "planning"},
    "projects": {"contracts", "configuration", "planning", "projects"},
    "studio": {"contracts", "projects", "studio"},
}
EXPERIMENTAL_CONTROL = ROOT / "experimental" / "connected_control"
FETCH_CLIENT = ROOT / "studio-ui" / "src" / "api" / "client.ts"
PERSISTENCE_ROOT = ROOT / "studio-ui" / "src" / "persistence"


def python_files(*roots: Path) -> list[Path]:
    return sorted(path for root in roots if root.exists() for path in root.rglob("*.py"))


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def import_names(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        return [f"<parse error: {error}>"]
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = imported_module(path, node)
            if module:
                names.append(module)
                # ``from pkg import name`` may import the submodule ``pkg.name``.
                names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def imported_module(path: Path, node: ast.ImportFrom) -> str:
    """Resolve the absolute module name of an absolute or relative ``from`` import."""
    if node.level == 0:
        return node.module or ""
    package = module_name(path).split(".")
    if path.name != "__init__.py":
        package.pop()
    parent = package[: len(package) - node.level + 1]
    if node.module:
        parent.extend(node.module.split("."))
    return ".".join(parent)


def layer_for(path: Path) -> str | None:
    try:
        relative = path.relative_to(ROOT / "queuewright")
    except ValueError:
        return None
    return relative.parts[0] if relative.parts and relative.parts[0] in PYTHON_LAYERS else None


def target_layer(name: str) -> str | None:
    parts = name.split(".")
    if len(parts) > 1 and parts[0] == "queuewright" and parts[1] in PYTHON_LAYERS:
        return parts[1]
    return None


def check_python_layers(failures: list[str]) -> None:
    for path in python_files(ROOT / "queuewright"):
        source_layer = layer_for(path)
        for name in import_names(path):
            if name.startswith("<parse error:"):
                failures.append(f"cannot parse Python source: {path.relative_to(ROOT)}: {name}")
                continue
            if "queuewright_control" in name or name.startswith("experimental.connected_control"):
                failures.append(
                    f"active Python imports experimental control: {path.relative_to(ROOT)} -> {name}"
                )
            target = target_layer(name)
            if source_layer and target and target not in LAYER_DEPENDENCIES[source_layer]:
                failures.append(
                    f"Python layer violation: {path.relative_to(ROOT)} "
                    f"({source_layer}) imports {target}"
                )
    for path in python_files(ROOT / "queuewright_studio"):
        for name in import_names(path):
            if "queuewright_control" in name or name.startswith("experimental.connected_control"):
                failures.append(
                    f"active Python imports experimental control: {path.relative_to(ROOT)} -> {name}"
                )
    for path in python_files(EXPERIMENTAL_CONTROL):
        for name in import_names(path):
            active_package = name == "queuewright" or name.startswith("queuewright.")
            active_studio = name == "queuewright_studio" or name.startswith("queuewright_studio.")
            if active_package or active_studio:
                failures.append(
                    f"experimental control imports active package: {path.relative_to(ROOT)} -> {name}"
                )


def private_import_failures(path: Path) -> list[str]:
    """Report underscore-prefixed names imported across queuewright subpackages."""
    source = path.relative_to(ROOT / "queuewright").parts
    source_package = source[0] if len(source) > 1 else None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = imported_module(path, node)
        parts = module.split(".")
        if (
            parts[0] != "queuewright" or len(parts) < 2
            or parts[1] not in PYTHON_LAYERS or parts[1] == source_package
        ):
            continue
        for alias in node.names:
            if alias.name.startswith("_") and not alias.name.startswith("__"):
                failures.append(
                    f"private name imported across subpackages: {path.relative_to(ROOT)} "
                    f"imports {alias.name} from {module}"
                )
    return failures


def check_private_imports(failures: list[str]) -> None:
    for path in python_files(ROOT / "queuewright"):
        failures.extend(private_import_failures(path))


def frontend_files() -> list[Path]:
    source = ROOT / "studio-ui" / "src"
    return sorted(path for path in source.rglob("*") if path.suffix in {".ts", ".tsx"})


def check_frontend_seams(failures: list[str]) -> None:
    fetch_pattern = re.compile(r"\bfetch\s*\(")
    storage_pattern = re.compile(r"\b(?:indexedDB|localStorage|sessionStorage)\b")
    direct_boundary = re.compile(
        r"(?:from\s+|import\s*\(\s*)['\"][^'\"]*(?:api|persistence)/"
    )
    data_import = re.compile(
        r"(?:from\s+|import\s*\(\s*)['\"](?:[^'\"]*/)?data(?:/[^'\"]*)?['\"]"
    )
    forbidden_low_level = re.compile(r"from\s+['\"][^'\"]*(?:editor|persistence)/")
    editor_internals = re.compile(
        r"(?:from\s+|import\s*\(\s*)['\"][^'\"]*editor/(?:reducer|effects)['\"]"
    )
    for path in frontend_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT / "studio-ui" / "src")
        if fetch_pattern.search(text) and path != FETCH_CLIENT:
            failures.append(f"Studio fetch call is outside api/client.ts: studio-ui/src/{relative}")
        if storage_pattern.search(text) and PERSISTENCE_ROOT not in path.parents:
            failures.append(
                f"Studio browser storage is outside persistence/: studio-ui/src/{relative}"
            )
        if relative.parts[0] in {"app", "components", "screens"} and direct_boundary.search(text):
            failures.append(f"Studio UI bypasses editor seam: studio-ui/src/{relative}")
        if relative.parts[0] in {"app", "components", "screens"} and data_import.search(text):
            failures.append(f"Studio UI imports bundled data directly: studio-ui/src/{relative}")
        if relative.parts[0] in {"app", "components", "screens"} and editor_internals.search(text):
            failures.append(
                f"Studio UI imports editor reducer or effects directly: studio-ui/src/{relative}"
            )
        if relative.parts[0] in {"api", "persistence"} and forbidden_low_level.search(text):
            failures.append(
                f"Studio low-level seam depends on editor or persistence: studio-ui/src/{relative}"
            )


def main() -> int:
    failures: list[str] = []
    check_python_layers(failures)
    check_private_imports(failures)
    check_frontend_seams(failures)
    if failures:
        print(f"FAIL: {len(failures)} architecture issue(s)")
        print(*(f"- {failure}" for failure in failures), sep="\n")
        return 1
    print("PASS: Python layers, isolated control, and Studio seams verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
