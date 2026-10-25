"""Thin wrapper — delegates to backend script so DATA_DIR / imports stay consistent."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
runpy.run_path(str(BACKEND / "app" / "scripts" / "run_ml_pipeline.py"), run_name="__main__")
