#!/usr/bin/env python3
# intent_hash: 0xPERIMETER_AWARENESS_TEST_20260916
"""Unit tests for perimeter-awareness tool."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB")


def test_perimeter_awareness_script_exists() -> bool:
    script = Path("D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness/perimeter_awareness.py")
    assert script.exists(), "perimeter_awareness.py missing"
    print("[UNIT] perimeter_awareness script exists OK")
    return True


def test_perimeter_awareness_self_check() -> bool:
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import self_check

    result = self_check()
    assert result.get("ok", False), "self_check should succeed"
    assert "current_repo" in result, "current_repo missing"
    assert "engines" in result, "engines missing"
    print("[UNIT] self_check OK")
    return True


def test_perimeter_awareness_discover() -> bool:
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import discover

    result = discover()
    assert "perimeter" in result, "perimeter missing"
    assert "engines" in result, "engines missing"
    perimeter = result["perimeter"]
    assert perimeter["total_repos"] > 0, "no repos discovered"
    print(f"[UNIT] discover OK: {perimeter['total_repos']} repos, {len(result['engines'])} engines")
    return True


def test_perimeter_awareness_validate_engines() -> bool:
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import validate_all_engines

    result = validate_all_engines()
    assert "engines" in result, "engines missing"
    assert "all_ok" in result, "all_ok missing"
    print(f"[UNIT] validate_engines OK: all_ok={result['all_ok']}")
    return True


def test_perimeter_awareness_self_check_current_repo() -> bool:
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import self_check

    result = self_check()
    current = result.get("current_repo", {})
    assert "name" in current, "repo name missing"
    assert current["name"] == "GOVERNANCE-HUB", f"Expected GOVERNANCE-HUB, got {current['name']}"
    print(f"[UNIT] current repo identified: {current['name']}")
    return True


def test_perimeter_awareness_discover_has_critical_engines() -> bool:
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import discover, validate_all_engines

    result = discover()
    perimeter = result["perimeter"]
    engines_found = perimeter.get("engines", {})

    # Vérifier que les 4 moteurs critiques sont trouvés
    # Note: anamorphoser est un outil DANS CTULU, pas un repo séparé
    critical = ["kg-l", "talex", "ctulu"]
    for engine in critical:
        assert engine in engines_found, f"Engine {engine} not in discovered engines"
        assert engines_found[engine].get("found", False), f"Engine {engine} not found"

    # anamorphoser est un outil DANS CTULU, vérifier qu'il est détecté via CTULU
    # Le test vérifie que l'import anamorphoser fonctionne
    sys.path.insert(0, "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")
    from perimeter_awareness import validate_all_engines
    engines = validate_all_engines()["engines"]
    # anamorphoser est testé via import test dans validate_all_engines
    assert "anamorphoser" in engines, "anamorphoser not in validated engines"
    assert engines["anamorphoser"].get("import_ok", False), "anamorphoser import failed"

    print(f"[UNIT] All critical engines discovered: {critical} + anamorphoser (via CTULU)")
    return True


def main() -> int:
    tests = [
        test_perimeter_awareness_script_exists,
        test_perimeter_awareness_self_check,
        test_perimeter_awareness_discover,
        test_perimeter_awareness_validate_engines,
        test_perimeter_awareness_self_check_current_repo,
        test_perimeter_awareness_discover_has_critical_engines,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"[UNIT] {test.__name__} FAILED: {e}")
            results.append(False)

    passed = sum(results)
    total = len(results)
    print(f"[UNIT] {passed}/{total} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())