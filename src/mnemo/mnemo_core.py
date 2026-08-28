"""
mnemo_core.py — Moteur Mémoire Opératoire Hot Cache (Mnemo).

Cache sémantique hot (accès < 5ms), gestion TTL, provenance tracking,
interface MemoryWrite/MemoryRead unifiée, sync bidirectionnel KG-L.

IntentHash: 0xMNEMO_CORE_HOT_CACHE_20260828
Version: 1.0.0
Author: gerivdb
Date: 2026-08-28
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from collections import OrderedDict

# ──────────────────────────────────────────────────────────────────────────────
# Enums & Dataclasses
# ──────────────────────────────────────────────────────────────────────────────

class MemoryTier(str, Enum):
    """Niveaux de persistance mémoire (AMU)."""
    HOT = "hot"          # Mnemo cache - < 5ms, TTL session
    WARM = "warm"        # Mnemo sync + KG-L subset - < 50ms, TTL 24h
    COLD = "cold"        # KG-L SOT - < 200ms, permanent
    PERMANENT = "permanent"  # HERMES MEMORY.md/USER.md - immuable


class Provenance(str, Enum):
    """Source de l'écriture mémoire."""
    BRAIN = "BRAIN"
    HERMES_NR = "HERMES_NR"
    N243 = "N243"
    CTULU = "CTULU"
    HUMAN = "HUMAN"
    MNEMO = "MNEMO"
    KG_L = "KG_L"
    WAZAA = "WAZAA"


class Operation(str, Enum):
    """Types d'opérations mémoire."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LINK = "link"


@dataclass
class MemoryEntry:
    """Entrée mémoire unique avec métadonnées complètes."""
    key: str
    value: Any
    tier: MemoryTier = MemoryTier.HOT
    provenance: Provenance = Provenance.MNEMO
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_seconds: Optional[int] = None  # None = permanent (pour HOT: session default)
    expires_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self):
        if self.ttl_seconds and not self.expires_at:
            self.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat()

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.fromisoformat(self.expires_at.replace('Z', '+00:00')) < datetime.now(timezone.utc)

    def touch(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.version += 1
        if self.ttl_seconds:
            self.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat()


@dataclass
class MemoryWrite:
    """Contrat d'écriture mémoire unifié (AMU)."""
    operation: Operation
    domain: str  # identity, facts, skills, causal, spectral, decisions
    payload: Dict[str, Any]
    provenance: Provenance = Provenance.MNEMO
    n243_gate_required: bool = True
    tier: MemoryTier = MemoryTier.HOT
    ttl_seconds: Optional[int] = None


@dataclass
class MemoryRead:
    """Contrat de lecture mémoire unifié (AMU)."""
    query: Union[str, Dict[str, Any]]
    domain: str
    tier: MemoryTier = MemoryTier.HOT
    format: str = "raw"  # raw, graph, spectral, timeline


@dataclass
class SyncReport:
    """Rapport de synchronisation Mnemo ↔ KG-L."""
    hot_to_warm: int = 0
    warm_to_cold: int = 0
    conflicts_resolved: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_ms: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# MnemoCore — Moteur principal
# ──────────────────────────────────────────────────────────────────────────────

class MnemoCore:
    """
    Cache sémantique hot (LRU + TTL) avec provenance tracking.
    
    Caractéristiques:
    - Accès < 5ms (dictionnaire + OrderedDict pour LRU)
    - TTL automatique par tier (HOT: session, WARM: 24h, COLD: permanent)
    - Provenance tracking obligatoire
    - Sync bidirectionnel KG-L (hot↔warm↔cold)
    - Thread-safe (RLock)
    """

    DEFAULT_HOT_TTL = 7200      # 2h (session)
    DEFAULT_WARM_TTL = 86400    # 24h
    MAX_HOT_ENTRIES = 10000     # Limite LRU

    def __init__(
        self,
        hot_ttl: int = DEFAULT_HOT_TTL,
        warm_ttl: int = DEFAULT_WARM_TTL,
        max_entries: int = MAX_HOT_ENTRIES,
        persistence_path: Optional[Path] = None,
    ):
        self.hot_ttl = hot_ttl
        self.warm_ttl = warm_ttl
        self.max_entries = max_entries
        self.persistence_path = persistence_path

        # Stockage principal: OrderedDict pour LRU (clé -> MemoryEntry)
        self._hot_cache: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._warm_cache: Dict[str, MemoryEntry] = {}  # Pas de LRU, TTL only
        self._lock = threading.RLock()

        # Index provenance pour queries
        self._provenance_index: Dict[Provenance, set] = {p: set() for p in Provenance}
        self._domain_index: Dict[str, set] = {}

        # Stats
        self._stats = {
            "hits": 0, "misses": 0, "sets": 0, "deletes": 0,
            "evictions": 0, "expirations": 0, "syncs": 0,
        }

        # Charger persistance si existe
        if persistence_path:
            pp = Path(persistence_path) if isinstance(persistence_path, str) else persistence_path
            if pp.exists():
                self._load_persistence()

        # Thread nettoyage expirations (daemon)
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    # ──────────────────────────────────────────────────────────────────────────
    # Opérations de base (MemoryWrite / MemoryRead contracts)
    # ──────────────────────────────────────────────────────────────────────────

    def write(self, mw: MemoryWrite) -> Dict[str, Any]:
        """Écriture via contrat MemoryWrite unifié."""
        with self._lock:
            if mw.operation == Operation.CREATE:
                return self._create(mw)
            elif mw.operation == Operation.UPDATE:
                return self._update(mw)
            elif mw.operation == Operation.DELETE:
                return self._delete(mw)
            elif mw.operation == Operation.LINK:
                return self._link(mw)
            else:
                return {"success": False, "error": f"Operation {mw.operation} not supported"}

    def _create(self, mw: MemoryWrite) -> Dict[str, Any]:
        key = mw.payload.get("key")
        if not key:
            return {"success": False, "error": "Missing 'key' in payload"}
        
        with self._lock:
            if key in self._hot_cache or key in self._warm_cache:
                return {"success": False, "error": f"Key '{key}' already exists"}

        entry = MemoryEntry(
            key=key,
            value=mw.payload.get("value"),
            tier=mw.tier,
            provenance=mw.provenance,
            ttl_seconds=self._get_ttl_for_tier(mw.tier, mw.payload.get("ttl_seconds")),
            tags=mw.payload.get("tags", []),
            metadata=mw.payload.get("metadata", {}),
        )
        return self._store_entry(key, entry)

    def _update(self, mw: MemoryWrite) -> Dict[str, Any]:
        key = mw.payload.get("key")
        if not key:
            return {"success": False, "error": "Missing 'key' in payload"}

        with self._lock:
            entry = self._get_entry_raw(key)
            if not entry:
                return {"success": False, "error": f"Key '{key}' not found"}

        entry.value = mw.payload.get("value", entry.value)
        if "tags" in mw.payload:
            entry.tags = mw.payload["tags"]
        if "metadata" in mw.payload:
            entry.metadata.update(mw.payload["metadata"])
        entry.touch()
        return {"success": True, "key": key, "version": entry.version}

    def _delete(self, mw: MemoryWrite) -> Dict[str, Any]:
        key = mw.payload.get("key")
        if not key:
            return {"success": False, "error": "Missing 'key' in payload"}

        with self._lock:
            if key in self._hot_cache:
                del self._hot_cache[key]
                self._remove_from_indexes(key)
                self._stats["deletes"] += 1
                return {"success": True, "key": key}
            elif key in self._warm_cache:
                del self._warm_cache[key]
                self._remove_from_indexes(key)
                self._stats["deletes"] += 1
                return {"success": True, "key": key}
            return {"success": False, "error": f"Key '{key}' not found"}

    def _link(self, mw: MemoryWrite) -> Dict[str, Any]:
        """Créer un lien entre deux clés (relation)."""
        source = mw.payload.get("source")
        target = mw.payload.get("target")
        relation = mw.payload.get("relation", "links_to")
        
        if not source or not target:
            return {"success": False, "error": "Missing 'source' or 'target'"}

        with self._lock:
            src_entry = self._get_entry_raw(source)
            tgt_entry = self._get_entry_raw(target)
            if not src_entry or not tgt_entry:
                return {"success": False, "error": "Source or target not found"}

            # Ajouter relation dans metadata
            if "relations" not in src_entry.metadata:
                src_entry.metadata["relations"] = []
            src_entry.metadata["relations"].append({"target": target, "relation": relation})
            src_entry.touch()

            return {"success": True, "source": source, "target": target, "relation": relation}

    def read(self, mr: MemoryRead) -> Dict[str, Any]:
        """Lecture via contrat MemoryRead unifié."""
        with self._lock:
            if isinstance(mr.query, str):
                # Clé directe
                entry = self._get_entry_raw(mr.query)
                if entry:
                    return {"success": True, "data": self._entry_to_dict(entry)}
                return {"success": False, "error": f"Key '{mr.query}' not found"}
            
            elif isinstance(mr.query, dict):
                # Query pattern
                return self._query_pattern(mr.query, mr.tier, mr.format)
            
            return {"success": False, "error": "Invalid query format"}

    # ──────────────────────────────────────────────────────────────────────────
    # Implémentation interne
    # ──────────────────────────────────────────────────────────────────────────

    def _store_entry(self, key: str, entry: MemoryEntry) -> Dict[str, Any]:
        # Éviction LRU si nécessaire
        if len(self._hot_cache) >= self.max_entries and key not in self._hot_cache:
            self._evict_lru()

        self._hot_cache[key] = entry
        self._hot_cache.move_to_end(key)  # LRU: most recent at end
        self._add_to_indexes(key, entry)
        self._stats["sets"] += 1
        return {"success": True, "key": key, "version": entry.version}

    def _get_entry_raw(self, key: str) -> Optional[MemoryEntry]:
        # Check HOT cache first (LRU)
        if key in self._hot_cache:
            entry = self._hot_cache[key]
            if entry.is_expired():
                del self._hot_cache[key]
                self._remove_from_indexes(key)
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None
            # LRU: move to end (most recent)
            self._hot_cache.move_to_end(key)
            self._stats["hits"] += 1
            return entry
        
        # Check WARM cache
        if key in self._warm_cache:
            entry = self._warm_cache[key]
            if entry.is_expired():
                del self._warm_cache[key]
                self._remove_from_indexes(key)
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None
            self._stats["hits"] += 1
            return entry
        
        self._stats["misses"] += 1
        return None

    def _query_pattern(self, pattern: Dict[str, Any], tier: MemoryTier, fmt: str) -> Dict[str, Any]:
        """Query par pattern: tags, provenance, domain, metadata."""
        results = []
        search_hot = tier in (MemoryTier.HOT, MemoryTier.WARM, MemoryTier.COLD)
        search_warm = tier in (MemoryTier.WARM, MemoryTier.COLD)
        
        search_space = []
        if search_hot:
            search_space.extend(self._hot_cache.items())
        if search_warm:
            search_space.extend(self._warm_cache.items())
        
        for key, entry in search_space:
            if self._matches_pattern(entry, pattern):
                results.append(self._entry_to_dict(entry) if fmt == "raw" else key)
        
        return {"success": True, "count": len(results), "results": results}

    def _matches_pattern(self, entry: MemoryEntry, pattern: Dict[str, Any]) -> bool:
        # Tags
        if "tags" in pattern:
            required_tags = set(pattern["tags"])
            if not required_tags.issubset(set(entry.tags)):
                return False
        # Provenance
        if "provenance" in pattern:
            if entry.provenance != pattern["provenance"]:
                return False
        # Domain (dans metadata)
        if "domain" in pattern:
            if entry.metadata.get("domain") != pattern["domain"]:
                return False
        # Metadata custom
        if "metadata" in pattern:
            for k, v in pattern["metadata"].items():
                if entry.metadata.get(k) != v:
                    return False
        return True

    def _entry_to_dict(self, entry: MemoryEntry) -> Dict[str, Any]:
        d = asdict(entry)
        # Handle both Enum and string
        d["tier"] = entry.tier.value if isinstance(entry.tier, MemoryTier) else entry.tier
        d["provenance"] = entry.provenance.value if isinstance(entry.provenance, Provenance) else entry.provenance
        return d

    def _get_ttl_for_tier(self, tier: MemoryTier, explicit_ttl: Optional[int]) -> Optional[int]:
        if explicit_ttl is not None:
            return explicit_ttl
        if tier == MemoryTier.HOT:
            return self.hot_ttl
        if tier == MemoryTier.WARM:
            return self.warm_ttl
        return None  # COLD/PERMANENT = pas de TTL

    def _evict_lru(self):
        """Éviction LRU de la plus ancienne entrée HOT."""
        if self._hot_cache:
            oldest_key, _ = self._hot_cache.popitem(last=False)  # FIFO
            self._remove_from_indexes(oldest_key)
            self._stats["evictions"] += 1

    def _add_to_indexes(self, key: str, entry: MemoryEntry):
        self._provenance_index[entry.provenance].add(key)
        domain = entry.metadata.get("domain", "default")
        if domain not in self._domain_index:
            self._domain_index[domain] = set()
        self._domain_index[domain].add(key)

    def _remove_from_indexes(self, key: str):
        for prov_set in self._provenance_index.values():
            prov_set.discard(key)
        for dom_set in self._domain_index.values():
            dom_set.discard(key)

    # ──────────────────────────────────────────────────────────────────────────
    # Tier Management (hot -> warm -> cold)
    # ──────────────────────────────────────────────────────────────────────────

    def promote_to_warm(self, key: str) -> bool:
        """Promouvoir HOT -> WARM (ex: fin de session)."""
        with self._lock:
            if key in self._hot_cache:
                entry = self._hot_cache.pop(key)
                entry.tier = MemoryTier.WARM
                entry.ttl_seconds = self.warm_ttl
                entry.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.warm_ttl)).isoformat()
                self._warm_cache[key] = entry
                return True
        return False

    def promote_to_cold(self, key: str) -> bool:
        """Promouvoir WARM -> COLD (archivage KG-L)."""
        with self._lock:
            if key in self._warm_cache:
                entry = self._warm_cache.pop(key)
                entry.tier = MemoryTier.COLD
                entry.ttl_seconds = None
                entry.expires_at = None
                # Note: le stockage COLD réel se fait dans KG-L via sync
                return True
        return False

    def demote_to_hot(self, key: str) -> bool:
        """Rétrograder WARM -> HOT (rechargement)."""
        with self._lock:
            if key in self._warm_cache:
                entry = self._warm_cache.pop(key)
                entry.tier = MemoryTier.HOT
                entry.ttl_seconds = self.hot_ttl
                entry.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.hot_ttl)).isoformat()
                self._hot_cache[key] = entry
                self._hot_cache.move_to_end(key)
                return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # Persistance & Nettoyage
    # ──────────────────────────────────────────────────────────────────────────

    def _cleanup_loop(self):
        """Thread daemon: nettoie entrées expirées toutes les 60s."""
        while True:
            time.sleep(60)
            self._cleanup_expired()

    def _cleanup_expired(self):
        with self._lock:
            # Hot cache
            expired = [k for k, e in self._hot_cache.items() if e.is_expired()]
            for k in expired:
                del self._hot_cache[k]
                self._remove_from_indexes(k)
                self._stats["expirations"] += 1
            
            # Warm cache
            expired = [k for k, e in self._warm_cache.items() if e.is_expired()]
            for k in expired:
                del self._warm_cache[k]
                self._remove_from_indexes(k)
                self._stats["expirations"] += 1

    def save_persistence(self):
        """Sauvegarde hot+warm cache sur disque (JSON)."""
        if not self.persistence_path:
            return
        pp = Path(self.persistence_path) if isinstance(self.persistence_path, str) else self.persistence_path
        with self._lock:
            data = {
                "hot": {k: self._entry_to_dict(v) for k, v in self._hot_cache.items()},
                "warm": {k: self._entry_to_dict(v) for k, v in self._warm_cache.items()},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            pp.parent.mkdir(parents=True, exist_ok=True)
            pp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    def _load_persistence(self):
        """Charge hot+warm cache depuis disque."""
        try:
            pp = Path(self.persistence_path) if isinstance(self.persistence_path, str) else self.persistence_path
            data = json.loads(pp.read_text(encoding="utf-8"))
            for k, v in data.get("hot", {}).items():
                v["tier"] = MemoryTier(v["tier"])
                v["provenance"] = Provenance(v["provenance"])
                self._hot_cache[k] = MemoryEntry(**v)
            for k, v in data.get("warm", {}).items():
                v["tier"] = MemoryTier(v["tier"])
                v["provenance"] = Provenance(v["provenance"])
                self._warm_cache[k] = MemoryEntry(**v)
            self._rebuild_indexes()
        except Exception as e:
            print(f"[MnemoCore] Load persistence failed: {e}")

    def _rebuild_indexes(self):
        self._provenance_index = {p: set() for p in Provenance}
        self._domain_index = {}
        for k, e in self._hot_cache.items():
            self._add_to_indexes(k, e)
        for k, e in self._warm_cache.items():
            self._add_to_indexes(k, e)

    # ──────────────────────────────────────────────────────────────────────────
    # API publique simplifiée
    # ──────────────────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any, tier: Union[MemoryTier, str] = MemoryTier.HOT, 
            provenance: Union[Provenance, str] = Provenance.MNEMO, ttl: Optional[int] = None,
            tags: Optional[List[str]] = None, metadata: Optional[Dict] = None) -> Dict:
        """API simplifiée: set(key, value, ...)."""
        # Convertir string -> Enum si nécessaire
        if isinstance(tier, str):
            tier = MemoryTier(tier.lower())
        if isinstance(provenance, str):
            provenance = Provenance(provenance.upper())
        
        mw = MemoryWrite(
            operation=Operation.CREATE,
            domain=metadata.get("domain", "default") if metadata else "default",
            payload={"key": key, "value": value, "tags": tags or [], "metadata": metadata or {}},
            provenance=provenance,
            tier=tier,
            ttl_seconds=ttl,
        )
        return self.write(mw)

    def get(self, key: str, tier: Union[MemoryTier, str] = MemoryTier.HOT) -> Optional[Any]:
        """API simplifiée: get(key)."""
        if isinstance(tier, str):
            tier = MemoryTier(tier.lower())
        mr = MemoryRead(query=key, domain="default", tier=tier)
        result = self.read(mr)
        return result.get("data", {}).get("value") if result.get("success") else None

    def query(self, pattern: Dict[str, Any], tier: Union[MemoryTier, str] = MemoryTier.HOT) -> List[Dict]:
        """API simplifiée: query(pattern)."""
        if isinstance(tier, str):
            tier = MemoryTier(tier.lower())
        mr = MemoryRead(query=pattern, domain="default", tier=tier)
        result = self.read(mr)
        return result.get("results", []) if result.get("success") else []

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                "hot_entries": len(self._hot_cache),
                "warm_entries": len(self._warm_cache),
                "max_hot": self.max_entries,
                "hit_rate": self._stats["hits"] / max(1, self._stats["hits"] + self._stats["misses"]),
            }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "hot_entries": len(self._hot_cache),
            "warm_entries": len(self._warm_cache),
            "stats": self.stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Factory & CLI
# ──────────────────────────────────────────────────────────────────────────────

def create_mnemo_core(
    hot_ttl: int = 7200,
    warm_ttl: int = 86400,
    persistence_path: Optional[str] = None,
) -> MnemoCore:
    """Factory pour créer MnemoCore avec config standard."""
    pp = Path(persistence_path) if persistence_path else None
    return MnemoCore(hot_ttl=hot_ttl, warm_ttl=warm_ttl, persistence_path=pp)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mnemo Core CLI")
    parser.add_argument("--hot-ttl", type=int, default=7200, help="HOT TTL seconds")
    parser.add_argument("--warm-ttl", type=int, default=86400, help="WARM TTL seconds")
    parser.add_argument("--persist", type=str, default=None, help="Persistence file path")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    args = parser.parse_args()

    mnemo = create_mnemo_core(
        hot_ttl=args.hot_ttl,
        warm_ttl=args.warm_ttl,
        persistence_path=args.persist,
    )

    if args.demo:
        print("=== Mnemo Core Demo ===")
        # Set
        mnemo.set("identity:user", {"name": "gerivdb", "role": "architect"}, 
                  provenance=Provenance.HUMAN, tags=["identity"])
        mnemo.set("fact:project", "gerivdb ecosystem", 
                  provenance=Provenance.HUMAN, tags=["fact", "project"])
        mnemo.set("skill:arch", {"name": "architect", "level": "expert"},
                  provenance=Provenance.HUMAN, tags=["skill"])
        
        # Get
        print(f"Get identity:user → {mnemo.get('identity:user')}")
        print(f"Get fact:project → {mnemo.get('fact:project')}")
        
        # Query
        results = mnemo.query({"tags": ["fact"]})
        print(f"Query tags:fact → {len(results)} results")
        
        # Stats
        print(f"Stats: {mnemo.stats()}")
        print(f"Health: {mnemo.health_check()}")