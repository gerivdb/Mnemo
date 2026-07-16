#!/usr/bin/env python3
"""
ascii_fix.py - Automatic correction of non-ASCII characters.
IntentHash: 0xASCII_FIX_SCRIPT_20260716

Usage:
    python tools/ascii_fix.py --dry-run    # Show violations without modifying
    python tools/ascii_fix.py --fix        # Automatically fix files
    python tools/ascii_fix.py --check      # Check without modification (return 0/1)
    python tools/ascii_fix.py --list       # List available ASCII mappings

This script is called automatically by the pre-commit hook before GATE-6.
"""

import argparse
import sys
import io

# Force UTF-8 output for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
from typing import Dict, List, Tuple, Optional


def load_ascii_map(config_path: Optional[Path] = None) -> Dict[str, str]:
    """Load ASCII mapping from configuration file."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "ascii_map.json"
    
    if config_path.exists():
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    # Default ASCII mapping using Unicode escapes (ASCII-only)
    return {
        # French accents - lowercase
        "\u00e9": "e",  # e acute
        "\u00e8": "e",  # e grave
        "\u00ea": "e",  # e circumflex
        "\u00eb": "e",  # e diaeresis
        "\u00e0": "a",  # a grave
        "\u00e2": "a",  # a circumflex
        "\u00e4": "a",  # a diaeresis
        "\u00f9": "u",  # u grave
        "\u00fb": "u",  # u circumflex
        "\u00fc": "u",  # u diaeresis
        "\u00f4": "o",  # o circumflex
        "\u00f6": "o",  # o diaeresis
        "\u00ee": "i",  # i circumflex
        "\u00ef": "i",  # i diaeresis
        "\u00e7": "c",  # c cedilla
        "\u00ff": "y",  # y diaeresis
        # French accents - uppercase
        "\u00c9": "E",
        "\u00c8": "E",
        "\u00ca": "E",
        "\u00cb": "E",
        "\u00c0": "A",
        "\u00c2": "A",
        "\u00c4": "A",
        "\u00d9": "U",
        "\u00db": "U",
        "\u00dc": "U",
        "\u00d4": "O",
        "\u00d6": "O",
        "\u00ce": "I",
        "\u00cf": "I",
        "\u00c7": "C",
        # Common symbols
        "\u2026": "...",  # ellipsis
        "\u2013": "-",    # en dash
        "\u2014": "--",   # em dash
        "\u00ab": '"',    # left guillemet
        "\u00bb": '"',    # right guillemet
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        # Arrows
        "\u2192": "->",  # right arrow
        "\u2193": "v",   # down arrow
        "\u2191": "^",   # up arrow
        "\u2190": "<-",  # left arrow
        "\u2194": "<->", # left-right arrow
        # Currency
        "\u20ac": "EUR", # euro
        "\u00a3": "GBP", # pound
        "\u00a5": "JPY", # yen
        # Mathematical
        "\u00b0": "deg", # degree
        "\u00b1": "+/-", # plus-minus
        "\u00d7": "x",   # multiplication
        "\u00f7": "/",   # division
        "\u00bc": "1/4", # 1/4
        "\u00bd": "1/2", # 1/2
        "\u00be": "3/4", # 3/4
        # Check marks
        "\u2713": "OK",  # check mark
        "\u2717": "X",   # X mark
        "\u2714": "OK",  # ballot check
        "\u2715": "X",   # ballot X
        # Stars, bullets
        "\u2605": "*",   # star
        "\u2606": "*",   # white star
        "\u25cf": "*",   # black circle
        "\u25cb": "o",   # white circle
        "\u25a0": "#",   # black square
        "\u25a1": "[]",  # white square
        "\u25c6": "<>",  # black diamond
        "\u25c7": "<>",  # white diamond
        "\u25b2": "^",   # black up triangle
        "\u25bc": "v",   # black down triangle
        "\u25ba": ">",   # black right triangle
        "\u25c4": "<",   # black left triangle
        "\u25b6": ">",   # black right triangle
        "\u25c0": "<",   # black left triangle
        "\u2022": "*",   # bullet
        "\u00b7": "*",   # middle dot
        "\u2027": "...", # horizontal ellipsis
        # Punctuation
        "\u00bf": "?",   # inverted question
        "\u00a1": "!",   # inverted exclamation
    }


def get_allowed_extensions() -> set:
    """Return file extensions to check."""
    return {
        ".yaml", ".yml", ".md", ".py", ".ps1", ".sh",
        ".js", ".ts", ".tsx", ".jsx", ".zig", ".sql",
        ".json", ".txt", ".toml", ".ini", ".cfg"
    }


def get_allowed_files() -> set:
    """Return files allowed with non-ASCII characters."""
    return {"README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE"}


def get_exclusions() -> List[str]:
    """Return patterns to exclude."""
    return ["node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"]


def scan_file(file_path: Path, ascii_map: Dict[str, str]) -> Tuple[bool, List[str], str]:
    """
    Scan a file for non-ASCII characters.
    Returns: (has_violations, modified_lines, corrected_content)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return False, [], ""
    
    violations = []
    lines = content.split("\n")
    corrected_lines = []
    
    for i, line in enumerate(lines, start=1):
        original_line = line
        corrected_line = line
        
        # Check for non-ASCII characters
        for char in ascii_map:
            if char in line:
                corrected_line = corrected_line.replace(char, ascii_map[char])
        
        if corrected_line != original_line:
            violations.append(f"  Line {i}: {original_line[:80]}")
        
        corrected_lines.append(corrected_line)
    
    return len(violations) > 0, violations, "\n".join(corrected_lines)


def scan_directory(repo_root: Path, ascii_map: Dict[str, str]) -> List[Tuple[Path, List[str]]]:
    """Scan all files in a directory."""
    violations = []
    
    for file_path in repo_root.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Skip files in exclusion directories
        if any(part.startswith(".") and part not in {".gitignore"} for part in file_path.parts):
            continue
        
        if any(excl in file_path.parts for excl in get_exclusions()):
            continue
        
        # Check extension
        if file_path.suffix.lower() not in get_allowed_extensions():
            continue
        
        # Allowed files
        if file_path.name in get_allowed_files():
            continue
        
        has_violations, file_violations, _ = scan_file(file_path, ascii_map)
        if has_violations:
            violations.append((file_path, file_violations))
    
    return violations


def fix_file(file_path: Path, ascii_map: Dict[str, str]) -> bool:
    """Fix a file in place."""
    _, _, corrected_content = scan_file(file_path, ascii_map)
    if not corrected_content:
        return False
    
    try:
        file_path.write_text(corrected_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[ERROR] Cannot fix {file_path}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Automatic correction of non-ASCII characters"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show violations without modifying files"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix files"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check without modification (return 0 if OK, 1 if violations)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available ASCII mappings"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process a specific file instead of directory"
    )
    
    args = parser.parse_args()
    
    # Load ASCII mapping
    ascii_map = load_ascii_map()
    
    if args.list:
        print("[ASCII_MAP] Available mappings:")
        for char, replacement in sorted(ascii_map.items(), key=lambda x: len(x[0]), reverse=True):
            try:
                print(f"  {repr(char)} -> {repr(replacement)}")
            except Exception:
                print(f"  [unicode char] -> {repr(replacement)}")
        return 0
    
    # Determine root directory
    repo_root = Path(__file__).resolve().parents[1]
    
    # Process a specific file or entire directory
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = repo_root / file_path
        
        has_violations, violations, _ = scan_file(file_path, ascii_map)
        
        if not has_violations:
            print(f"[ASCII_FIX] OK - {file_path} no violations")
            return 0
        
        if args.dry_run or args.check:
            print(f"[ASCII_FIX] Violations in {file_path}:")
            for v in violations:
                print(v)
            return 1 if args.check else 0
        
        if args.fix:
            if fix_file(file_path, ascii_map):
                print(f"[ASCII_FIX] Fixed: {file_path}")
                return 0
            return 1
    
    # Scan directory
    violations = scan_directory(repo_root, ascii_map)
    
    if not violations:
        print("[ASCII_FIX] OK - no violations detected")
        return 0
    
    if args.dry_run or args.check:
        print(f"[ASCII_FIX] {len(violations)} file(s) with violations:")
        for file_path, file_violations in violations[:10]:  # Limit output
            print(f"\n{file_path}:")
            for v in file_violations[:5]:  # Limit per file
                print(v)
        if len(violations) > 10:
            print(f"... and {len(violations) - 10} more files")
        return 1 if args.check else 0
    
    if args.fix:
        fixed_count = 0
        for file_path, _ in violations:
            if fix_file(file_path, ascii_map):
                print(f"[ASCII_FIX] Fixed: {file_path}")
                fixed_count += 1
        
        print(f"[ASCII_FIX] {fixed_count}/{len(violations)} files fixed")
        return 0
    
    return 0


if __name__ == "__main__":
    sys.exit(main())