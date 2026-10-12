# .githooks/rules.sh - Auto-generated from multi-repo-governance.yaml
# DO NOT EDIT MANUALLY - Run: python .githooks/generate_rules.py
# Generated: 2026-10-12T23:53:36.774346
# BRGS Version: 3.0
# Repository: fix/*
# IntentHash: 0xBRG_GENERATE_RULES_20260526

BRGS_VERSION="3.0"
GUARD_MODE="BLOCK"
TARGET_REPO="fix/*"

# Forbidden paths (pipe-separated globs)
FORBIDDEN_PATHS="EPICS/|PRD/|ADR/|INTENTS/|SPEC/|docs/architecture/|config/schemas/|.githooks/|.kilocode/|.github/workflows/|.env|secrets.json|config/secrets.yaml|config/bdcp_config.yaml|config/security.yaml"

# Allowed branch prefixes (pipe-separated)
ALLOWED_PREFIXES="chore/|ci/|deploy/|docs/|emergency/|experiment/|feat/|fix/|hotfix/|perf/|refactor/|release/|rollback/|test/"

# Redirect map (format: source_path:target_repo|...)
REDIRECT_MAP=""
