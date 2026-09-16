#!/usr/bin/env python3
# intent_hash: 0xPERIMETER_DEPLOY_20260916
"""
Deploy perimeter-awareness to all repos in SOT.

Ce script déploie l'outil perimeter-awareness sur tous les repos
listés dans known_repositories.yaml pour permettre l'auto-reconnaissance
depuis n'importe quel repo du périmètre.

Usage:
    python deploy_perimeter.py --dry-run    # Simulation
    python deploy_perimeter.py --deploy     # Déploiement réel
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Charger la SOT
SOT_PATH = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB/known_repositories.yaml")
SOURCE_TOOL = Path("D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/perimeter-awareness")


def load_sot():
    import yaml
    if not Path(SOT_PATH).exists():
        return []
    data = yaml.safe_load(Path(SOT_PATH).read_text(encoding="utf-8"))
    repos = []
    if isinstance(data, dict):
        for key in ["P0_REPOS", "P1_REPOS", "P2_REPOS", "P3_REPOS", "P4_REPOS", "P5_REPOS"]:
            if key in data and isinstance(data[key], list):
                repos.extend(data[key])
    return repos


def deploy_to_repo(repo: dict, dry_run: bool = True) -> dict:
    """Déploie perimeter-awareness dans un repo."""
    name = repo.get("name", "")
    local_path = repo.get("local_path", "")

    if not local_path:
        return {"repo": name, "ok": False, "error": "No local_path"}

    target_path = Path(local_path)
    if not target_path.exists():
        return {"repo": name, "ok": False, "error": f"Path does not exist: {local_path}"}

    # Skip source directory
    if target_path.resolve() == SOURCE_TOOL.resolve():
        return {"repo": name, "ok": True, "skipped": True, "reason": "Source directory"}

    # Skip if target is the source tool directory itself
    if "CTULU" in str(target_path) and "perimeter-awareness" in str(target_path / "tools" / "perimeter-awareness"):
        return {"repo": name, "ok": True, "skipped": True, "reason": "Source tool directory"}

    # Créer le répertoire scripts s'il n'existe pas
    scripts_dir = target_path / "scripts"
    if not scripts_dir.exists():
        if not dry_run:
            scripts_dir.mkdir(parents=True, exist_ok=True)

    # Copier perimeter-awareness
    target_tool = target_path / "tools" / "perimeter-awareness"
    if not dry_run:
        if target_tool.exists():
            shutil.rmtree(target_tool)
        shutil.copytree(SOURCE_TOOL, target_tool)

    # Créer un wrapper d'appel pour faciliter l'usage
    wrapper_content = '''#!/usr/bin/env python3
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
'''
    wrapper_path = target_path / "scripts" / "perimeter_awareness.py"
    if not dry_run:
        wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        wrapper_path.write_text(wrapper_content, encoding="utf-8")

    return {
        "repo": repo.get("name"),
        "path": str(target_path),
        "ok": True,
        "tool_path": str(target_tool) if not dry_run else f"would create: {target_tool}",
        "wrapper": str(wrapper_path) if not dry_run else f"would create: {wrapper_path}",
    }


def main():
    parser = argparse.ArgumentParser(description="Deploy perimeter-awareness to all SOT repos")
    parser.add_argument("--dry-run", action="store_true", help="Simulation only")
    parser.add_argument("--deploy", action="store_true", help="Actual deployment")
    parser.add_argument("--repo", help="Deploy to specific repo only")
    args = parser.parse_args()

    if not args.dry_run and not args.deploy:
        print("Use --dry-run or --deploy")
        return 1

    repos = load_sot()
    if args.repo:
        repos = [r for r in repos if r.get("name") == args.repo]
        if not repos:
            print(f"Repo {args.repo} not found in SOT")
            return 1

    print(f"[DEPLOY] Found {len(repos)} repos in SOT")
    print(f"[DEPLOY] Mode: {'DRY-RUN' if args.dry_run else 'DEPLOY'}")

    results = []
    for repo in repos:
        name = repo.get("name", "unknown")
        if repo.get("status") == "dormant":
            continue  # Skip dormant repos

        result = deploy_to_repo(repo, dry_run=args.dry_run)
        results.append(result)
        status = "OK" if result["ok"] else "FAIL"
        print(f"  [{status}] {name}: {result.get('tool_path', result.get('error', 'unknown'))}")

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n[DEPLOY] Summary: {ok_count}/{len(results)} OK")

    if not args.dry_run:
        print("[DEPLOY] Deployment complete")
    else:
        print("[DEPLOY] Dry-run complete. Use --deploy to actually deploy.")

    return 0


if __name__ == "__main__":
    sys.exit(main())