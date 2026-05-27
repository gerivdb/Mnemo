#!/usr/bin/env pwsh
# ─────────────────────────────────────────────────────────────────────────────
# pre-push.ps1 — Branch Routing & Governance System (BRGS) v3.0 (Windows/Linux)
#
# PowerShell-native pre-push hook for environments where bash is not available.
# Called by the shim pre-push script on Windows PowerShell / PowerShell Core.
#
# Guards:
#   Guard 1: Remote URL validation (EXISTANT)
#   Guard 2: Ancestry check (EXISTANT)
#   Guard 3: Forbidden paths check (NOUVEAU — BRGS)
#   Guard 4: Branch prefix validation (NOUVEAU — BRGS)
#
# IntentHash: 0xBRG_PRE_PUSH_PS1_20260526
# Version: 1.0.0
# ─────────────────────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory=$true)]
    [string]$RemoteName,

    [Parameter(Mandatory=$true)]
    [string]$RemoteUrl
)

$ErrorActionPreference = "Stop"
$script:ExitCode = 0

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-BrgsLog {
    param([string]$Message, [string]$Level = "INFO")
    $prefix = switch ($Level) {
        "OK"     { "✅" }
        "WARN"   { "⚠️ " }
        "ERR"    { "❌" }
        default  { "ℹ️ " }
    }
    Write-Host "[BRGS] $prefix $Message"
}

function Get-GitCurrentBranch {
    $branch = git symbolic-ref --short HEAD 2>$null
    if (-not $branch) { $branch = "DETACHED" }
    return $branch
}

function Get-GitRepoRoot {
    return (git rev-parse --show-toplevel).Trim()
}

function Invoke-Git {
    param([string[]]$Arguments)
    $output = & git @Arguments 2>&null
    return ($output -join "`n").Trim()
}

# ── Config ────────────────────────────────────────────────────────────────────

$RepoRoot      = Get-GitRepoRoot
$RepoName      = Split-Path $RepoRoot -Leaf
$CurrentBranch = Get-GitCurrentBranch
$ManifestPath  = "D:\DO\WEB\TOOLS\L0-CANON\GOVERNANCE-HUB\multi-repo-governance.yaml"

Write-BrgsLog "Validating push -> $RemoteName ($RemoteUrl)"
Write-BrgsLog "Branch: $CurrentBranch"
Write-BrgsLog "Repo:   $RepoName"

if (Test-Path $ManifestPath) {
    Write-BrgsLog "Manifest: $ManifestPath"
} else {
    Write-BrgsLog "Manifest not found — using fallback rules" "WARN"
}

# ── Load rules from manifest ──────────────────────────────────────────────────

$ForbiddenPaths  = @()
$AllowedPrefixes = @()
$RedirectMap     = @{}
$GuardMode       = "BLOCK"

if (Test-Path $ManifestPath) {
    try {
        # Requires PyYAML; if unavailable, use fallback
        $rulesRaw = python -c "
import yaml, sys, json
with open(r'$ManifestPath', 'r', encoding='utf-8') as f:
    m = yaml.safe_load(f)
repos = m.get('branch_routing', {}).get('repositories', {})
cfg = repos.get('$RepoName', {})
print(json.dumps({
    'forbidden_paths': cfg.get('forbidden_paths', []),
    'allowed_prefixes': cfg.get('allowed_branch_prefixes', []),
    'redirect_map': cfg.get('redirect_map', {}),
}))
" 2>$null

        if ($rulesRaw) {
            $rules = $rulesRaw | ConvertFrom-Json
            $ForbiddenPaths  = $rules.forbidden_paths
            $AllowedPrefixes = $rules.allowed_prefixes
            foreach ($kv in $rules.redirect_map.PSObject.Properties) {
                $RedirectMap[$kv.Name] = $kv.Value
            }
            Write-BrgsLog "Rules loaded from manifest for $RepoName"
        }
    } catch {
        Write-BrgsLog "Failed to load manifest rules: $_" "WARN"
    }
}

# Fallback for DevTools
if ($ForbiddenPaths.Count -eq 0 -and $RepoName -eq "DevTools") {
    $ForbiddenPaths  = @("src/ecos/", ".ecos/", ".kilocode/", "bin/")
    $AllowedPrefixes = @("devtools/", "fix/", "chore/", "docs/", "refactor/")
    $RedirectMap     = @{
        "src/ecos/"    = "gerivdb/ECOS-CLI"
        ".ecos/"       = "gerivdb/ECOYSTEM"
        ".kilocode/"   = "gerivdb/ECOS-CLI"
        "bin/"         = "gerivdb/ECOS-CLI"
    }
    Write-BrgsLog "Using fallback rules for DevTools" "WARN"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Guard 1: Remote URL validation
# ═══════════════════════════════════════════════════════════════════════════════

$EcosRoot = Join-Path $RepoRoot "ECOS_ROOT.json"
if (Test-Path $EcosRoot) {
    $expectedPattern = "gerivdb/$RepoName"
    if ($RemoteUrl -notmatch [regex]::Escape($expectedPattern)) {
        Write-BrgsLog "BLOCKED: Remote URL mismatch!" "ERR"
        Write-Host "  Expected pattern : $expectedPattern"
        Write-Host "  Got              : $RemoteUrl"
        Write-Host "  Fix: git remote set-url origin https://github.com/$expectedPattern.git"
        exit 1
    }
    Write-BrgsLog "Guard 1 — Remote URL validated: $RemoteUrl" "OK"
} else {
    Write-BrgsLog "Guard 1 — No ECOS_ROOT.json, skipping" "OK"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Guard 2: Ancestry check
# ═══════════════════════════════════════════════════════════════════════════════

if ($CurrentBranch -ne "main" -and $CurrentBranch -ne "dev") {
    $mergeBase = git merge-base HEAD origin/main 2>$null
    if (-not $mergeBase) {
        Write-BrgsLog "Guard 2 — Cannot verify ancestry (origin/main not fetched)" "WARN"
        Write-Host "  Run: git fetch origin main"
    } else {
        $commitsAhead  = (git rev-list --count origin/main..HEAD 2>$null) -replace '\s'
        $commitsBehind = (git rev-list --count HEAD..origin/main 2>$null) -replace '\s'
        $changedFiles  = (git diff --name-only origin/main...HEAD 2>$null | Measure-Object).Count

        Write-BrgsLog "Guard 2 — Branch stats: ahead=$commitsAhead behind=$commitsBehind files=$changedFiles"

        if ($changedFiles -gt 200) {
            Write-BrgsLog "BLOCKED: $changedFiles files changed — ancestry mismatch suspected!" "ERR"
            Write-Host "  Fix: rebase onto origin/main"
            exit 1
        }
        if ($commitsBehind -gt 100) {
            Write-BrgsLog "BLOCKED: Branch is $commitsBehind commits behind main — rebase required" "ERR"
            exit 1
        }
        Write-BrgsLog "Guard 2 — Ancestry validated" "OK"
    }
} else {
    Write-BrgsLog "Guard 2 — Skipping (on $CurrentBranch)" "OK"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Guard 3: Forbidden paths check
# ═══════════════════════════════════════════════════════════════════════════════

if ($ForbiddenPaths.Count -gt 0) {
    $changedFiles = git diff --name-only HEAD...origin/main 2>$null
    if (-not $changedFiles) {
        $changedFiles = git diff --name-only HEAD 2>$null
    }

    if ($changedFiles) {
        $violated = @()
        foreach ($file in $changedFiles) {
            foreach ($fp in $ForbiddenPaths) {
                $prefix = $fp.TrimEnd('/')
                if ($file.StartsWith("$prefix/") -or $file -eq $prefix) {
                    $violated += $file
                    break
                }
            }
        }

        if ($violated.Count -gt 0) {
            Write-BrgsLog "BLOCKED: Forbidden paths detected in $RepoName" "ERR"
            Write-Host "`n  Modified files in forbidden paths:"
            foreach ($v in $violated) { Write-Host "    $v" }

            $redirectTarget = ""
            foreach ($fp in $ForbiddenPaths) {
                $fpPrefix = $fp.TrimEnd('/')
                foreach ($v in $violated) {
                    if ($v.StartsWith("$fpPrefix/") -and $RedirectMap.ContainsKey($fp)) {
                        $redirectTarget = $RedirectMap[$fp]
                        break
                    }
                }
                if ($redirectTarget) { break }
            }

            if ($redirectTarget) {
                Write-Host "`n  These paths belong to: $redirectTarget"
                Write-Host "`n  Fix:"
                Write-Host "    git stash"
                Write-Host "    cd <path/to/$redirectTarget>"
                Write-Host "    git checkout -b <prefix>/feat/your-branch"
                Write-Host "    git stash pop && git add . && git commit -m 'feat: your feature'"
                Write-Host "    git push origin <prefix>/feat/your-branch"
            }

            Write-Host "`n  Bypass (NOT recommended): git push --no-verify`n"
            exit 1
        }
    }
    Write-BrgsLog "Guard 3 — No forbidden path violations" "OK"
} else {
    Write-BrgsLog "Guard 3 — No forbidden paths configured" "OK"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Guard 4: Branch prefix validation
# ═══════════════════════════════════════════════════════════════════════════════

if ($AllowedPrefixes.Count -gt 0 -and $CurrentBranch -notin @("main", "dev")) {
    $prefixOk = $false
    foreach ($p in $AllowedPrefixes) {
        $cleanP = $p.TrimEnd('/')
        if ($CurrentBranch.StartsWith($cleanP)) {
            $prefixOk = $true
            break
        }
    }

    if (-not $prefixOk) {
        Write-BrgsLog "BLOCKED: Branch prefix mismatch in $RepoName" "ERR"
        Write-Host "`n  Branch: $CurrentBranch"
        Write-Host "  Allowed prefixes:"
        foreach ($p in $AllowedPrefixes) { Write-Host "    $p" }

        # Check if the branch name suggests another repo
        $branchRepoPrefix = $CurrentBranch.Split("/")[0]
        switch ($branchRepoPrefix) {
            "ecos-cli"   { Write-Host "`n  Suggests ECOS-CLI. Try: git checkout -b ecos-cli/$CurrentBranch" }
            "ecosystem"  { Write-Host "`n  Suggests ECOYSTEM. Try: git checkout -b ecosystem/$CurrentBranch" }
            "devtools"   { Write-Host "`n  Suggests DevTools. Try: git checkout -b devtools/$CurrentBranch" }
            "fluence"    { Write-Host "`n  Suggests FLUENCE. Try: git checkout -b fluence/$CurrentBranch" }
        }

        Write-Host "`n  Bypass (NOT recommended): git push --no-verify`n"
        exit 1
    }
    Write-BrgsLog "Guard 4 — Branch prefix validated ($CurrentBranch)" "OK"
} else {
    Write-BrgsLog "Guard 4 — Skipping (on $CurrentBranch or no rules)" "OK"
}

# ── All guards passed ─────────────────────────────────────────────────────────
Write-Host "`n[BRGS] ✅ All guards passed — proceeding with push"
exit 0
