"""
Test suite for the compliance scanner (§F.2).
Verifies detection of all prohibited patterns.
"""

import subprocess
import tempfile
import os
import pytest


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
    result = subprocess.run(
        ["python", "/ivgs/scripts/compliance_scanner.py", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"Scanner should have caught: {env_var}"


@pytest.mark.parametrize("package", PROHIBITED_PIP_PACKAGES)
def test_scanner_detects_pip_packages(package, tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(package)
    result = subprocess.run(
        ["python", "/ivgs/scripts/compliance_scanner.py", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"Scanner should have caught: {package}"


@pytest.mark.parametrize("import_line", PROHIBITED_IMPORTS)
def test_scanner_detects_imports(import_line, tmp_path):
    py_file = tmp_path / "test_module.py"
    py_file.write_text(import_line)
    result = subprocess.run(
        ["python", "/ivgs/scripts/compliance_scanner.py", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"Scanner should have caught: {import_line}"


@pytest.mark.parametrize("url", PROHIBITED_URLS)
def test_scanner_detects_urls(url, tmp_path):
    py_file = tmp_path / "client.py"
    py_file.write_text(f'API_URL = "https://{url}"')
    result = subprocess.run(
        ["python", "/ivgs/scripts/compliance_scanner.py", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"Scanner should have caught URL: {url}"


def test_scanner_passes_clean_code(tmp_path):
    """Verify scanner passes on compliant code."""
    py_file = tmp_path / "clean.py"
    py_file.write_text("from ivgs.shared.providers import LLMProvider\n")
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("httpx==0.27.0\ncelery==5.4.0\n")
    result = subprocess.run(
        ["python", "/ivgs/scripts/compliance_scanner.py", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "Scanner should pass on clean code"
