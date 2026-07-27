"""Command-line interface for the offline configuration package."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .compiler import compile_loaded_profile
from .errors import ConfigurationError
from .profile import (
    is_forbidden_local_path,
    load_profile,
    validate_loaded_profile,
    validate_profile,
)


def _dump(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_plan(
    output: str, rendered: str, loaded: dict[str, object]
) -> None:
    target = Path(output).resolve()
    if target.suffix.lower() != ".json" or is_forbidden_local_path(target):
        raise ConfigurationError(
            "plan output must be a non-sensitive local JSON path"
        )
    if target in {loaded["profile_path"], loaded["manifest_path"]}:
        raise ConfigurationError("refusing to overwrite profile or manifest input")
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".queuewright-",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(rendered + "\n")
        target.hardlink_to(temporary)
    except FileExistsError as error:
        raise ConfigurationError(
            f"refusing to overwrite existing plan output {target}"
        ) from error
    except OSError as error:
        raise ConfigurationError(f"cannot write plan output {target}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m queuewright",
        description="Queuewright offline configuration compiler",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("profile")
    plan = commands.add_parser("plan")
    plan.add_argument("profile")
    plan.add_argument("--output")
    commands.add_parser("self-test")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "self-test":
            root = Path(__file__).resolve().parent.parent
            validate_profile(root / "studio/templates/university")
            profiles = root / "profiles"
            validate_profile(profiles / "example")
            print("self-test: ok")
            return 0
        loaded = load_profile(args.profile)
        result = (
            validate_loaded_profile(loaded)
            if args.command == "validate"
            else compile_loaded_profile(loaded)
        )
        rendered = _dump(result)
        if args.command == "plan" and args.output:
            _write_plan(args.output, rendered, loaded)
        else:
            print(rendered)
        return 0
    except ConfigurationError as error:
        parser.error(str(error))
    return 2
