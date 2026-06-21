#!/usr/bin/env python3
"""
swarm_node.py — Daemon de coordination SWARM par repo/node.

Chaque instance KiloCode (ou agent) lance ce daemon au démarrage.
Le daemon :
1. S'enregistre dans SWARM.yaml (GOVERNANCE-HUB) comme node actif
2. Écoute les événements locaux (commit, push, merge, ADR, EPIC)
3. Signale son heartbeat périodique
4. Propage les événements aux autres nodes via holograph-anything
5. Peut être interrogé pour connaître l'état global du swarm

Usage:
    python swarm_node.py --action register --repo NEXUS --agent kilo-env2
    python swarm_node.py --action heartbeat --repo NEXUS --agent kilo-env2
    python swarm_node.py --action status
    python swarm_node.py --action release --repo NEXUS --agent kilo-env2
    python swarm_node.py --action detect-conflicts --repo NEXUS

IntentHash: 0xSWARM_NODE_DAEMON_20260621
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────
GOVERNANCE_HUB = Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB")
SWARM_FILE = GOVERNANCE_HUB / "SWARM.yaml"
SESSION_FILE = GOVERNANCE_HUB / ".swarm_session"
HOLOGRAPH_SCRIPT = Path("D:/DO/WEB/TOOLS/L4-TOOLS/CTULU/tools/holograph-anything/holograph.py")

# ── Constants ─────────────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL = 300  # seconds
LOCK_TIMEOUT = 1800  # 30 minutes
DEFAULT_BRANCH = "main"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_swarm() -> dict:
    """Charge SWARM.yaml."""
    import yaml
    if not SWARM_FILE.exists():
        return {"version": "2.0", "nodes": {}, "agents": [], "conflicts": [], "queue": [], "events": []}
    return yaml.safe_load(SWARM_FILE.read_text(encoding="utf-8")) or {}


def save_swarm(data: dict) -> None:
    """Sauvegarde SWARM.yaml."""
    import yaml
    data["last_updated"] = _now()
    SWARM_FILE.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")


def get_agent_id(agent_name: str) -> str:
    """Génère un ID unique et persistant pour cet agent."""
    hostname = socket.gethostname()
    if SESSION_FILE.exists():
        sid = SESSION_FILE.read_text(encoding="utf-8").strip()
        if sid:
            return sid
    pid = os.getpid()
    sid = f"{hostname}-{agent_name}-{pid}"
    SESSION_FILE.write_text(sid, encoding="utf-8")
    return sid


def git_run(repo_path: str, *args, check: bool = False) -> subprocess.CompletedProcess:
    """Exécute une commande git dans un repo donné."""
    return subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, check=check,
    )


def git_get_current_branch(repo_path: str) -> str:
    """Retourne la branche courante d'un repo."""
    r = git_run(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def git_get_last_commit(repo_path: str) -> dict:
    """Retourne les infos du dernier commit."""
    r = git_run(repo_path, "log", "-1", "--format=%H|%an|%ae|%ai|%s")
    if r.returncode == 0 and "|" in r.stdout:
        parts = r.stdout.strip().split("|", 4)
        return {
            "sha": parts[0],
            "author": parts[1],
            "email": parts[2],
            "date": parts[3],
            "subject": parts[4] if len(parts) > 4 else "",
        }
    return {}


def git_has_uncommitted(repo_path: str) -> bool:
    """Vérifie s'il y a des changements non commités."""
    r = git_run(repo_path, "status", "--porcelain")
    return bool(r.stdout.strip())


def get_repo_phase(repo_path: str) -> str:
    """Détecte la phase Epic depuis les fichiers EPIC locaux."""
    epics_dir = Path(repo_path) / "EPICS"
    if not epics_dir.exists():
        epics_dir = Path(repo_path) / "epics"
    if epics_dir.exists():
        epic_files = list(epics_dir.glob("*.md"))
        if epic_files:
            # Extraire la phase depuis le dernier EPIC modifié
            latest = max(epic_files, key=lambda f: f.stat().st_mtime)
            content = latest.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if "phase" in line.lower() and ":" in line:
                    return line.split(":", 1)[1].strip()[:20]
    return "unknown"


# ── Node Registration ────────────────────────────────────────────────────────

def register_node(repo_name: str, repo_path: str, agent_name: str) -> dict:
    """Enregistre un node (repo + agent) dans SWARM.yaml."""
    data = load_swarm()
    agent_id = get_agent_id(agent_name)
    now = _now()

    # Initialiser la structure nodes si absente
    if "nodes" not in data:
        data["nodes"] = {}

    # Enregistrer le node
    data["nodes"][repo_name] = {
        "repo_path": repo_path,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "branch": git_get_current_branch(repo_path),
        "last_commit": git_get_last_commit(repo_path),
        "has_uncommitted": git_has_uncommitted(repo_path),
        "phase": get_repo_phase(repo_path),
        "status": "active",
        "registered_at": now,
        "last_heartbeat": now,
        "locked_resources": [],
    }

    # Enregistrer l'agent
    if "agents" not in data:
        data["agents"] = []
    # Supprimer l'ancienne entrée si existe
    data["agents"] = [a for a in data["agents"] if a.get("id") != agent_id]
    data["agents"].append({
        "id": agent_id,
        "name": agent_name,
        "repo": repo_name,
        "status": "active",
        "registered_at": now,
        "last_seen": now,
        "pid": os.getpid(),
    })

    save_swarm(data)
    print(f"[SWARM_NODE] Registered: {repo_name} @ {agent_id}")
    return data


def heartbeat_node(repo_name: str, agent_name: str) -> dict:
    """Met à jour le heartbeat d'un node."""
    data = load_swarm()
    now = _now()

    if "nodes" in data and repo_name in data["nodes"]:
        node = data["nodes"][repo_name]
        node["last_heartbeat"] = now
        node["branch"] = git_get_current_branch(node.get("repo_path", ""))
        node["last_commit"] = git_get_last_commit(node.get("repo_path", ""))
        node["has_uncommitted"] = git_has_uncommitted(node.get("repo_path", ""))
        node["phase"] = get_repo_phase(node.get("repo_path", ""))

    if "agents" in data:
        for agent in data["agents"]:
            if agent.get("name") == agent_name:
                agent["last_seen"] = now
                agent["status"] = "active"

    save_swarm(data)
    return data


def release_node(repo_name: str, agent_name: str) -> dict:
    """Libère un node (désenregistrement)."""
    data = load_swarm()

    if "nodes" in data and repo_name in data["nodes"]:
        del data["nodes"][repo_name]

    if "agents" in data:
        agent_id = get_agent_id(agent_name)
        data["agents"] = [a for a in data["agents"] if a.get("id") != agent_id]

    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    save_swarm(data)
    print(f"[SWARM_NODE] Released: {repo_name} @ {agent_name}")
    return data


# ── Conflict Detection ───────────────────────────────────────────────────────

def detect_conflicts(repo_name: str, repo_path: str) -> list[dict]:
    """Détecte les conflits potentiels entre ce node et les autres nodes actifs."""
    data = load_swarm()
    conflicts = []
    now = datetime.now(timezone.utc)

    if "nodes" not in data:
        return conflicts

    for other_name, other_node in data["nodes"].items():
        if other_name == repo_name:
            continue

        # Vérifier si l'autre node est stale (pas de heartbeat > 30 min)
        last_hb = other_node.get("last_heartbeat", "")
        if last_hb:
            try:
                hb_time = datetime.fromisoformat(last_hb)
                age_seconds = (now - hb_time).total_seconds()
                if age_seconds > LOCK_TIMEOUT:
                    conflicts.append({
                        "type": "stale_node",
                        "node": other_name,
                        "age_minutes": round(age_seconds / 60),
                        "message": f"Node {other_name} stale ({round(age_seconds/60)} min sans heartbeat)",
                    })
            except (ValueError, TypeError):
                pass

        # Vérifier les ressources verrouillées
        locked = other_node.get("locked_resources", [])
        if locked:
            conflicts.append({
                "type": "locked_resources",
                "node": other_name,
                "resources": locked,
                "message": f"Node {other_name} verrouille: {locked}",
            })

    return conflicts


# ── Holographic Event Propagation ────────────────────────────────────────────

def propagate_event(event_type: str, repo_name: str, details: dict) -> dict:
    """Propage un événement via holograph-anything (propagation causale cross-repo)."""
    event = {
        "type": event_type,
        "source_node": repo_name,
        "timestamp": _now(),
        "details": details,
    }

    # Sauvegarder dans SWARM.yaml events log
    data = load_swarm()
    if "events" not in data:
        data["events"] = []
    data["events"].append(event)
    # Garder seulement les 100 derniers événements
    data["events"] = data["events"][-100:]
    save_swarm(data)

    # Essayer d'invoquer holograph-anything si disponible
    if HOLOGRAPH_SCRIPT.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(HOLOGRAPH_SCRIPT),
                 "trigger", f"--event={event_type}", f"--source={repo_name}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                event["holograph_result"] = json.loads(result.stdout) if result.stdout.strip() else {}
        except Exception as e:
            event["holograph_error"] = str(e)

    print(f"[SWARM_NODE] Event propagated: {event_type} from {repo_name}")
    return event


# ── Ecosystem Status ──────────────────────────────────────────────────────────

def get_ecosystem_status() -> dict:
    """Retourne l'état complet de l'écosystème (vue organisme)."""
    data = load_swarm()
    now = datetime.now(timezone.utc)

    nodes = data.get("nodes", {})
    agents = data.get("agents", [])
    events = data.get("events", [])

    # Calculer la santé globale
    active_nodes = 0
    stale_nodes = 0
    total_uncommitted = 0

    for name, node in nodes.items():
        last_hb = node.get("last_heartbeat", "")
        if last_hb:
            try:
                hb_time = datetime.fromisoformat(last_hb)
                age = (now - hb_time).total_seconds()
                if age < LOCK_TIMEOUT:
                    active_nodes += 1
                else:
                    stale_nodes += 1
            except (ValueError, TypeError):
                stale_nodes += 1
        if node.get("has_uncommitted"):
            total_uncommitted += 1

    return {
        "timestamp": _now(),
        "global_phase": data.get("global_phase", "unknown"),
        "total_nodes": len(nodes),
        "active_nodes": active_nodes,
        "stale_nodes": stale_nodes,
        "total_agents": len(agents),
        "uncommitted_changes": total_uncommitted,
        "recent_events": events[-10:],
        "nodes": nodes,
        "health": "healthy" if stale_nodes == 0 else "degraded" if stale_nodes < active_nodes else "critical",
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SWARM Node Daemon — Coordination écosystémique")
    parser.add_argument("--action", required=True,
                        choices=["register", "heartbeat", "release", "status", "detect-conflicts",
                                 "propagate", "ecosystem"],
                        help="Action à effectuer")
    parser.add_argument("--repo", default="", help="Nom du repo (ex: NEXUS)")
    parser.add_argument("--repo-path", default="", help="Chemin local du repo")
    parser.add_argument("--agent", default="kilo", help="Nom de l'agent (ex: kilo-env2)")
    parser.add_argument("--event-type", default="", help="Type d'événement (pour propagate)")
    parser.add_argument("--event-details", default="{}", help="Détails JSON de l'événement")
    args = parser.parse_args()

    if args.action == "register":
        if not args.repo or not args.repo_path:
            print("[ERROR] --repo et --repo-path requis pour register")
            sys.exit(2)
        register_node(args.repo, args.repo_path, args.agent)

    elif args.action == "heartbeat":
        if not args.repo:
            print("[ERROR] --repo requis pour heartbeat")
            sys.exit(2)
        heartbeat_node(args.repo, args.agent)

    elif args.action == "release":
        if not args.repo:
            print("[ERROR] --repo requis pour release")
            sys.exit(2)
        release_node(args.repo, args.agent)

    elif args.action == "status":
        data = load_swarm()
        nodes = data.get("nodes", {})
        agents = data.get("agents", [])
        print(f"\n=== SWARM Node Status ({_now()}) ===")
        print(f"  Nodes actifs: {len(nodes)}")
        for name, node in nodes.items():
            print(f"    {name}: {node.get('status', '?')} | branch={node.get('branch', '?')} | "
                  f"agent={node.get('agent_name', '?')} | uncommitted={node.get('has_uncommitted', False)}")
        print(f"  Agents actifs: {len(agents)}")
        for agent in agents:
            print(f"    {agent.get('name', '?')}: {agent.get('status', '?')} @ {agent.get('repo', '?')}")

    elif args.action == "detect-conflicts":
        if not args.repo:
            print("[ERROR] --repo requis pour detect-conflicts")
            sys.exit(2)
        repo_path = args.repo_path or ""
        conflicts = detect_conflicts(args.repo, repo_path)
        if conflicts:
            print(f"[SWARM_NODE] {len(conflicts)} conflit(s) détecté(s):")
            for c in conflicts:
                print(f"  - [{c['type']}] {c['message']}")
        else:
            print(f"[SWARM_NODE] Aucun conflit pour {args.repo}")

    elif args.action == "propagate":
        if not args.repo or not args.event_type:
            print("[ERROR] --repo et --event-type requis pour propagate")
            sys.exit(2)
        details = json.loads(args.event_details) if args.event_details else {}
        propagate_event(args.event_type, args.repo, details)

    elif args.action == "ecosystem":
        status = get_ecosystem_status()
        print(f"\n{'='*60}")
        print(f"  SWARM ECOSYSTEM STATUS")
        print(f"{'='*60}")
        print(f"  Santé globale: {status['health'].upper()}")
        print(f"  Phase globale: {status['global_phase']}")
        print(f"  Nodes: {status['active_nodes']} actifs / {status['stale_nodes']} stale / {status['total_nodes']} total")
        print(f"  Agents: {status['total_agents']}")
        print(f"  Repos avec changements non commités: {status['uncommitted_changes']}")
        print()
        for name, node in status.get("nodes", {}).items():
            print(f"  [{name}]")
            print(f"    branch: {node.get('branch', '?')} | phase: {node.get('phase', '?')}")
            print(f"    agent: {node.get('agent_name', '?')} | uncommitted: {node.get('has_uncommitted', False)}")
            last_hb = node.get("last_heartbeat", "")
            if last_hb:
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_hb)).total_seconds()
                    print(f"    last_heartbeat: {round(age)}s ago")
                except Exception:
                    pass
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
