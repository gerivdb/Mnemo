#!/usr/bin/env python3
"""Wrapper CLI pour perimeter-awareness."""
import importlib.util
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent / "tools" / "perimeter-awareness"
SPEC_PATH = TOOL_DIR / "perimeter_awareness.py"

if not SPEC_PATH.exists():
    raise SystemExit(f"[perimeter] missing module: {SPEC_PATH}")

spec = importlib.util.spec_from_file_location("perimeter_awareness_under_test", SPEC_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

if __name__ == "__main__":
    sys.exit(mod.main())
