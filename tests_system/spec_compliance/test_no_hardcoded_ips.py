"""Spec-compliance guard (subsumes P2.14): the obsolete 10.10.0.x node scheme must
never re-enter tracked code/config. Spec 2.3 mandates 192.168.1.0/24, single-sourced
via the NODE_0x_IP registry in node-01 .env. The pre-commit hook is the fast local
gate; this test is the CI / full-suite backstop.

OUTSTANDING_WORK.md documents the migration history (and legitimately names the old
scheme), and this guard necessarily references the pattern, so both are excluded.
"""
import subprocess
from pathlib import Path

# Assembled from fragments so the literal obsolete-scheme string never appears verbatim
# here -- keeps both the pre-commit hook and this very scan from matching the guard.
_OBSOLETE = r"10\." + r"10\.0\.[0-9]"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXCLUDES = (":(exclude)OUTSTANDING_WORK.md",
             ":(exclude)tests/spec_compliance/test_no_hardcoded_ips.py")


def test_no_obsolete_ip_scheme_in_tracked_files():
    """No tracked file may carry a 10.10.0.x literal (spec 2.3 -> 192.168.1.0/24)."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "grep", "-nIE", _OBSOLETE, "--", ".", *_EXCLUDES],
        capture_output=True, text=True,
    )
    # git grep: 0 = matches found (FAIL), 1 = none (PASS), >1 = error.
    assert result.returncode == 1, (
        "Obsolete 10.10.0.x scheme found in tracked files "
        "(spec 2.3 mandates 192.168.1.0/24 via the NODE_0x_IP registry):\n" + result.stdout
    )
