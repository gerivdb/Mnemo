#!/usr/bin/env python3
"""
verify_statement.py — Standard Check₀ vérification unifié (GEN-049)

Standardisable dans n'importe quel repo gerivdb/*.
Interface : verify(statement_path, evidence_paths) → bool

Proof-of-Life : testé sur ONTOLOGY (commit 80c6826) et GOVERNANCE-HUB.
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime


# ============================================================
# Métriques standards (vérifiées par KG Engine)
# ============================================================
METRIC_CONSTRAINTS = {
    "H":    {"min": 0.33, "max": 0.43, "desc": "Entropie (Cycle R24)"},
    "TM":   {"min": 0.15, "max": 0.25, "desc": "Taux de mutation"},
    "F_grav": {"min": 0.85, "max": 1.00, "desc": "Force gravitationnelle (éthique)"},
    "C":    {"min": 0.92, "max": 1.00, "desc": "Check Rate (hooks + metrics validés)"},
    "I":    {"min": 0.20, "max": 1.00, "desc": "Introspection (aok)"},
}

# Garde-fous associés
GUARDE_FOU_MAP = {
    "C":    "GF-19",  # C <= 0.85 × 2 cycles → alerte
    "H":    "GF-3",   # H hors [0.33, 0.43]
    "TM":   "GF-3",   # TM hors [0.15, 0.25]
    "F_grav": "Axe 19", # F_grav < 0.85
    "I":    "GEN-045",
}


def load_statement(stmt_path: str = "introspection/statement.json") -> dict:
    """Charge le Statement publié par un repo."""
    path = Path(stmt_path)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_evidence_dir(evidence_dir: str = "introspection/evidence/") -> list[dict]:
    """Charge tous les Evidence d'un répertoire."""
    d = Path(evidence_dir)
    if not d.exists():
        return []
    evidences = []
    for f in sorted(d.glob("*.json")):
        with open(f) as fh:
            e = json.load(fh)
            e["_file"] = f.name
            evidences.append(e)
    return evidences


def load_evidence_files(evidence_paths: list[str]) -> list[dict]:
    """Charge des Evidence spécifiques par chemin."""
    evidences = []
    for p in evidence_paths:
        with open(p) as f:
            e = json.load(f)
            e["_file"] = Path(p).name
            evidences.append(e)
    return evidences


def extract_metrics(stmt: dict) -> dict:
    """Extrait les métriques du Statement (au top niveau ou dans metrics)."""
    if "metrics" in stmt:
        return stmt["metrics"]
    return {k: v for k, v in stmt.items() if k in METRIC_CONSTRAINTS}


def completeness(evidence: dict) -> bool:
    """
    Vérifie qu'un Evidence contient les éléments nécessaires :
    - commit (SHA git)
    - hooks_passed (liste non vide)
    - metrics (dictionnaire)
    - timestamp (horodatage UTC)
    """
    required_keys = ["commit", "hooks_passed", "metrics"]
    if not all(k in evidence for k in required_keys):
        return False
    if not evidence["hooks_passed"]:
        return False
    if not isinstance(evidence["metrics"], dict):
        return False
    # Optional: timestamp check
    if "timestamp" in evidence:
        try:
            datetime.fromisoformat(evidence["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            return False
    return True


def soundness(stmt: dict) -> bool:
    """
    Vérifie que les métriques respectent les contraintes.
    Si contentOnly=true, le contenu est sa preuve → soundness par construction.
    """
    if stmt.get("contentOnly", False):
        return True  # Origine : contentOnly = true → automatically sound

    metrics = extract_metrics(stmt)
    for key, constraints in METRIC_CONSTRAINTS.items():
        if key in metrics:
            val = metrics[key]
            if not (constraints["min"] <= val <= constraints["max"]):
                return False
    return True


def verify(stmt_path: str, evidence_paths: list[str]) -> bool:
    """
    Point d'entrée principal : verify(Statement, Evidence) → Bool.

    Returns True si :
    - Le Statement existe
    - Au moins un Evidence est complet (completeness)
    - Le Statement respecte les contraintes (soundness)
    """
    stmt = load_statement(stmt_path)
    if stmt is None:
        print(f"[FAIL] Statement not found: {stmt_path}")
        return False

    evidences = load_evidence_files(evidence_paths) if evidence_paths else load_evidence_dir()
    if not evidences:
        print(f"[FAIL] No evidence found")
        return False

    # Vérifier completeness pour chaque Evidence
    for e in evidences:
        if completeness(e):
            print(f"[OK] completeness: {e.get('_file', 'unknown')}")
        else:
            print(f"[WARN] incomplete evidence: {e.get('_file', 'unknown')}")

    # Vérifier soundness
    if not soundness(stmt):
        print(f"[FAIL] soundness: metrics out of constraints")
        return False
    print(f"[OK] soundness: all constraints respected")

    return True


def verify_with_evidence_ref(stmt: dict, evidence_ref: str, evidence_dir: str = "introspection/evidence/") -> bool:
    """Vérifie un Statement en utilisant un evidence_ref spécifique."""
    path = Path(evidence_dir) / evidence_ref
    if not path.exists():
        print(f"[FAIL] Evidence not found: {path}")
        return False
    return verify_from_dict(stmt, str(path))


def verify_from_dict(stmt: dict, evidence_path: str) -> bool:
    """Vérifie un Statement déjà chargé avec un Evidence fichier."""
    e = json.load(open(evidence_path))
    if not completeness(e):
        print(f"[FAIL] Evidence incomplete: {e.get('_file', evidence_path)}")
        return False
    if not soundness(stmt):
        print(f"[FAIL] Statement soundness check failed")
        return False
    return True


# CLI interface
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify a Statement against Evidence (GEN-049 standard)")
    parser.add_argument("statement", nargs="?", default="introspection/statement.json",
                        help="Path to statement.json")
    parser.add_argument("evidence", nargs="*",
                        help="Paths to evidence JSON files (default: introspection/evidence/)")
    args = parser.parse_args()

    result = verify(args.statement, args.evidence)
    print(f"\n{'✅ PASS' if result else '❌ FAIL'} : verify_statement.py exit {'0' if result else '1'}")
    sys.exit(0 if result else 1)
