#!/usr/bin/env python3
# =============================================================================
# IVGS v5 — Compliance Scanner
# =============================================================================
# Spec reference: Appendix F.2 — Prohibited Dependency Scanner
#                 §18.3 — Prohibited Actions
#                 §1.4 — v5 Mandate and Enforcement
#
# Scans the repository for PROHIBITED dependencies per §F.2:
#   1. Environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY,
#      ELEVENLABS_API_KEY, DID_API_KEY, SYNTHESIA_API_KEY
#   2. Pip packages: openai, anthropic, elevenlabs, did-client, synthesia
#   3. API endpoints: api.openai.com, api.anthropic.com, api.elevenlabs.io,
#      api.d-id.com
#   4. Import patterns: import openai, from openai, import anthropic, etc.
#
# Exit codes:
#   0 — No violations found
#   1 — Violations detected (build should fail)
# =============================================================================

import os
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Optional


@dataclass
class Violation:
    """A single compliance violation."""
    category: str
    pattern: str
    file_path: str
    line_number: int
    line_content: str


@dataclass
class ScanResult:
    """Aggregated scan results."""
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    directories_scanned: int = 0

    @property
    def is_clean(self) -> bool:
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# Scan patterns per §F.2 — EXACT patterns from specification
# ---------------------------------------------------------------------------

# Category 1: Prohibited environment variables
# grep -rE "OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|
#           DID_API_KEY|SYNTHESIA_API_KEY"
#   --include="*.env*" --include="*.yml" --include="*.yaml" --include="*.py"
ENV_VAR_PATTERNS = re.compile(
    r"OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|"
    r"DID_API_KEY|SYNTHESIA_API_KEY"
)
ENV_VAR_FILE_GLOBS = {"*.env*", "*.yml", "*.yaml", "*.py", "*.toml"}

# Category 2: Prohibited pip packages
# grep -rE "^openai|^anthropic|^elevenlabs|^did-client|^synthesia"
#   requirements*.txt pyproject.toml
PIP_PACKAGE_PATTERNS = re.compile(
    r"^(openai|anthropic|elevenlabs|did-client|synthesia)\b",
    re.MULTILINE,
)
PIP_FILE_GLOBS = {"requirements*.txt", "pyproject.toml", "setup.cfg", "setup.py"}

# Category 3: Prohibited API endpoint patterns
# grep -rE "api\.openai\.com|api\.anthropic\.com|api\.elevenlabs\.io|
#           api\.d-id\.com"
#   --include="*.py" --include="*.ts" --include="*.js"
API_ENDPOINT_PATTERNS = re.compile(
    r"api\.openai\.com|api\.anthropic\.com|api\.elevenlabs\.io|api\.d-id\.com"
)
API_FILE_GLOBS = {"*.py", "*.ts", "*.js", "*.tsx", "*.jsx"}

# Category 4: Prohibited import patterns
# grep -rE "^import openai|^from openai|^import anthropic|^from anthropic|
#           ^import elevenlabs"
#   --include="*.py"
IMPORT_PATTERNS = re.compile(
    r"^(import\s+openai|from\s+openai|import\s+anthropic|"
    r"from\s+anthropic|import\s+elevenlabs|from\s+elevenlabs)",
    re.MULTILINE,
)
IMPORT_FILE_GLOBS = {"*.py"}

# Directories to skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "venv", ".venv", "dist", "build", ".eggs",
}

# Files to skip (this scanner itself contains the patterns)
SKIP_FILES = {"compliance_scanner.py", "test_compliance_scanner.py", "v4_to_v5_migration.py", "compliance-check.yml"}


def match_glob(filename: str, globs: set[str]) -> bool:
    """Check if filename matches any of the glob patterns.

    WP-56 Task 0, ledger P2.49. The previous implementation special-cased only
    ``*``-PREFIXED globs and exact filenames. Every glob with an INFIX ``*``
    fell through to the ``filename == pattern`` branch and matched nothing, so
    ``PIP_FILE_GLOBS``' ``"requirements*.txt"`` never selected a file and
    Appendix F.2 **Rule 2 was never enforced** -- the only one of the four
    categories with such a glob. Anyone could add ``openai==1.0.0`` to a
    requirements file and the CI compliance gate stayed green; measured by
    WP-52, all four prohibited packages scored rc=0.

    ``fnmatchcase`` is the whole fix. It is case-SENSITIVE deliberately:
    ``fnmatch.fnmatch`` normalises case against the host platform, which would
    make this scanner's verdict differ between a Linux runner and a macOS
    checkout. A compliance gate that answers differently per platform is worse
    than one that answers wrongly in the same way everywhere.

    The old ``*.env*``-matches-``.env`` special case is not needed and is not
    reproduced: ``fnmatchcase(".env", "*.env*")`` is already True, because both
    stars are free to match the empty string.
    """
    return any(fnmatchcase(filename, pattern) for pattern in globs)


def scan_file(
    file_path: Path,
    category: str,
    pattern: re.Pattern,
    file_globs: set[str],
) -> list[Violation]:
    """Scan a single file for violations."""
    if not match_glob(file_path.name, file_globs):
        return []
    if file_path.name in SKIP_FILES:
        return []

    violations = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.splitlines(), start=1):
            # Skip comment lines that are documentation (like "# PROHIBITED" sections)
            stripped = line.strip()
            if stripped.startswith("#") and ("PROHIBITED" in stripped or "NEVER" in stripped):
                continue
            if stripped.startswith("//") and ("PROHIBITED" in stripped or "NEVER" in stripped):
                continue

            if pattern.search(line):
                violations.append(Violation(
                    category=category,
                    pattern=pattern.pattern[:60],
                    file_path=str(file_path),
                    line_number=i,
                    line_content=line.strip()[:120],
                ))
    except (OSError, UnicodeDecodeError):
        pass
    return violations


def scan_directory(root: Path) -> ScanResult:
    """Recursively scan a directory for all compliance violations."""
    result = ScanResult()

    scan_configs = [
        ("Prohibited env vars (§F.2 Rule 1)", ENV_VAR_PATTERNS, ENV_VAR_FILE_GLOBS),
        ("Prohibited pip packages (§F.2 Rule 2)", PIP_PACKAGE_PATTERNS, PIP_FILE_GLOBS),
        ("Prohibited API endpoints (§F.2 Rule 3)", API_ENDPOINT_PATTERNS, API_FILE_GLOBS),
        ("Prohibited imports (§F.2 Rule 4)", IMPORT_PATTERNS, IMPORT_FILE_GLOBS),
    ]

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        result.directories_scanned += 1

        for filename in filenames:
            file_path = Path(dirpath) / filename
            result.files_scanned += 1

            for category, pattern, globs in scan_configs:
                violations = scan_file(file_path, category, pattern, globs)
                result.violations.extend(violations)

    return result


def print_report(result: ScanResult) -> None:
    """Print a formatted compliance report."""
    print("=" * 72)
    print("IVGS v5 — Compliance Scanner Report")
    print("Spec reference: Appendix F.2 — Prohibited Dependency Scanner")
    print("=" * 72)
    print(f"Files scanned:       {result.files_scanned}")
    print(f"Directories scanned: {result.directories_scanned}")
    print(f"Violations found:    {len(result.violations)}")
    print("-" * 72)

    if result.is_clean:
        print("✓ No prohibited dependencies found")
        print("✓ Compliance check PASSED")
    else:
        print("✗ COMPLIANCE CHECK FAILED")
        print()
        # Group by category
        by_category: dict[str, list[Violation]] = {}
        for v in result.violations:
            by_category.setdefault(v.category, []).append(v)

        for category, violations in by_category.items():
            print(f"  [{category}]")
            for v in violations:
                print(f"    {v.file_path}:{v.line_number}")
                print(f"      → {v.line_content}")
            print()

    print("=" * 72)


def main() -> int:
    """Main entry point. Returns 0 on clean scan, 1 on violations."""
    # Determine scan root
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        # Default: scan from repository root (parent of scripts/)
        root = Path(__file__).resolve().parent.parent

    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    print(f"Scanning: {root}")
    result = scan_directory(root)
    print_report(result)

    return 0 if result.is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
