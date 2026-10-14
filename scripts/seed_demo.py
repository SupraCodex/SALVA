#!/usr/bin/env python3
"""Seed the reference data and the demonstration workspace (idempotent).

Thin wrapper kept for compatibility; the logic lives in ``backend/app/seed.py`` so that
the container can run it with ``python -m app.seed``. Run from the repository root with
DATABASE_URL set (and optionally DEMO_USER_PASSWORD):

    python scripts/seed_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.seed import main

if __name__ == "__main__":
    sys.exit(main(["--reference", "--demo"]))
