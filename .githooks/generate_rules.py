#!/usr/bin/env python3
"""
generate_rules.py — Generate .githooks/rules.sh from multi-repo-governance.yaml

Reads the branch_routing section of the governance manifest and produces
a bash-sourced rules.sh file with FORBIDDEN_PATHS, ALLOWED_PREFIXES,
REDIRECT_MAP, and GUARD_MODE variables.

Usage:
    python .githooks/generate_rules.py <manifest_path> <repo_name> [output_path]

Arguments:
    manifest_path   Path to multi-repo-governance.yaml
    repo_name       Name of the repository (must match branch_routing.repositories key)
    output_path     Output path for rules.sh (default: .githooks/rules.sh)

IntentHash: 0xBRG_GENERATE_RULES_20260526
Version: 1.0.0
"""

import datetime
import os
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ─── Constants ────────────────────────────────────────────────────────────────

HOOK_VERSION = "1.0.0"
HOOK_INTENT_HASH = "0xBRG_GENERATE_RULES_20260526"


def generate_rules(manifest_path: str, repo_name: str, output_path: str) -> None:
    """Generate rules.sh from the governance manifest for a specific repository."""
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)

    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    if HAS_YAML:
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error: Invalid YAML in manifest: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: PyYAML required — pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    routing = manifest.get("branch_routing", {})
    repos = routing.get("repositories", {})
    repo_config = repos.get(repo_name)

    if not repo_config:
        print(f"Warning: No branch_routing found for {repo_name}", file=sys.stderr)
        print(f"Available: {', '.join(repos.keys())}", file=sys.stderr)
        sys.exit(1)

    forbidden = repo_config.get("forbidden_paths", [])
    prefixes = repo_config.get("allowed_branch_prefixes", [])
    redirects = repo_config.get("redirect_map", {})

    forbidden_str = "|".join(forbidden) if forbidden else ""
    prefixes_str = "|".join(prefixes) if prefixes else ""
    redirect_items = [f"{k}:{v}" for k, v in redirects.items()]
    redirect_str = "|".join(redirect_items) if redirect_items else ""

    now = datetime.datetime.now().isoformat()
    brgs_version = routing.get("version", "3.0")

    content = f"""# .githooks/rules.sh — Auto-generated from multi-repo-governance.yaml
# DO NOT EDIT MANUALLY — Run: python .githooks/generate_rules.py
# Generated: {now}
# BRGS Version: {brgs_version}
# Repository: {repo_name}
# IntentHash: {HOOK_INTENT_HASH}

BRGS_VERSION="{brgs_version}"
GUARD_MODE="BLOCK"
TARGET_REPO="{repo_name}"

# Forbidden paths (pipe-separated globs)
FORBIDDEN_PATHS="{forbidden_str}"

# Allowed branch prefixes (pipe-separated)
ALLOWED_PREFIXES="{prefixes_str}"

# Redirect map (format: source_path:target_repo|...)
REDIRECT_MAP="{redirect_str}"
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"[generate_rules] Generated {output_path} for {repo_name}")
    print(f"  Forbidden paths : {len(forbidden)}")
    print(f"  Allowed prefixes: {len(prefixes)}")
    print(f"  Redirects       : {len(redirects)}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("Usage: python generate_rules.py <manifest_path> <repo_name> [output_path]")
        sys.exit(1)

    manifest_path = sys.argv[1]
    repo_name = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else ".githooks/rules.sh"

    generate_rules(manifest_path, repo_name, output_path)


if __name__ == "__main__":
    main()
