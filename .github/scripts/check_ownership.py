#!/usr/bin/env python3
"""
check_ownership.py — BRGS L4: Branch ownership check for GitHub Actions

Reads the branch_routing section of the governance manifest and verifies
that files modified in the current push don't belong to a different repository.

This script is intended to be run as a step in .github/workflows/branch-gate.yml.
It is NON-BLOQUING — it reports violations via GitHub status checks and annotations
but does NOT prevent the push (GitHub doesn't allow that for post-push actions).

Environment variables (required):
    GOVERNANCE_HUB_PATH  — Absolute path to GOVERNANCE-HUB clone on the runner
    REPO_NAME            — Name of the repository being pushed (from github.event.repository.name)
    BRANCH_NAME          — Branch being pushed (from github.ref_name)
    COMMIT_SHA           — SHA of the commit (from github.sha)
    GITHUB_TOKEN         — GitHub API token (from secrets.GITHUB_TOKEN)

IntentHash: 0xBRG_CHECK_OWNERSHIP_20260526
Version: 1.0.0
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ─── Constants ────────────────────────────────────────────────────────────────

HOOK_VERSION = "1.0.0"
HOOK_INTENT_HASH = "0xBRG_CHECK_OWNERSHIP_20260526"


def get_manifest_path() -> Optional[Path]:
    """Resolve the governance manifest path from environment or defaults."""
    env_path = os.environ.get("GOVERNANCE_HUB_PATH", "")
    if env_path:
        p = Path(env_path) / "multi-repo-governance.yaml"
        if p.exists():
            return p

    # Fallback: common absolute paths
    fallbacks = [
        Path("D:/DO/WEB/TOOLS/L0-CANON/GOVERNANCE-HUB/multi-repo-governance.yaml"),
        Path("/home/runner/work/GOVERNANCE-HUB/GOVERNANCE-HUB/multi-repo-governance.yaml"),
    ]
    for p in fallbacks:
        if p.exists():
            return p

    return None


def load_manifest(manifest_path: Path) -> Dict:
    """Load and parse the governance manifest."""
    if not HAS_YAML:
        print("::error::PyYAML required — pip install pyyaml")
        sys.exit(1)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"::error::Invalid YAML in manifest: {e}")
        sys.exit(1)


def get_changed_files() -> List[str]:
    """Get list of files changed in the current push."""
    try:
        # Try to get files from the push event
        # For push events, compare against the previous commit
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f for f in result.stdout.strip().split("\n") if f]

        # Fallback: check uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f for f in result.stdout.strip().split("\n") if f]

        return []
    except Exception as e:
        print(f"::warning::Could not determine changed files: {e}")
        return []


def check_ownership(
    manifest: Dict,
    repo_name: str,
    changed_files: List[str],
) -> Tuple[bool, List[Dict]]:
    """
    Check if changed files violate branch_routing rules.

    Returns:
        (passed, violations) where violations is a list of dicts with
        file, forbidden_path, redirect_target keys.
    """
    routing = manifest.get("branch_routing", {})
    repos = routing.get("repositories", {})
    repo_config = repos.get(repo_name)

    if not repo_config:
        print(f"::warning::No branch_routing rules for {repo_name} — skipping")
        return True, []

    forbidden_paths = repo_config.get("forbidden_paths", [])
    redirect_map = repo_config.get("redirect_map", {})

    if not forbidden_paths:
        return True, []

    violations = []

    for file_path in changed_files:
        for fp in forbidden_paths:
            prefix = fp.rstrip("/")
            if file_path.startswith(prefix + "/") or file_path == prefix:
                redirect_target = redirect_map.get(fp, redirect_map.get(prefix + "/", ""))
                violations.append({
                    "file": file_path,
                    "forbidden_path": fp,
                    "redirect_target": redirect_target,
                })
                break  # One violation per file is enough

    return len(violations) == 0, violations


def report_violations(violations: List[Dict], repo_name: str) -> None:
    """Report violations as GitHub Actions annotations."""
    print(f"::warning::BRGS: {len(violations)} forbidden path violation(s) in {repo_name}")

    for v in violations:
        file_path = v["file"]
        fp = v["forbidden_path"]
        target = v["redirect_target"]

        msg = f"File '{file_path}' matches forbidden path '{fp}'"
        if target:
            msg += f" — belongs to {target}"

        # GitHub annotation format
        print(f"::warning file={file_path}::{msg}")

    print("")
    print("=" * 60)
    print(f"BRGS L4 — {len(violations)} violation(s) detected")
    print("=" * 60)
    print("")
    print("This push has been accepted but contains files that")
    print("belong to a different repository according to the")
    print("branch_routing rules in multi-repo-governance.yaml.")
    print("")
    for v in violations:
        if v["redirect_target"]:
            print(f"  {v['file']} → should be in {v['redirect_target']}")
    print("")
    print("Please move these files to the correct repository.")
    print("=" * 60)


def main():
    print(f"[BRGS L4] check_ownership.py v{HOOK_VERSION}")
    print(f"[BRGS L4] IntentHash: {HOOK_INTENT_HASH}")
    print("")

    # Resolve inputs
    repo_name = os.environ.get("REPO_NAME", "")
    branch_name = os.environ.get("BRANCH_NAME", "")
    commit_sha = os.environ.get("COMMIT_SHA", "")

    if not repo_name:
        print("::error::REPO_NAME environment variable not set")
        sys.exit(1)

    print(f"[BRGS L4] Repository : {repo_name}")
    print(f"[BRGS L4] Branch     : {branch_name}")
    print(f"[BRGS L4] Commit     : {commit_sha[:12] if commit_sha else 'N/A'}")
    print("")

    # Load manifest
    manifest_path = get_manifest_path()
    if not manifest_path:
        print("::error::GOVERNANCE_HUB_PATH not set and manifest not found at default paths")
        print("::error::Set GOVERNANCE_HUB_PATH secret to the absolute path of GOVERNANCE-HUB clone")
        sys.exit(1)

    print(f"[BRGS L4] Manifest   : {manifest_path}")
    manifest = load_manifest(manifest_path)

    # Get changed files
    changed_files = get_changed_files()
    print(f"[BRGS L4] Changed    : {len(changed_files)} file(s)")

    if not changed_files:
        print("[BRGS L4] ✅ No files to check — passing")
        sys.exit(0)

    # Check ownership
    passed, violations = check_ownership(manifest, repo_name, changed_files)

    if passed:
        print(f"[BRGS L4] ✅ All {len(changed_files)} file(s) pass ownership check")
        sys.exit(0)
    else:
        report_violations(violations, repo_name)
        # Non-bloquing: exit 0 but with warnings
        sys.exit(0)


if __name__ == "__main__":
    main()
