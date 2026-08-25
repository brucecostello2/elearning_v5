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
