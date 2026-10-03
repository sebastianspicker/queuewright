"""Build isolated control archives and verify schema access from an installed wheel."""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "queuewright_control/__init__.py",
    "queuewright_control/schemas/zammad-connection.schema.json",
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="queuewright-control-package-") as temporary:
        directory = Path(temporary)
        output = directory / "artifacts"
        subprocess.run([
            sys.executable, "-m", "build", "--outdir", str(output),
            str(ROOT / "experimental/connected_control"),
        ], check=True)
        wheel, = output.glob("*.whl")
        sdist, = output.glob("*.tar.gz")
        with zipfile.ZipFile(wheel) as archive:
            wheel_names = set(archive.namelist())
        with tarfile.open(sdist) as archive:
            source_names = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}
        for label, names in (("wheel", wheel_names), ("sdist", source_names)):
            if not REQUIRED <= names:
                raise RuntimeError(f"{label} is missing package files: {sorted(REQUIRED - names)}")
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([
            str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel),
        ], cwd=directory, check=True)
        probe = """
import json
import pathlib
import sys
from importlib.resources import files
import queuewright_control
package = pathlib.Path(queuewright_control.__file__).resolve()
assert package.is_relative_to(pathlib.Path(sys.prefix).resolve()), package
schema = json.loads(files('queuewright_control').joinpath('schemas/zammad-connection.schema.json').read_text())
assert schema['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
assert schema['type'] == 'object'
print('PASS: isolated installed control wheel exposes its connection schema')
"""
        subprocess.run([str(python), "-I", "-c", probe], cwd=directory, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
