"""Fail a pull-request check when core coverage drops below its base branch."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def percentage(path: Path) -> float:
    """Read and validate coverage.py's JSON total percentage."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        value = float(report["totals"]["percent_covered"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read coverage percentage from {path}: {exc}") from exc
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise SystemExit(f"Invalid coverage percentage in {path}: {value!r}")
    return value


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_coverage_regression.py CURRENT.json BASE.json")
    current = percentage(Path(sys.argv[1]))
    base = percentage(Path(sys.argv[2]))
    print(f"Core coverage: base={base:.2f}%, current={current:.2f}%")
    if current + 1e-9 < base:
        print("Core coverage must not decrease on a pull request.")
        return 1
    print("Core coverage did not decrease.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
