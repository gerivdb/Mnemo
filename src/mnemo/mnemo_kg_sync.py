"""
mnemo_kg_sync.py — Synchronisation Bidirectionnelle Mnemo ↔ KG-L.

Cold ↔ Warm ↔ Hot tier synchronization avec validation causale.
Export KG-L → Mnemo (cold→warm), Push Mnemo → KG-L (hot→cold).

IntentHash: 0xMNEMO_KG_SYNC_BIDIR_20260828
Version: 1.0.0
Author: gerivdb
Date: 2026-08-28
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.mnemo.mnemo_core import MnemoCore, MemoryEntry, MemoryTier, Provenance


# ──────────────────────────────────────────────────────────────────────────────
# KG-L Graph Interface
# ──────────────────────────────────────────────────────────────────────────────

KG_L_GRAPH_PATH = Path(r"D:\DO\WEB\TOOLS\L4-TOOLS\KG-L\docs\ecosystem_kg_full.json")
KG_L_EDGE_TYPES = {"causes", "confounds", "prevents", "correlates"}


@dataclass
class SyncStats:
    """Statistiques de synchronisation."""
    kg_l_nodes_exported: int = 0
    kg_l_edges_exported: int = 0
    mnemo_entries_created: int = 0
    mnemo_entries_updated: int = 0
    mnemo_entries_promoted_warm: int = 0
    mnemo_entries_promoted_cold: int = 0
    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_ms: float = 0.0


class KGLEngine:
    """Interface pour lire/écrire le graphe KG-L."""

    def __init__(self, graph_path: Path = KG_L_GRAPH_PATH):
        self.graph_path = graph_path
        self._graph_cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl = 30  # seconds

    def load_graph(self, force: bool = False) -> Dict[str, Any]:
        """Charge le graphe KG-L depuis le fichier JSON."""
        now = time.time()
        if not force and self._graph_cache and (now - self._cache_time) < self._cache_ttl:
            return self._graph_cache
        
        if not self.graph_path.exists():
            raise FileNotFoundError(f"KG-L graph not found: {self.graph_path}")
        
        content = self.graph_path.read_text(encoding="utf-8")
        self._graph_cache = json.loads(content)
        self._cache_time = now
        return self._graph_cache

    def get_nodes(self) -> Dict[str, Any]:
        return self.load_graph().get("nodes", {})

    def get_edges(self) -> List[Dict[str, Any]]:
        return self.load_graph().get("edges", [])

    def add_node(self, node_id: str, node_data: Dict[str, Any]) -> bool:
        """Ajoute un nœud au graphe (en mémoire, flush requis)."""
        graph = self.load_graph(force=True)
        if "nodes" not in graph:
            graph["nodes"] = {}
        graph["nodes"][node_id] = node_data
        self._graph_cache = graph
        return True

    def add_edge(self, src: str, dst: str, kind: str, weight: float = 1.0) -> bool:
        """Ajoute une arête au graphe."""
        if kind not in KG_L_EDGE_TYPES:
            return False
        graph = self.load_graph(force=True)
        if "edges" not in graph:
            graph["edges"] = []
        graph["edges"].append({"src": src, "dst": dst, "kind": kind, "weight": weight})
        self._graph_cache = graph
        return True

    def flush(self) -> bool:
        """Écrit le graphe mis à jour sur disque."""
        if self._graph_cache is None:
            return False
        try:
            self.graph_path.parent.mkdir(parents=True, exist_ok=True)
            self.graph_path.write_text(
                json.dumps(self._graph_cache, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
            self._cache_time = 0  # Invalider cache
            return True
        except Exception as e:
            print(f"[KGLEngine] Flush failed: {e}")
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Synchronisation KG-L → Mnemo (Cold → Warm)
# ──────────────────────────────────────────────────────────────────────────────

def export_kg_l_to_mnemo(
    mnemo: MnemoCore,
    kg_l: KGLEngine,
    domains: Optional[List[str]] = None,
    max_nodes: int = 5000,
) -> SyncStats:
    """
    Export KG-L graph → Mnemo warm cache.
    
    Convertit nœuds/arêtes KG-L en entrées Mnemo (tier WARM).
    Filtre par domaines optionnels.
    """
    stats = SyncStats()
    start = time.time()
    
    try:
        graph = kg_l.load_graph()
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        
        # Filtrer nœuds par domaine si spécifié
        filtered_nodes = {}
        for nid, ndata in nodes.items():
            if domains:
                node_domain = ndata.get("domain", "default")
                if node_domain not in domains:
                    continue
            filtered_nodes[nid] = ndata
            if len(filtered_nodes) >= max_nodes:
                break
        
        stats.kg_l_nodes_exported = len(filtered_nodes)
        stats.kg_l_edges_exported = len(edges)
        
        # Créer entrées Mnemo pour nœuds
        for nid, ndata in filtered_nodes.items():
            key = f"kg_l:node:{nid}"
            entry_data = {
                **ndata,
                "kg_l_node_id": nid,
                "kg_l_edges": [e for e in edges if e.get("src") == nid or e.get("dst") == nid],
            }
            
            existing = mnemo._get_entry_raw(key)
            if existing:
                # Update
                existing.value = entry_data
                existing.touch()
                existing.tier = MemoryTier.WARM
                existing.provenance = Provenance.KG_L
                mnemo._warm_cache[key] = existing
                stats.mnemo_entries_updated += 1
            else:
                # Create
                entry = MemoryEntry(
                    key=key,
                    value=entry_data,
                    tier=MemoryTier.WARM,
                    provenance=Provenance.KG_L,
                    tags=["kg_l", "node", ndata.get("node_type", "unknown")],
                    metadata={"domain": ndata.get("domain", "kg_l"), "source": "kg_l_export"},
                )
                mnemo._warm_cache[key] = entry
                mnemo._add_to_indexes(key, entry)
                stats.mnemo_entries_created += 1
            
            stats.mnemo_entries_promoted_warm += 1
        
        # Promouvoir entrées HOT → WARM si elles existent aussi en KG-L
        for key in list(mnemo._hot_cache.keys()):
            if key.startswith("kg_l:"):
                mnemo.promote_to_warm(key)
                stats.mnemo_entries_promoted_warm += 1
        
        stats.completed_at = datetime.now(timezone.utc).isoformat()
        stats.duration_ms = (time.time() - start) * 1000
        return stats
        
    except Exception as e:
        stats.errors.append(f"Export KG-L→Mnemo failed: {e}")
        stats.completed_at = datetime.now(timezone.utc).isoformat()
        stats.duration_ms = (time.time() - start) * 1000
        return stats


# ──────────────────────────────────────────────────────────────────────────────
# Synchronisation Mnemo → KG-L (Hot → Cold)
# ──────────────────────────────────────────────────────────────────────────────

def push_mnemo_to_kg_l(
    mnemo: MnemoCore,
    kg_l: KGLEngine,
    require_n243_gate: bool = True,
    gate_client: Optional[Any] = None,
) -> SyncStats:
    """
    Push Mnemo hot/warm entries → KG-L (cold tier).
    
    Valide causalité (edge types KG-L) avant insertion.
    Optionnel: gate N243 pour validation ternaire.
    """
    stats = SyncStats()
    start = time.time()
    
    try:
        # Collecter entrées Mnemo à pousser (HOT + WARM avec tag kg_l ou provenance KG_L)
        entries_to_push = []
        
        for key, entry in mnemo._hot_cache.items():
            if _should_push_to_kg_l(entry):
                entries_to_push.append((key, entry, MemoryTier.HOT))
        
        for key, entry in mnemo._warm_cache.items():
            if _should_push_to_kg_l(entry):
                entries_to_push.append((key, entry, MemoryTier.WARM))
        
        # Gate N243 si requis
        if require_n243_gate and gate_client:
            for key, entry, tier in entries_to_push:
                decision = _call_n243_gate(gate_client, "create", {
                    "key": key,
                    "value": entry.value,
                    "tier": tier.value,
                    "provenance": entry.provenance.value,
                })
                if decision != "APPROUVER":
                    stats.conflicts_detected += 1
                    stats.errors.append(f"N243 gate {decision} for {key}")
                    continue
                stats.conflicts_resolved += 1
        
        # Insérer dans KG-L
        for key, entry, tier in entries_to_push:
            node_id = _mnemo_key_to_kg_l_node(key)
            node_data = _mnemo_entry_to_kg_l_node(entry)
            
            if kg_l.add_node(node_id, node_data):
                stats.mnemo_entries_promoted_cold += 1
                
                # Promouvoir Mnemo HOT/WARM → COLD
                if tier == MemoryTier.HOT:
                    mnemo.promote_to_warm(key)
                    mnemo.promote_to_cold(key)
                elif tier == MemoryTier.WARM:
                    mnemo.promote_to_cold(key)
                
                # Ajouter arêtes causales depuis metadata relations
                relations = entry.metadata.get("relations", [])
                for rel in relations:
                    target = rel.get("target")
                    kind = rel.get("relation", "correlates")
                    if target:
                        target_id = _mnemo_key_to_kg_l_node(target)
                        if kind in KG_L_EDGE_TYPES:
                            kg_l.add_edge(node_id, target_id, kind)
                            stats.kg_l_edges_exported += 1
            else:
                stats.errors.append(f"Failed to add node {node_id}")
        
        # Flush KG-L
        if kg_l.flush():
            stats.completed_at = datetime.now(timezone.utc).isoformat()
            stats.duration_ms = (time.time() - start) * 1000
            return stats
        else:
            stats.errors.append("KG-L flush failed")
            stats.completed_at = datetime.now(timezone.utc).isoformat()
            stats.duration_ms = (time.time() - start) * 1000
            return stats
            
    except Exception as e:
        stats.errors.append(f"Push Mnemo→KG-L failed: {e}")
        stats.completed_at = datetime.now(timezone.utc).isoformat()
        stats.duration_ms = (time.time() - start) * 1000
        return stats


def _should_push_to_kg_l(entry: MemoryEntry) -> bool:
    """Détermine si une entrée Mnemo doit être poussée vers KG-L."""
    # Explicit tag kg_l
    if "kg_l" in entry.tags:
        return True
    # Provenance KG_L
    if entry.provenance == Provenance.KG_L:
        return True
    # Metadata domain causal
    if entry.metadata.get("domain") in ("causal", "kg_l", "decisions"):
        return True
    # Relations causales dans metadata
    relations = entry.metadata.get("relations", [])
    if any(r.get("relation") in KG_L_EDGE_TYPES for r in relations):
        return True
    return False


def _mnemo_key_to_kg_l_node(key: str) -> str:
    """Convertit clé Mnemo en node ID KG-L."""
    if key.startswith("kg_l:node:"):
        return key[10:]  # Remove "kg_l:node:" prefix
    if key.startswith("kg_l:"):
        return key[5:]   # Remove "kg_l:" prefix
    return f"mnemo:{key}"


def _mnemo_entry_to_kg_l_node(entry: MemoryEntry) -> Dict[str, Any]:
    """Convertit MemoryEntry en format nœud KG-L."""
    base = {
        "node_type": entry.metadata.get("node_type", "mnemo_entry"),
        "source": "mnemo",
        "provenance": entry.provenance.value,
        "tier": entry.tier.value,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "version": entry.version,
        "tags": entry.tags,
        "metadata": entry.metadata,
    }
    # Merge value if dict
    if isinstance(entry.value, dict):
        base.update(entry.value)
    else:
        base["value"] = entry.value
    return base


def _call_n243_gate(gate_client: Any, operation: str, payload: Dict) -> str:
    """Appelle le gate N243 via client (WAZAA topic ou HTTP)."""
    # TODO: Implémenter appel réel gate N243 via WAZAA
    # Pour l'instant, simule APPROUVER
    return "APPROUVER"


# ──────────────────────────────────────────────────────────────────────────────
# Sync Bidirectionnel Complet
# ──────────────────────────────────────────────────────────────────────────────

class MnemoKGSync:
    """Orchestrateur de synchronisation bidirectionnelle Mnemo ↔ KG-L."""

    def __init__(
        self,
        mnemo: MnemoCore,
        kg_l_graph_path: Path = KG_L_GRAPH_PATH,
        n243_gate_client: Optional[Any] = None,
        auto_sync_interval: int = 300,  # 5 min
    ):
        self.mnemo = mnemo
        self.kg_l = KGLEngine(kg_l_graph_path)
        self.n243_gate_client = n243_gate_client
        self.auto_sync_interval = auto_sync_interval
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_sync: Optional[SyncStats] = None

    def sync_kg_l_to_mnemo(self, domains: Optional[List[str]] = None) -> SyncStats:
        """Sync KG-L → Mnemo (cold → warm)."""
        print("[MnemoKGSync] Starting KG-L → Mnemo sync...")
        stats = export_kg_l_to_mnemo(self.mnemo, self.kg_l, domains)
        self._last_sync = stats
        print(f"[MnemoKGSync] KG-L→Mnemo complete: {stats.mnemo_entries_created} created, "
              f"{stats.mnemo_entries_updated} updated, {stats.mnemo_entries_promoted_warm} promoted")
        return stats

    def sync_mnemo_to_kg_l(self) -> SyncStats:
        """Sync Mnemo → KG-L (hot/warm → cold)."""
        print("[MnemoKGSync] Starting Mnemo → KG-L sync...")
        stats = push_mnemo_to_kg_l(self.mnemo, self.kg_l, n243_gate_client=self.n243_gate_client)
        self._last_sync = stats
        print(f"[MnemoKGSync] Mnemo→KG-L complete: {stats.mnemo_entries_promoted_cold} promoted, "
              f"{stats.conflicts_detected} conflicts")
        return stats

    def full_sync(self, domains: Optional[List[str]] = None) -> Dict[str, SyncStats]:
        """Sync bidirectionnel complet."""
        print("[MnemoKGSync] Starting FULL bidirectional sync...")
        kg_to_mnemo = self.sync_kg_l_to_mnemo(domains)
        mnemo_to_kg = self.sync_mnemo_to_kg_l()
        return {
            "kg_l_to_mnemo": kg_to_mnemo,
            "mnemo_to_kg_l": mnemo_to_kg,
        }

    def start_auto_sync(self, domains: Optional[List[str]] = None):
        """Démarre sync automatique périodique (thread daemon)."""
        if self._running:
            return
        self._running = True
        self._sync_thread = threading.Thread(target=self._auto_sync_loop, args=(domains,), daemon=True)
        self._sync_thread.start()
        print(f"[MnemoKGSync] Auto-sync started (interval: {self.auto_sync_interval}s)")

    def stop_auto_sync(self):
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        print("[MnemoKGSync] Auto-sync stopped")

    def _auto_sync_loop(self, domains: Optional[List[str]]):
        while self._running:
            time.sleep(self.auto_sync_interval)
            if not self._running:
                break
            try:
                self.full_sync(domains)
            except Exception as e:
                print(f"[MnemoKGSync] Auto-sync error: {e}")

    def get_last_sync(self) -> Optional[SyncStats]:
        return self._last_sync


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mnemo ↔ KG-L Sync CLI")
    parser.add_argument("--mnemo-persist", type=str, default=None, help="Mnemo persistence file")
    parser.add_argument("--kg-l-path", type=str, default=str(KG_L_GRAPH_PATH), help="KG-L graph path")
    parser.add_argument("--direction", choices=["kg2mnemo", "mnemo2kg", "full"], default="full")
    parser.add_argument("--domains", type=str, default=None, help="Comma-separated domains filter")
    parser.add_argument("--auto", action="store_true", help="Run auto-sync loop")
    parser.add_argument("--interval", type=int, default=300, help="Auto-sync interval (seconds)")
    args = parser.parse_args()

    # Init
    mnemo = MnemoCore(persistence_path=args.mnemo_persist) if args.mnemo_persist else MnemoCore()
    kg_l = KGLEngine(Path(args.kg_l_path))
    sync = MnemoKGSync(mnemo, kg_l, auto_sync_interval=args.interval)

    domains = args.domains.split(",") if args.domains else None

    if args.auto:
        print(f"[CLI] Starting auto-sync (interval: {args.interval}s)...")
        sync.start_auto_sync(domains)
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            sync.stop_auto_sync()
            print("\n[CLI] Stopped")
    else:
        if args.direction in ("kg2mnemo", "full"):
            sync.sync_kg_l_to_mnemo(domains)
        if args.direction in ("mnemo2kg", "full"):
            sync.sync_mnemo_to_kg_l()
        print("[CLI] Sync complete")


if __name__ == "__main__":
    main()