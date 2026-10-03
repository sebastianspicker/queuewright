"""Comparable temporary-ledger append benchmark with no pass/fail timing gate."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from queuewright_control import InMemoryKeyProvider, Ledger


def _sample(count: int) -> float:
    with tempfile.TemporaryDirectory(prefix="queuewright-ledger-benchmark-") as directory:
        ledger = Ledger(
            Path(directory) / "ledger.sqlite3",
            InMemoryKeyProvider(b"benchmark-key-material-32-bytes!"),
        )
        try:
            started = time.perf_counter()
            for index in range(count):
                ledger.audit("benchmark", "append", {"index": index})
            duration = time.perf_counter() - started
            if ledger.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] != count:
                raise RuntimeError("benchmark ledger did not retain every append")
            return duration
        finally:
            ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=(50, 100, 200))
    parser.add_argument("--repeats", type=int, default=7)
    arguments = parser.parse_args()
    if arguments.repeats < 1 or any(size < 1 for size in arguments.sizes):
        parser.error("sizes and repeats must be positive")

    results = []
    for count in arguments.sizes:
        samples = [_sample(count) for _ in range(arguments.repeats)]
        results.append(
            {
                "appends": count,
                "seconds": samples,
                "median_seconds": statistics.median(samples),
                "min_seconds": min(samples),
                "max_seconds": max(samples),
            }
        )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "repeats": arguments.repeats,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
