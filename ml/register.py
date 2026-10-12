"""Decide which model the backend uses (writes ml/artifacts/active.json).

Rule enforced here: LightGBM becomes the PRODUCTION model only if its go_nogo.json says
"LIGHTGBM GO" and --promote is passed.  Otherwise the kinetic model stays in production and
the package (if any) is registered as EXPERIMENTAL.  Nothing forces a replacement.

    python -m ml.register --package ml/artifacts/models/<version> --report ml/reports/<version> [--promote]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ARTIFACTS_DIR, write_json

ACTIVE_PATH = ARTIFACTS_DIR / "active.json"


def register(package_dir: Path | str, report_dir: Path | str, *, promote: bool = False,
             active_path: Path | str | None = None) -> dict[str, str | None]:
    package_dir, report_dir = Path(package_dir), Path(report_dir)
    verdict = json.loads((report_dir / "go_nogo.json").read_text())["go_nogo"]["verdict"]
    name = package_dir.name
    path = Path(active_path or ACTIVE_PATH)
    if promote and verdict != "LIGHTGBM GO":
        raise PermissionError(f"Refusing to promote {name}: verdict is {verdict}")
    cfg = {"production": name if promote else "kinetic", "experimental": None if promote else name,
           "verdict": verdict}
    write_json(path, cfg)
    return cfg


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Register the active/experimental model")
    ap.add_argument("--package", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--promote", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(register(a.package, a.report, promote=a.promote), indent=2))


if __name__ == "__main__":
    main()
