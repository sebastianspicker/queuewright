"""Reproducible offline compiler timing and transport-size measurements."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from queuewright.contracts.json import canonical_json
from queuewright.projects import compile_v2_project
from queuewright.studio.representation import editor_representation


def measure(containers: int, repetitions: int) -> dict[str, object]:
    project = json.loads((ROOT / "queuewright/examples/university/project-v2.json").read_text())
    project["bundle"]["manifest"]["groups"].extend(
        {"active": True, "key": f"bench_{index}", "kind": "container",
         "name": f"University Template · Benchmark {index}",
         "parent": f"bench_{index - 1}" if index else "university"}
        for index in range(containers)
    )
    reference = compile_v2_project(project)
    durations = []
    for _ in range(repetitions):
        started = time.perf_counter()
        compiled = compile_v2_project(project)
        durations.append((time.perf_counter() - started) * 1000)
        if compiled != reference:
            raise RuntimeError("repeated compilation changed the canonical artifacts")
    compact = editor_representation(reference)
    return {
        "additional_containers": containers,
        "repetitions": repetitions,
        "median_ms": round(statistics.median(durations), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "request_bytes": len(canonical_json({"project": project}).encode()),
        "full_response_bytes": len(canonical_json(reference).encode()),
        "editor_response_bytes": len(canonical_json(compact).encode()),
        "hashes": reference["hashes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--containers", type=int, nargs="+", default=[0, 500, 1000, 2000])
    args = parser.parse_args()
    if args.repetitions < 1 or any(size < 0 for size in args.containers):
        parser.error("repetitions must be positive and container counts nonnegative")
    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "warmups": 1,
        "workload": "valid university project with an added container chain; compilation only",
        "measurements": [measure(size, args.repetitions) for size in args.containers],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
