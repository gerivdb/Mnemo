# intent_hash: 0xPERIMETER_AWARENESS_INIT_20260916
"""Perimeter Awareness — Auto-Reconnaissance Universelle du Périmètre d'Implémentation."""

# Avoid relative imports for pytest compatibility
import sys
from pathlib import Path

_TOOL_DIR = Path(__file__).parent
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))

from perimeter_awareness import (
    self_check,
    discover,
    register_in_perimeter,
    validate_bidirectional,
    validate_all_engines,
    full_pipeline,
    get_current_repo_info,
    load_sot,
    discover_perimeter,
)

__all__ = [
    "self_check",
    "discover",
    "register_in_perimeter",
    "validate_bidirectional",
    "validate_all_engines",
    "full_pipeline",
    "get_current_repo_info",
    "load_sot",
    "discover_perimeter",
]

__version__ = "1.0.0"
__intent_hash__ = "0xPERIMETER_AWARENESS_20260916"