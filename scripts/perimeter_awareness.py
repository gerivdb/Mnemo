#!/usr/bin/env python3
"""Wrapper pour perimeter-awareness - auto-ajout au path."""
import sys
from pathlib import Path

# Auto-détection du chemin perimeter-awareness
TOOL_DIR = Path(__file__).parent.parent / "tools" / "perimeter-awareness"
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from perimeter_awareness import main
if __name__ == "__main__":
    sys.exit(main())
