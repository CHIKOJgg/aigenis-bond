"""Size budget enforcement (ArchitectureAudit A-12).

Prevents new oversized files. Thresholds apply to the whole repo; legacy
files that already exceed the budget are recorded in ``LEGACY`` and must be
split during refactoring passes instead of raising the thresholds.

Complexity is enforced separately by ruff (C901, max-complexity=12, with a
recorded baseline for legacy modules).

Usage:
    python scripts/check_size_budget.py            # default roots
    python scripts/check_size_budget.py --json     # machine-readable report
    python scripts/check_size_budget.py --verbose  # include compliant files

Exit code 1 when any non-legacy file exceeds its budget.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (glob, max_lines, max_bytes) — first matching rule wins.
LIMITS = [
    ("**/*.py", 1000, 45_000),
    ("frontend/src/**/*.{ts,tsx}", 650, 30_000),
    ("frontend/src/i18n/dicts/**/*.ts", 1500, 40_000),
]

# Directories never scanned (generated, vendored, or non-source).
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "playwright-report",
    "test-results",
    "__pycache__",
    "bonds_engine.egg-info",
    "alembic/versions",
    "ml/artifacts",
    "frontend/public/assets",
    "logs",
    "demo-data",
}

# Test files are allowed to grow; the budget targets production source.
EXCLUDE_PATTERNS = ("**/test_*.py", "**/__tests__/**", "**/*.min.js", "**/e2e/**")

# Legacy files over the budget, recorded so the checker stays green while
# these modules are split in refactoring passes (do not add new entries here
# for anything that is not already in the repo).
LEGACY = {
    "telegram_bot/commands.py": "1149 lines / 55 KB bot command hub; split into per-command modules",
    "api/demo.py": "1305 lines / 60 KB demo API (manifest-driven snapshot, impact math, stress, optimize); split on next refactor pass",
}


def _matches(path: Path, pattern: str) -> bool:
    return path.match(pattern)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--verbose", action="store_true", help="include compliant files")
    args = parser.parse_args()

    violations: list[dict] = []
    report: list[dict] = []
    checked = 0

    for rule in LIMITS:
        glob, max_lines, max_bytes = rule
        for path in ROOT.glob(glob):
            if not path.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if any(path.match(p) for p in EXCLUDE_PATTERNS):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in LEGACY:
                continue
            checked += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            line_count = text.count("\n")
            byte_count = path.stat().st_size
            entry = {
                "path": rel,
                "lines": line_count,
                "bytes": byte_count,
                "max_lines": max_lines,
                "max_bytes": max_bytes,
            }
            report.append(entry)
            if line_count > max_lines or byte_count > max_bytes:
                entry["rule"] = glob
                violations.append(entry)

    if args.json:
        print(
            json.dumps(
                {"checked": checked, "violations": violations, "files": report},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1 if violations else 0

    print(f"size_budget: checked {checked} files")
    for v in violations:
        print(
            f"  FAIL {v['path']}: {v['lines']} lines / {v['bytes']} bytes "
            f"(limit {v['max_lines']} / {v['max_bytes']})"
        )
    if not violations:
        print("size_budget: all files within budget")
        return 0
    print(
        "size_budget: split the files above; legacy over-budget modules are "
        "tracked in LEGACY (see scripts/check_size_budget.py)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
