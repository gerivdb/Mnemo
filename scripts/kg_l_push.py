#!/usr/bin/env python3
"""
kg_l_push.py — CLI tool to push Mnemo entries to KG-L.

Pushes Mnemo hot/warm entries with kg_l tag or causal domain to KG-L graph.
Integrates with N243 gate for ternary validation.

IntentHash: 0xKG_L_PUSH_CLI_20260828
Version: 1.0.0
Author: gerivdb
Date: 2026-08-28
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mnemo.mnemo_core import MnemoCore, MemoryTier, Provenance
from src.mnemo.mnemo_kg_sync import (
    KGLEngine, MnemoKGSync, push_mnemo_to_kg_l, KG_L_GRAPH_PATH,
    KG_L_EDGE_TYPES, MemoryEntry, MemoryTier, Provenance,
    SyncStats, _should_push_to_kg_l, _mnemo_key_to_kg_l_node,
    _mnemo_entry_to_kg_l_node, KG_L_GRAPH_PATH
)


def push_entries(
    mnemo: MnemoCore,
    kg_l: KGLEngine,
    require_gate: bool = True,
    gate_client: Optional[Any] = None,
    dry_run: bool = False,
) -> SyncStats:
    """Push Mnemo entries to KG-L."""
    print(f"[kg_l_push] Starting push Mnemo → KG-L...")
    print(f"  KG-L graph: {KG_L_GRAPH_PATH}")
    print(f"  Dry run: {dry_run}")
    print(f"  N243 gate: {'enabled' if require_gate else 'disabled'}")
    
    if dry_run:
        print("[DRY RUN] Would push entries but not write to KG-L")
        # In dry-run, just list candidates and return empty stats
        candidates = list_candidates(mnemo)
        print(f"[DRY RUN] Would push {len(candidates)} entries")
        return SyncStats(
            mnemo_entries_promoted_cold=len([c for c in candidates if c["tier"] in ("hot", "warm")]),
            duration_ms=0,
        )
    
    print(f"[kg_l_push] Starting push Mnemo → KG-L...")
    print(f"  KG-L graph: {KG_L_GRAPH_PATH}")
    print(f"  Dry run: {dry_run}")
    print(f"  N243 gate: {'enabled' if require_gate else 'disabled'}")
    
    stats = push_mnemo_to_kg_l(
        mnemo, kg_l, 
        require_n243_gate=require_gate,
        gate_client=None  # TODO: implement gate client
    )
    
    print(f"[kg_l_push] Push complete:")
    print(f"  Entries promoted to cold: {stats.mnemo_entries_promoted_cold}")
    print(f"  KG-L edges added: {stats.kg_l_edges_exported}")
    print(f"  Conflicts detected: {stats.conflicts_detected}")
    print(f"  Conflicts resolved: {stats.conflicts_resolved}")
    print(f"  Errors: {len(stats.errors)}")
    if stats.errors:
        for err in stats.errors:
            print(f"  - {err}")
    print(f"  Duration: {stats.duration_ms:.1f}ms")
    
    return stats


def list_candidates(mnemo: MnemoCore) -> List[Dict[str, Any]]:
    """List entries that would be pushed to KG-L."""
    candidates = []
    
    for key, entry in mnemo._hot_cache.items():
        if _should_push_to_kg_l(entry):
            candidates.append({
                "key": key,
                "tier": entry.tier.value,
                "provenance": entry.provenance.value,
                "tags": entry.tags,
                "domain": entry.metadata.get("domain", "unknown"),
            })
    
    for key, entry in mnemo._warm_cache.items():
        if _should_push_to_kg_l(entry):
            candidates.append({
                "key": key,
                "tier": entry.tier.value,
                "provenance": entry.provenance.value,
                "tags": entry.tags,
                "domain": entry.metadata.get("domain", "unknown"),
            })
    
    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Push Mnemo entries to KG-L graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kg_l_push.py --push                    # Push all eligible entries
  kg_l_push.py --list                    # List candidates without pushing
  kg_l_push.py --push --dry-run          # Dry run (no writes)
  kg_l_push.py --push --no-gate          # Skip N243 gate validation
        """
    )
    parser.add_argument("--push", action="store_true", help="Push entries to KG-L")
    parser.add_argument("--list", action="store_true", help="List candidates without pushing")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no writes to KG-L)")
    parser.add_argument("--no-gate", action="store_true", help="Skip N243 gate validation")
    parser.add_argument("--mnemo-persist", type=str, default=None, help="Mnemo persistence file")
    parser.add_argument("--kg-l-path", type=str, default=str(KG_L_GRAPH_PATH), help="KG-L graph path")
    parser.add_argument("--domains", type=str, default=None, help="Comma-separated domains filter")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Initialize
    mnemo = MnemoCore(persistence_path=args.mnemo_persist) if args.mnemo_persist else MnemoCore()
    kg_l = KGLEngine(Path(args.kg_l_path))
    
    if args.list:
        print("[kg_l_push] Listing candidates...")
        candidates = list_candidates(mnemo)
        print(f"Found {len(candidates)} candidates:")
        for c in candidates:
            print(f"  {c['key']} (tier={c['tier']}, prov={c['provenance']}, domain={c['domain']})")
        return 0
    
    if args.push:
        stats = push_entries(
            mnemo, 
            kg_l, 
            require_gate=not args.no_gate,
            gate_client=None,
            dry_run=args.dry_run,
        )
        
        if stats.errors:
            print(f"[ERROR] Push completed with {len(stats.errors)} errors", file=sys.stderr)
            return 1
        return 0
    
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())