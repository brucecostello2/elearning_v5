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
# Exemptions (WP-63 Task 10): a flagged line may carry an inline pragma
#   `# compliance-exempt: F.2-R1 - <reason>` (or the `//` form). It is honoured
#   only when the rule id names the rule that flagged THAT line and a reason
#   follows it, and every applied exemption is printed in the report. See the
#   block above RULE_IDS for the full rationale.
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
class Exemption:
    """One line that matched a rule and carried a valid pragma for THAT rule.

    WP-63 Task 10. Every one of these is printed in the report. An exemption
    that is not reported is indistinguishable from a rule that is not enforced,
    and the whole value of this scanner is that its verdict can be trusted.
    """
    rule_id: str
    reason: str
    category: str
    file_path: str
    line_number: int
    line_content: str


@dataclass
class ScanResult:
    """Aggregated scan results."""
    violations: list[Violation] = field(default_factory=list)
    exemptions: list[Exemption] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
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


# ---------------------------------------------------------------------------
# Rule ids, and the inline exemption pragma — WP-63 Task 10
# ---------------------------------------------------------------------------
#
# THE PROBLEM THIS SOLVES, measured. CI runs #262 (6a3b074) and #263 (8f64692)
# both failed at compliance-scan on ONE line:
#
#     tests_system/test_wp61_node05.py:251
#     for banned in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
#
# That is the WP-61 test which ASSERTS THOSE VARIABLES ARE ABSENT from node-05's
# environment. The scanner matches the literal names and cannot tell
# referencing-to-forbid from use. Downstream jobs cancel on the failed gate, so
# CI has been fully red since the WP-61 push.
#
# THE FIX IS TO THE SCANNER, NOT THE TEST. Renaming the test's literals,
# building them with `"OPENAI" + "_API_KEY"`, or deleting the assertion would
# each turn a working compliance test into a decoration to get past a
# compliance scanner. The test's honesty is the point of the test.
#
# THE MECHANISM. A line may carry, in a comment ON THAT LINE:
#
#     # compliance-exempt: F.2-R1 - asserts these names are ABSENT
#
# It is honoured only when ALL THREE of these hold:
#
#   1. the rule id is present and NAMES THE RULE THAT FLAGGED THIS LINE. A
#      pragma for F.2-R4 does not silence an F.2-R1 finding, so an exemption
#      cannot widen itself when a second rule starts matching the same line;
#   2. a reason follows the rule id, non-empty. "Because" has to be written
#      down;
#   3. the pragma is on the flagged line itself, not on a neighbouring line or
#      at the top of the file, so it cannot drift away from what it excuses.
#
# A BARE `# compliance-exempt` IS NOT HONOURED. Neither is one with a rule id
# and no reason. Both fail closed, as a violation.
#
# AND EVERY APPLIED EXEMPTION IS PRINTED. `print_report` lists each one with its
# rule, file, line and reason, on clean runs as well as failing ones. An
# exemption nobody can see is a rule nobody is enforcing.

RULE_IDS = {
    "Prohibited env vars (§F.2 Rule 1)": "F.2-R1",
    "Prohibited pip packages (§F.2 Rule 2)": "F.2-R2",
    "Prohibited API endpoints (§F.2 Rule 3)": "F.2-R3",
    "Prohibited imports (§F.2 Rule 4)": "F.2-R4",
}

#: `# compliance-exempt: <ids> <separator> <reason>` or the `//` equivalent.
#: ``<ids>`` is one or more rule ids, comma-separated. The separator before the
#: reason may be ``-``, an en/em dash, or ``:``.
EXEMPT_PRAGMA = re.compile(
    r"(?:#|//)\s*compliance-exempt\s*:\s*"
    r"(?P<ids>[A-Za-z0-9.\-]+(?:\s*,\s*[A-Za-z0-9.\-]+)*)"
    r"\s*(?:-|\u2013|\u2014|:)\s*"
    r"(?P<reason>\S.*?)\s*$"
)


def parse_exemption(line: str) -> Optional[tuple[set[str], str]]:
    """The rule ids and reason a line's pragma carries, or None.

    Returns None for a line with no pragma, for a bare ``# compliance-exempt``,
    and for one with a rule id but no reason — all three fail closed.
    """
    match = EXEMPT_PRAGMA.search(line)
    if match is None:
        return None
    ids = {part.strip() for part in match.group("ids").split(",") if part.strip()}
    reason = match.group("reason").strip()
    if not ids or not reason:
        return None
    return ids, reason


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
) -> tuple[list[Violation], list[Exemption]]:
    """Scan a single file, returning its violations AND the exemptions applied.

    The two are returned together on purpose: a caller cannot take the verdict
    without also receiving what was excused from it.
    """
    if not match_glob(file_path.name, file_globs):
        return [], []
    if file_path.name in SKIP_FILES:
        return [], []

    rule_id = RULE_IDS.get(category, category)
    violations: list[Violation] = []
    exemptions: list[Exemption] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.splitlines(), start=1):
            # Skip comment lines that are documentation (like "# PROHIBITED" sections)
            stripped = line.strip()
            if stripped.startswith("#") and ("PROHIBITED" in stripped or "NEVER" in stripped):
                continue
            if stripped.startswith("//") and ("PROHIBITED" in stripped or "NEVER" in stripped):
                continue

            if not pattern.search(line):
                continue

            parsed = parse_exemption(line)
            if parsed is not None and rule_id in parsed[0]:
                exemptions.append(Exemption(
                    rule_id=rule_id,
                    reason=parsed[1],
                    category=category,
                    file_path=str(file_path),
                    line_number=i,
                    line_content=stripped[:120],
                ))
                continue

            violations.append(Violation(
                category=category,
                pattern=pattern.pattern[:60],
                file_path=str(file_path),
                line_number=i,
                line_content=stripped[:120],
            ))
    except (OSError, UnicodeDecodeError):
        pass
    return violations, exemptions


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

            if filename in SKIP_FILES:
                # WP-63 Task 10. Reported, not silent. These four are excused
                # WHOLESALE and always have been; until now nothing said so in
                # the output, which is the same defect the pragma mechanism
                # exists to prevent — one file at a time instead of one line.
                result.skipped_files.append(str(file_path))

            for category, pattern, globs in scan_configs:
                violations, exemptions = scan_file(
                    file_path, category, pattern, globs,
                )
                result.violations.extend(violations)
                result.exemptions.extend(exemptions)

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
    print(f"Exemptions applied:  {len(result.exemptions)}")
    print(f"Files skipped whole: {len(result.skipped_files)}")
    print("-" * 72)

    # WP-63 Task 10. EXEMPTIONS ARE PRINTED FIRST AND ALWAYS, on a clean run as
    # well as a failing one. A scanner that reports "0 violations" while
    # silently excusing lines is worse than one that reports nothing.
    if result.exemptions:
        print("  [Exemptions applied - each honoured because its pragma names")
        print("   the rule that flagged the line, and gives a reason]")
        for ex in sorted(
            result.exemptions, key=lambda e: (e.file_path, e.line_number)
        ):
            print(f"    {ex.file_path}:{ex.line_number}  [{ex.rule_id}]")
            print(f"      -> {ex.line_content}")
            print(f"      reason: {ex.reason}")
        print()

    if result.skipped_files:
        print("  [Files skipped wholesale - not scanned by any rule]")
        for path in sorted(set(result.skipped_files)):
            print(f"    {path}")
        print()

    if result.is_clean:
        print("✓ No prohibited dependencies found")
        if result.exemptions:
            print(
                f"✓ Compliance check PASSED "
                f"({len(result.exemptions)} exemption(s) applied, listed above)"
            )
        else:
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
