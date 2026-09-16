# intent_hash: 0xPERIMETER_AWARENESS_PROTOCOL_20260916
# EPIC-XXX — perimeter-awareness: Universal Self-Recognition Protocol
"""Perimeter Awareness — Auto-Reconnaissance Universelle du Périmètre d'Implémentation.

Protocole permettant à n'importe quel repo de :
1. S'auto-reconnaître comme acteur du périmètre d'implémentation
2. Découvrir le périmètre complet depuis la SOT (known_repositories.yaml)
3. Valider la connectivité aux moteurs critiques (KG-L, TALEX, CTULU, Anamorphoser)
5. S'enregistrer dans le registre de périmètre (SWARM.yaml / perimeter-registry.json)
6. S'auto-valider comme acteur légitime du périmètre

Usage:
    python -m perimeter_awareness --self-check          # Auto-validation locale
    python -m perimeter_awareness --discover            # Découverte périmètre complet
    python -m perimeter_awareness --register            # Enregistrement dans SWARM/perimeter-registry
    python -m perimeter_awareness --validate-all        # Validation complète bidirectionnelle
    python -m perimeter_awareness --full                # Pipeline complète

IntentHash: 0xPERIMETER_AWARENESS_20260916
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent  # GOVERNANCE-HUB or any repo root
SOT_PATH = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB/known_repositories.yaml")
SWARM_PATH = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB/SWARM.yaml")
PERIMETER_REGISTRY = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB/perimeter-registry.json")

# Moteurs critiques avec leurs points de santé
CRITICAL_ENGINES = {
    "kg-l": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/KG-L",
        "health_endpoint": "http://127.0.0.1:8787/health",
        "validate_endpoint": "http://127.0.0.1:8787/validate_causal",
        "import_test": "kg_l_server",
        "required": True,
    },
    "talex": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/TALEX",
        "health_endpoint": None,
        "validate_endpoint": None,
        "import_test": "talex.runners.curx",
        "required": True,
    },
    "ctulu": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU",
        "health_endpoint": None,
        "validate_endpoint": None,
        "import_test": "anamorphoser",
        "required": True,
    },
    "anamorphoser": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/anamorphoser",
        "health_endpoint": None,
        "validate_endpoint": None,
        "import_test": "anamorphoser",
        "import_check_attr": "MoteurComparaison",
        "required": True,
    },
    "causal-guard": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/causal-guard-anything",
        "health_endpoint": None,
        "validate_endpoint": None,
        "import_test": "causal_guard",
        "required": False,
    },
    "causal-drift": {
        "path": "D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/causal-drift",
        "health_endpoint": None,
        "validate_endpoint": None,
        "import_test": "causal_drift",
        "required": False,
    },
}

# Chemins SOT par strate
STRATE_PATHS = {
    "L0_CANON": "D:/DO/WEB/TOOLS/L0-CANON",
    "L1_CAUSALITY": "D:/DO/WEB/TOOLS/L1-INFRA",
    "L1b": "D:/DO/WEB/TOOLS/L1-INFRA",
    "L2_COMPOSITION": "D:/DO/WEB/TOOLS/L2-PLATFORM",
    "L2_PLATFORM": "D:/DO/WEB/TOOLS/L2-PLATFORM",
    "L3_EMERGENCE": "D:/DO/WEB/TOOLS/L3-CITIZENS",
    "L4_TOOLS": "D:/DO/WEB/TOOLS/L4-TOOLS",
    "L5_ARCHIVE": "D:/DO/WEB/TOOLS/L5-ARCHIVE",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: List[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def get_current_repo_info() -> Dict[str, Any]:
    """Identifie le repo courant et son identité."""
    try:
        # Trouver la racine git
        r = run_cmd(["git", "rev-parse", "--show-toplevel"], Path.cwd())
        if r.returncode != 0:
            return {"error": "Not in a git repository"}
        repo_root = Path(r.stdout.strip())

        # Infos repo
        name = repo_root.name
        remote_url = ""
        r = run_cmd(["git", "config", "--get", "remote.origin.url"], repo_root)
        if r.returncode == 0:
            remote_url = r.stdout.strip()

        branch = ""
        r = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
        if r.returncode == 0:
            branch = r.stdout.strip()

        commit = ""
        r = run_cmd(["git", "rev-parse", "HEAD"], repo_root)
        if r.returncode == 0:
            commit = r.stdout.strip()[:12]

        return {
            "name": name,
            "path": str(repo_root),
            "remote_url": remote_url,
            "branch": branch,
            "commit": commit,
            "timestamp": _now_iso(),
        }
    except Exception as e:
        return {"error": str(e)}


def load_sot() -> List[Dict[str, Any]]:
    """Charge la Source of Truth (known_repositories.yaml)."""
    if not SOT_PATH.exists():
        return []
    try:
        data = yaml.safe_load(SOT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Charger tous les niveaux de priorité P0-P5
            repos = []
            for key in ["P0_REPOS", "P1_REPOS", "P2_REPOS", "P3_REPOS", "P4_REPOS", "P5_REPOS"]:
                if key in data and isinstance(data[key], list):
                    repos.extend(data[key])
            # Aussi charger la clé 'repositories' si elle existe (format legacy)
            if "repositories" in data and isinstance(data["repositories"], list):
                repos.extend(data["repositories"])
            return repos
        elif isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def discover_perimeter() -> Dict[str, Any]:
    """Découvre le périmètre complet depuis la SOT."""
    repos = load_sot()
    perimeter = {
        "total_repos": len(repos),
        "by_layer": {},
        "by_status": {},
        "engines": {},
        "repos": [],
    }

    for repo in repos:
        layer = repo.get("layer", "UNKNOWN")
        status = repo.get("status", "UNKNOWN")
        perimeter["by_layer"][layer] = perimeter["by_layer"].get(layer, 0) + 1
        perimeter["by_status"][status] = perimeter["by_status"].get(status, 0) + 1

        repo_info = {
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "layer": layer,
            "status": status,
            "local_path": repo.get("local_path"),
            "role": repo.get("role"),
            "intent_hash": repo.get("intent_hash"),
            "entity_type": repo.get("entity_type", "REPO"),
            "logical_layers": repo.get("logical_layers", []),
        }
        perimeter["repos"].append(repo_info)

    # Identifier les moteurs critiques
    for engine_name, engine_info in CRITICAL_ENGINES.items():
        for repo in repos:
            if repo.get("name") == engine_name or engine_name.lower() in repo.get("name", "").lower():
                perimeter["engines"][engine_name] = {
                    "found": True,
                    "local_path": repo.get("local_path"),
                    "status": repo.get("status"),
                }
                break
        else:
            perimeter["engines"][engine_name] = {"found": False, "required": engine_info.get("required", True)}

    return perimeter


def validate_engine_connectivity(engine_name: str, engine_info: Dict) -> Dict[str, Any]:
    """Valide la connectivité à un moteur critique."""
    result = {
        "engine": engine_name,
        "path_exists": False,
        "import_ok": False,
        "health_ok": False,
        "validate_ok": False,
        "errors": [],
    }

    path = Path(engine_info["path"])
    result["path_exists"] = path.exists()

    if not path.exists():
        result["errors"].append(f"Path not found: {path}")
        return result

    # Test import
    try:
        sys.path.insert(0, str(path))
        module = __import__(engine_info["import_test"])
        # Check for optional attribute check
        if "import_check_attr" in engine_info:
            if not hasattr(module, engine_info["import_check_attr"]):
                raise AttributeError(f"Module missing attribute: {engine_info['import_check_attr']}")
        result["import_ok"] = True
    except Exception as e:
        result["errors"].append(f"Import failed: {e}")

    # Health endpoint si disponible
    if engine_info.get("health_endpoint"):
        try:
            import urllib.request
            req = urllib.request.Request(engine_info["health_endpoint"])
            resp = urllib.request.urlopen(req, timeout=5)
            if resp.status == 200:
                result["health_ok"] = True
        except Exception as e:
            result["errors"].append(f"Health check failed: {e}")

    # Validate endpoint si disponible
    if engine_info.get("validate_endpoint"):
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                engine_info["validate_endpoint"],
                data=json.dumps({"graph": {"nodes": [], "edges": []}}).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            if resp.status == 200:
                result["validate_ok"] = True
        except Exception as e:
            result["errors"].append(f"Validate check failed: {e}")

    return result


def validate_all_engines() -> Dict[str, Any]:
    """Valide tous les moteurs critiques."""
    results = {}
    all_ok = True
    for name, info in CRITICAL_ENGINES.items():
        result = validate_engine_connectivity(name, info)
        results[name] = result
        if info.get("required", True) and not (result["path_exists"] and result["import_ok"]):
            all_ok = False
    return {"all_ok": all_ok, "engines": results}


def get_current_repo_sot_entry() -> Optional[Dict]:
    """Trouve l'entrée SOT correspondant au repo courant."""
    current = get_current_repo_info()
    if "error" in current:
        return None

    repos = load_sot()
    current_path = Path(current["path"]).resolve()

    for repo in repos:
        local_path = repo.get("local_path", "")
        if local_path and Path(local_path).resolve() == current_path:
            return repo

    # Fallback: match par nom
    for repo in repos:
        if repo.get("name") == current.get("name"):
            return repo

    return None


def self_check() -> Dict[str, Any]:
    """Auto-validation locale du repo courant."""
    current = get_current_repo_info()
    if "error" in current:
        return {"ok": False, "error": current["error"]}

    sot_entry = get_current_repo_sot_entry()
    engine_results = validate_all_engines()

    # Vérifier si le repo courant est dans la SOT
    in_sot = sot_entry is not None

    return {
        "ok": True,
        "current_repo": current,
        "in_sot": in_sot,
        "sot_entry": sot_entry,
        "engines": engine_results["engines"],
        "all_engines_ok": engine_results["all_ok"],
        "timestamp": _now_iso(),
    }


def discover() -> Dict[str, Any]:
    """Découverte complète du périmètre."""
    perimeter = discover_perimeter()
    engines = validate_all_engines()

    return {
        "perimeter": perimeter,
        "engines": engines["engines"],
        "all_engines_ok": engines["all_ok"],
        "timestamp": _now_iso(),
    }


def register_in_perimeter() -> Dict[str, Any]:
    """Enregistre le repo courant dans le registre de périmètre."""
    current = get_current_repo_info()
    if "error" in current:
        return {"ok": False, "error": current["error"]}

    sot_entry = get_current_repo_sot_entry()
    if not sot_entry:
        return {"ok": False, "error": "Current repo not found in SOT"}

    # Charger ou créer le registre
    registry = {}
    if PERIMETER_REGISTRY.exists():
        try:
            registry = json.loads(PERIMETER_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            registry = {}

    # Mettre à jour l'entrée
    repo_name = current["name"]
    registry[repo_name] = {
        "name": current["name"],
        "path": current["path"],
        "remote_url": current["remote_url"],
        "branch": current["branch"],
        "commit": current["commit"],
        "sot_role": sot_entry.get("role"),
        "sot_layer": sot_entry.get("layer"),
        "sot_status": sot_entry.get("status"),
        "logical_layers": sot_entry.get("logical_layers", []),
        "intent_hash": sot_entry.get("intent_hash"),
        "last_seen": _now_iso(),
        "status": "active",
    }

    # Sauvegarder
    PERIMETER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    PERIMETER_REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    # Aussi mettre à jour SWARM.yaml si il existe
    if SWARM_PATH.exists():
        try:
            swarm = yaml.safe_load(SWARM_PATH.read_text(encoding="utf-8")) or {}
            if "nodes" not in swarm:
                swarm["nodes"] = {}
            swarm["nodes"][current["name"]] = {
                "path": current["path"],
                "layer": sot_entry.get("layer"),
                "role": sot_entry.get("role"),
                "status": "active",
                "last_seen": _now_iso(),
            }
            SWARM_PATH.write_text(yaml.dump(swarm, allow_unicode=True), encoding="utf-8")
        except Exception:
            pass  # Non-bloquant

    return {
        "ok": True,
        "repo": current["name"],
        "registry_path": str(PERIMETER_REGISTRY),
        "timestamp": _now_iso(),
    }


def validate_bidirectional() -> Dict[str, Any]:
    """Validation bidirectionnelle : depuis ce repo vers le périmètre ET depuis le périmètre vers ce repo."""
    current = get_current_repo_info()
    if "error" in current:
        return {"ok": False, "error": current["error"]}

    perimeter = discover_perimeter()
    engines = validate_all_engines()

    # Test bidirectionnel : peut-on atteindre les moteurs depuis ici ?
    reachability = {}
    for engine_name, info in CRITICAL_ENGINES.items():
        if not info.get("required", True):
            continue
        result = validate_engine_connectivity(engine_name, CRITICAL_ENGINES[engine_name])
        reachability[engine_name] = {
            "reachable": result["path_exists"] and result["import_ok"],
            "details": result,
        }

    # Test inverse : le périmètre peut-il voir ce repo ?
    sot_entry = get_current_repo_sot_entry()
    visible_in_perimeter = sot_entry is not None

    return {
        "ok": True,
        "current_repo": current["name"],
        "reachability": reachability,
        "visible_in_perimeter": visible_in_perimeter,
        "sot_entry": sot_entry,
        "timestamp": _now_iso(),
    }


def full_pipeline() -> Dict[str, Any]:
    """Pipeline complète d'auto-reconnaissance."""
    results = {
        "self_check": self_check(),
        "discover": discover(),
        "register": register_in_perimeter(),
        "validate_bidirectional": validate_bidirectional(),
        "timestamp": _now_iso(),
    }

    # Résumé global
    all_ok = (
        results["self_check"].get("ok", False) and
        results["discover"].get("perimeter", {}).get("total_repos", 0) > 0 and
        results["register"].get("ok", False) and
        results["validate_bidirectional"].get("ok", False)
    )

    results["overall_ok"] = all_ok
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Perimeter Awareness — Auto-Reconnaissance Universelle")
    parser.add_argument("--self-check", action="store_true", help="Auto-validation locale")
    parser.add_argument("--discover", action="store_true", help="Découverte périmètre complet")
    parser.add_argument("--register", action="store_true", help="Enregistrement dans périmètre")
    parser.add_argument("--validate-bidirectional", action="store_true", help="Validation bidirectionnelle")
    parser.add_argument("--validate-engines", action="store_true", help="Validation moteurs critiques")
    parser.add_argument("--full", action="store_true", help="Pipeline complète")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Format de sortie")
    parser.add_argument("--output", help="Fichier de sortie JSON")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
    elif args.discover:
        result = discover()
    elif args.register:
        result = register_in_perimeter()
    elif args.validate_bidirectional:
        result = validate_bidirectional()
    elif args.validate_engines:
        result = validate_all_engines()
    elif args.full:
        result = full_pipeline()
    else:
        parser.print_help()
        return 1

    if args.format == "json":
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"[PERIMETER] Rapport écrit dans {args.output}")
        else:
            print(output)
    else:
        # Format texte
        if isinstance(result, dict) and "ok" in result:
            status = "OK" if result.get("ok", False) else "FAIL"
            print(f"[PERIMETER] {status}")
            for k, v in result.items():
                if k != "ok":
                    print(f"  {k}: {v}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())