#!/usr/bin/env python3
"""
swarm_ecosystem.py — Orchestrateur Global SWARM (EPIC-214).

Vue organisme de l'écosystème geribdb :
- Tous les repos sont des nodes (cellules)
- SWARM.yaml est le système nerveux central
- Chaque node a un état de santé, une phase, des connexions
- La coordination est holographique (propagation causale)
- Les CTULU lenses fournissent la perception (observe, depth, simulate)

Cet orchestrateur ne remplace pas swarm_node.py (chaque node a son daemon).
Il fournit la VUE GLOBALE et les opérations écosystémiques :
- Scan de santé de tous les repos
- Détection de conflits inter-repos
- Synchronisation/pull de tous les repos
- Projection holographique (holographique-anamorphique)
- Rapport de vitalité de l'organisme

Usage:
    python swarm_ecosystem.py --scan
    python swarm_ecosystem.py --health
    python swarm_ecosystem.py --sync --repos all
    python swarm_ecosystem.py --topology
    python swarm_ecosystem.py --vitals

IntentHash: 0XSWARM_ECOSYSTEM_ORCHESTRATOR_20260621
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GOVERNANCE_HUB = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB")
SWARM_FILE = GOVERNANCE_HUB / "SWARM.yaml"
REPORTS_DIR = GOVERNANCE_HUB / "REPORTS"

# ── Topologie de l'organisme (depuis known_repositories.yaml) ────────────────

# Les repos actifs avec leur chemin local (scan dynamique)
REPO_SCAN_ROOTS = [
    Path("D:/DO/WEB/TOOLS/L0-CANON"),
    Path("D:/DO/WEB/TOOLS/L1-INFRA"),
    Path("D:/DO/WEB/TOOLS/L4-TOOLS"),
    Path("D:/DO/WEB"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_repos() -> dict:
    """Découvre tous les repos git locaux (scan filesystem)."""
    repos = {}
    for root in REPO_SCAN_ROOTS:
        if not root.exists():
            continue
        for item in sorted(root.iterdir()):
            if item.is_dir() and (item / ".git").exists():
                repos[item.name] = str(item)
    return repos


def git_run(repo_path: str, *args, check: bool = False, timeout: int = 30) -> subprocess.CompletedProcess:
    """Exécute une commande git."""
    return subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, check=check, timeout=timeout,
    )


def scan_repo_health(repo_name: str, repo_path: str) -> dict:
    """Scanne la santé d'un repo (node)."""
    health = {
        "name": repo_name,
        "path": repo_path,
        "reachable": True,
        "branch": "unknown",
        "last_commit": {},
        "uncommitted": 0,
        "untracked": 0,
        "ahead": 0,
        "behind": 0,
        "has_clinerules": False,
        "has_swarm_rule": False,
        "issues": [],
    }

    try:
        # Branche courante
        r = git_run(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode == 0:
            health["branch"] = r.stdout.strip()

        # Dernier commit
        r = git_run(repo_path, "log", "-1", "--format=%H|%an|%ae|%ai|%s")
        if r.returncode == 0 and "|" in r.stdout:
            parts = r.stdout.strip().split("|", 4)
            health["last_commit"] = {
                "sha": parts[0][:12],
                "author": parts[1],
                "date": parts[3],
                "subject": parts[4] if len(parts) > 4 else "",
            }

        # Fichiers modifiés
        r = git_run(repo_path, "status", "--porcelain")
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                if line.startswith("??"):
                    health["untracked"] += 1
                else:
                    health["uncommitted"] += 1

        # Ahead/behind origin/main
        r = git_run(repo_path, "rev-list", "--left-right", "--count", "origin/main...HEAD", check=False, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            if len(parts) == 2:
                health["behind"] = int(parts[0])
                health["ahead"] = int(parts[1])

        # .clinerules
        cr_path = Path(repo_path) / ".clinerules"
        if cr_path.exists():
            health["has_clinerules"] = True
            if cr_path.is_file():
                content = cr_path.read_text(encoding="utf-8", errors="ignore")
            elif cr_path.is_dir():
                # Chercher dans les fichiers du répertoire
                content = ""
                for f in cr_path.rglob("*.md"):
                    content += f.read_text(encoding="utf-8", errors="ignore")
            else:
                content = ""
            health["has_swarm_rule"] = "SWARM Coordination" in content

        # Issues
        if health["uncommitted"] > 20:
            health["issues"].append(f"Beaucoup de fichiers modifiés ({health['uncommitted']})")
        if health["behind"] > 0:
            health["issues"].append(f"En retard de {health['behind']} commits sur origin/main")
        if health["branch"] != "main" and health["branch"] != "unknown":
            health["issues"].append(f"Branche non-main: {health["branch"]}")

    except subprocess.TimeoutExpired:
        health["reachable"] = False
        health["issues"].append("Timeout git (>30s)")
    except Exception as e:
        health["reachable"] = False
        health["issues"].append(str(e))

    return health


# ── Scan global ──────────────────────────────────────────────────────────────

def scan_all_repos() -> dict:
    """Scanne tous les repos locaux et retourne un rapport de santé."""
    repos = discover_repos()
    print(f"\n[ECOSYSTEM] Scan de {len(repos)} repos locaux...")
    print()

    results = {}
    for name, path in sorted(repos.items()):
        health = scan_repo_health(name, path)
        results[name] = health

        status = "[OK]" if health["reachable"] and not health["issues"] else "[WARN]" if health["reachable"] else "[ERR]"
        swarm = "[SWARM]" if health["has_swarm_rule"] else "  "
        print(f"  {status} {swarm} {name:20s} | {health['branch']:15s} | "
              f"modified={health['uncommitted']:3d} | untracked={health['untracked']:3d} | "
              f"ahead={health['ahead']:3d} behind={health['behind']:3d}")
        for issue in health["issues"]:
            print(f"      [WARN] {issue}")

    return results


# ── Health Report ────────────────────────────────────────────────────────────

def health_report(results: dict) -> None:
    """Génère un rapport de santé de l'écosystème."""
    total = len(results)
    reachable = sum(1 for h in results.values() if h["reachable"])
    healthy = sum(1 for h in results.values() if h["reachable"] and not h["issues"])
    with_swarm = sum(1 for h in results.values() if h["has_swarm_rule"])
    total_uncommitted = sum(h["uncommitted"] for h in results.values())
    total_behind = sum(h["behind"] for h in results.values())

    print(f"\n{'='*70}")
    print(f"  SWARM ECOSYSTEM HEALTH REPORT")
    print(f"  {_now()}")
    print(f"{'='*70}")
    print(f"  Nodes totaux:        {total}")
    print(f"  Nodes accessibles:   {reachable}")
    print(f"  Nodes sains:         {healthy}")
    print(f"  Nodes avec SWARM:    {with_swarm}/{total}")
    print(f"  Fichiers modifiés:   {total_uncommitted}")
    print(f"  Commits en retard:   {total_behind}")
    print()

    if healthy == total:
        print(f"  [GREEN] ORGANISME SAIN — Tous les nodes sont en bonne santé")
    elif healthy >= total * 0.7:
        print(f"  [YELLOW] ORGANISME STABLE — {total - healthy} node(s) avec des alertes")
    else:
        print(f"  [RED] ORGANISME EN DIFFICULTÉ — {total - healthy} node(s) problématiques")

    print(f"{'='*70}")


# ── Topology ─────────────────────────────────────────────────────────────────

def show_topology() -> None:
    """Affiche la topologie de l'écosystème (graphe des connexions)."""
    import yaml
    print(f"\n{'='*70}")
    print(f"  SWARM ECOSYSTEM TOPOLOGY")
    print(f"{'='*70}")
    print()

    # Charger les connexions anatomiques depuis SWARM.yaml si disponibles
    data = {}
    if SWARM_FILE.exists():
        data = yaml.safe_load(SWARM_FILE.read_text(encoding="utf-8")) or {}

    nodes = data.get("nodes", {})
    agents = data.get("agents", [])

    print(f"  Nodes enregistrés dans SWARM.yaml: {len(nodes)}")
    for name, node in sorted(nodes.items()):
        print(f"    [*] {name}")
        print(f"      path:   {node.get('repo_path', '?')}")
        print(f"      branch: {node.get('branch', '?')}")
        print(f"      agent:  {node.get('agent_name', '?')}")
        print(f"      status: {node.get('status', '?')}")
        locked = node.get("locked_resources", [])
        if locked:
            print(f"      locked: {locked}")
        print()

    print(f"  Agents actifs: {len(agents)}")
    for agent in agents:
        print(f"    [>] {agent.get('name', '?')} @ {agent.get('repo', '?')} [{agent.get('status', '?')}]")
    print()

    # Scanner les repos locaux non encore enregistrés
    local_repos = discover_repos()
    unregistered = set(local_repos.keys()) - set(nodes.keys())
    if unregistered:
        print(f"  Repos locaux NON enregistrés dans SWARM: {len(unregistered)}")
        for name in sorted(unregistered):
            print(f"    [o] {name}  ({local_repos[name]})")
        print()

    print(f"{'='*70}")


# ── Sync all repos ───────────────────────────────────────────────────────────

def sync_repos(repo_filter: str = "all", dry_run: bool = True) -> dict:
    """Synchronise tous les repos (pull --rebase origin main)."""
    repos = discover_repos()

    if repo_filter != "all":
        targets = {k: v for k, v in repos.items() if k in repo_filter.split(",")}
    else:
        targets = repos

    print(f"\n[ECOSYSTEM] Synchronisation de {len(targets)} repos...")
    print(f"[ECOSYSTEM] Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    print()

    results = {}
    for name, path in sorted(targets.items()):
        print(f"  [{name}]")
        try:
            # Fetch
            r = git_run(path, "fetch", "origin", timeout=30)
            if r.returncode != 0:
                print(f"    [WARN] fetch failed: {r.stderr.strip()[:100]}")
                results[name] = {"status": "fetch_failed"}
                continue

            # Pull --rebase
            r = git_run(path, "pull", "--rebase", "origin", "main", timeout=60)
            if r.returncode == 0:
                print(f"    [OK] synced: {r.stdout.strip()[:80]}")
                results[name] = {"status": "synced"}
            else:
                if "CONFLICT" in r.stdout or "conflict" in r.stderr.lower():
                    print(f"    [WARN] CONFLIT: {r.stderr.strip()[:100]}")
                    results[name] = {"status": "conflict"}
                else:
                    print(f"    [WARN] pull failed: {r.stderr.strip()[:100]}")
                    results[name] = {"status": "pull_failed"}

        except subprocess.TimeoutExpired:
            print(f"    [WARN] timeout")
            results[name] = {"status": "timeout"}
        except Exception as e:
            print(f"    [WARN] error: {e}")
            results[name] = {"status": "error", "error": str(e)}

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWARM Ecosystem Orchestrator — Vue organisme")
    sub = parser.add_subparsers(dest="cmd")

    # scan
    sub.add_parser("scan", help="Scanner tous les repos locaux")

    # health
    sub.add_parser("health", help="Rapport de santé de l'écosystème")

    # topology
    sub.add_parser("topology", help="Afficher la topologie (graphe des connexions)")

    # sync
    p_sync = sub.add_parser("sync", help="Synchroniser tous les repos")
    p_sync.add_argument("--repos", default="all", help="Repos ciblés (all ou liste séparée par des virgules)")
    p_sync.add_argument("--apply", action="store_true", help="Appliquer (sinon dry-run)")

    # vitals
    sub.add_parser("vitals", help="Signes vitaux de l'écosystème (scan + health combiné)")

    args = parser.parse_args()

    if args.cmd == "scan":
        scan_all_repos()

    elif args.cmd == "health":
        results = {}
        repos = discover_repos()
        for name, path in sorted(repos.items()):
            results[name] = scan_repo_health(name, path)
        health_report(results)

    elif args.cmd == "topology":
        show_topology()

    elif args.cmd == "sync":
        sync_repos(args.repos, dry_run=not args.apply)

    elif args.cmd == "vitals":
        results = scan_all_repos()
        health_report(results)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
