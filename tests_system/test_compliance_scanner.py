"""
Test suite for the compliance scanner (§F.2).
Verifies detection of all prohibited patterns.

WP-52 -- three root causes, two of them here:

1. Every case shelled out to `"python"`. node-01 has `python3` only, so
   `subprocess.run` raised `FileNotFoundError` before the scanner ran. All 19
   tests failed on that alone. Now `sys.executable`, which is also the only way
   to guarantee the interpreter running the tests is the one being tested.

2. The script path was `/ivgs/scripts/compliance_scanner.py` -- the path the
   repo is mounted at INSIDE the containers. On the host the repo is
   `/opt/ivgs`, and `/ivgs` holds only `rollback_points`. Fixing (1) alone would
   have been worse than leaving it: a missing script exits 2, and 18 of these 19
   tests assert only `returncode != 0`, so they would have gone green while
   proving nothing at all. The path is now derived from `__file__`, so it
   follows the checkout.

3. NOT fixed here, and not fixable here: the scanner does not implement §F.2
   Rule 2. `match_glob` handles only `*`-prefixed globs and exact names, so
   `"requirements*.txt"` matches no file and prohibited pip packages are never
   scanned for. That is a defect in `scripts/compliance_scanner.py`, not in this
   file, and the four `test_scanner_detects_pip_packages` cases are RIGHT to
   fail. Ledger P2.49.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# The scanner under test, resolved from this file rather than from a mount path.
SCANNER = str(Path(__file__).resolve().parents[1] / "scripts" / "compliance_scanner.py")


def run_scanner(target_dir) -> subprocess.CompletedProcess:
    """Run the compliance scanner over `target_dir` and return the result."""
    return subprocess.run(
        [sys.executable, SCANNER, str(target_dir)],
        capture_output=True,
        text=True,
    )


PROHIBITED_ENV_VARS = [
    "OPENAI_API_KEY=sk-test123",
    "ANTHROPIC_API_KEY=sk-ant-test",
    "ELEVENLABS_API_KEY=test",
    "DID_API_KEY=test",
    "SYNTHESIA_API_KEY=test",
]

PROHIBITED_PIP_PACKAGES = [
    "openai==1.0.0",
    "anthropic==0.5.0",
    "elevenlabs==0.2.0",
    "did-client==1.0.0",
]

PROHIBITED_IMPORTS = [
    "import openai",
    "from openai import OpenAI",
    "import anthropic",
    "from anthropic import Anthropic",
    "import elevenlabs",
]

PROHIBITED_URLS = [
    "api.openai.com/v1/chat/completions",
    "api.anthropic.com/v1/messages",
    "api.elevenlabs.io/v1/text-to-speech",
    "api.d-id.com/talks",
]


@pytest.mark.parametrize("env_var", PROHIBITED_ENV_VARS)
def test_scanner_detects_env_vars(env_var, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(env_var)
    result = run_scanner(tmp_path)
    assert result.returncode != 0, f"Scanner should have caught: {env_var}"


@pytest.mark.parametrize("package", PROHIBITED_PIP_PACKAGES)
def test_scanner_detects_pip_packages(package, tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(package)
    result = run_scanner(tmp_path)
    assert result.returncode != 0, f"Scanner should have caught: {package}"


@pytest.mark.parametrize("import_line", PROHIBITED_IMPORTS)
def test_scanner_detects_imports(import_line, tmp_path):
    py_file = tmp_path / "test_module.py"
    py_file.write_text(import_line)
    result = run_scanner(tmp_path)
    assert result.returncode != 0, f"Scanner should have caught: {import_line}"


@pytest.mark.parametrize("url", PROHIBITED_URLS)
def test_scanner_detects_urls(url, tmp_path):
    py_file = tmp_path / "client.py"
    py_file.write_text(f'API_URL = "https://{url}"')
    result = run_scanner(tmp_path)
    assert result.returncode != 0, f"Scanner should have caught URL: {url}"


def test_scanner_passes_clean_code(tmp_path):
    """Verify scanner passes on compliant code."""
    py_file = tmp_path / "clean.py"
    py_file.write_text("from ivgs.shared.providers import LLMProvider\n")
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("httpx==0.27.0\ncelery==5.4.0\n")
    result = run_scanner(tmp_path)
    assert result.returncode == 0, "Scanner should pass on clean code"


# ---------------------------------------------------------------------------
# WP-63 Task 10 — the exemption pragma
# ---------------------------------------------------------------------------
#
# CI runs #262 (6a3b074) and #263 (8f64692) failed at compliance-scan on one
# line: `tests_system/test_wp61_node05.py:251`, the WP-61 test that ASSERTS
# those three variables are absent from node-05's environment. Downstream jobs
# cancel on the failed gate, so CI has been fully red since the WP-61 push.
#
# The scanner was fixed, not the test. These cases gate the fix in both
# directions: an exemption must work, and it must be impossible to get one
# quietly or by accident.


VIOLATING_LINE = 'for banned in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):'


def _write(tmp_path, line: str, name: str = "sample.py"):
    (tmp_path / name).write_text(line + "\n")
    return run_scanner(tmp_path)


def test_a_violating_line_still_fails(tmp_path):
    """The baseline. Everything below is only meaningful if this holds."""
    result = _write(tmp_path, VIOLATING_LINE)
    assert result.returncode != 0
    assert "Violations found:    1" in result.stdout


@pytest.mark.parametrize("suffix,should_pass,why", [
    ("", False, "no pragma at all"),
    ("  # compliance-exempt", False, "bare pragma: no rule id, no reason"),
    ("  # compliance-exempt: F.2-R1", False, "rule id but no reason"),
    ("  # compliance-exempt: F.2-R1 -", False, "separator but empty reason"),
    ("  # compliance-exempt: - a reason", False, "reason but no rule id"),
    ("  # compliance-exempt: F.2-R4 - wrong rule", False, "pragma names another rule"),
    ("  # compliance-exempt: F.2-R1 - asserts these names are ABSENT", True,
     "correct rule id and a reason"),
    ("  # compliance-exempt: F.2-R1, F.2-R4 - two rules, one line", True,
     "a list of rule ids, one of which matches"),
])
def test_the_pragma_is_honoured_only_when_it_is_complete_and_correct(
    tmp_path, suffix, should_pass, why,
):
    result = _write(tmp_path, VIOLATING_LINE + suffix)
    if should_pass:
        assert result.returncode == 0, f"{why}: expected a pass\n{result.stdout}"
    else:
        assert result.returncode != 0, f"{why}: expected a FAILURE\n{result.stdout}"


def test_an_applied_exemption_is_listed_in_the_report(tmp_path):
    """An exemption nobody can see is a rule nobody is enforcing."""
    result = _write(
        tmp_path,
        VIOLATING_LINE + "  # compliance-exempt: F.2-R1 - asserts these names are ABSENT",
    )
    assert result.returncode == 0, result.stdout
    assert "Exemptions applied:  1" in result.stdout
    assert "F.2-R1" in result.stdout
    assert "asserts these names are ABSENT" in result.stdout
    assert "sample.py:1" in result.stdout


def test_the_wrong_rule_id_is_reported_as_a_violation_not_an_exemption(tmp_path):
    """A pragma for another rule must not even be counted as an exemption.

    Otherwise the report would say a line was excused when it was not, which is
    the same class of lie in the other direction.
    """
    result = _write(
        tmp_path, VIOLATING_LINE + "  # compliance-exempt: F.2-R4 - wrong rule",
    )
    assert result.returncode != 0
    assert "Exemptions applied:  0" in result.stdout
    assert "Violations found:    1" in result.stdout


def test_a_pragma_on_a_neighbouring_line_does_not_reach(tmp_path):
    """It has to sit on the line it excuses, or it drifts away from it."""
    (tmp_path / "sample.py").write_text(
        "# compliance-exempt: F.2-R1 - on the wrong line\n" + VIOLATING_LINE + "\n"
    )
    assert run_scanner(tmp_path).returncode != 0


def test_the_slash_comment_form_works_for_typescript(tmp_path):
    (tmp_path / "sample.ts").write_text(
        'const u = "https://api.openai.com/v1";'
        "  // compliance-exempt: F.2-R3 - names the host in a blocklist\n"
    )
    result = run_scanner(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "F.2-R3" in result.stdout


def test_the_repository_itself_scans_clean_with_its_exemption_listed():
    """The acceptance criterion, run against the real tree.

    Not a tmp_path fixture: the thing that has to be true is that THIS
    repository passes, and that the one exemption it relies on is visible in
    the output rather than inferred from an exit code.
    """
    repo = Path(__file__).resolve().parents[1]
    result = run_scanner(repo)
    assert result.returncode == 0, result.stdout[-4000:]
    assert "tests_system/test_wp61_node05.py" in result.stdout
    assert "asserts these names are ABSENT" in result.stdout


def test_files_skipped_wholesale_are_named(tmp_path):
    """SKIP_FILES is an exemption too, and it was silent until this package."""
    result = run_scanner(Path(__file__).resolve().parents[1])
    assert "Files skipped wholesale" in result.stdout
    assert "compliance_scanner.py" in result.stdout
