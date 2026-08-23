#!/bin/bash
# IVGS v5 — Pre-Deployment Spec Compliance Verification
# Run from repository root: bash scripts/verify_spec_compliance.sh
set -u

PASS=0
FAIL=0

check() {
    local label="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo "  ✅ PASS: $label"
        ((PASS++))
    else
        echo "  ❌ FAIL: $label"
        ((FAIL++))
    fi
}

echo "=========================================="
echo "IVGS v5 Pre-Deployment Compliance Check"
echo "=========================================="
echo ""

# --- Gate 1: Prohibited Dependencies ---
echo "--- Gate 1: Prohibited Dependencies ---"
if grep -rqE "^import openai|^from openai" --include="*.py" --exclude-dir=".git" .; then
    check "No openai imports" "FAIL"
else
    check "No openai imports" "PASS"
fi

# Check for prohibited env vars (excluding comments, test files, scanner, and documentation)
if grep -rE "OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|DID_API_KEY|REPLICATE_API_TOKEN" \
    --include="*.env*" --include="*.yml" --include="*.yaml" --include="*.py" \
    --exclude-dir=".git" --exclude-dir="tests" --exclude-dir="tests_system" \
    --exclude="compliance_scanner.py" --exclude="compliance-check.yml" \
    --exclude="test_*.py" --exclude="verify_spec_compliance.sh" \
    . 2>/dev/null | grep -v "# .*NEVER" | grep -qv "^$"; then
    check "No prohibited env vars" "FAIL"
else
    check "No prohibited env vars" "PASS"
fi

# --- Gate 2: Python & Linting ---
echo ""
echo "--- Gate 2: Python & Linting ---"
if grep -q '"3.12"' .github/workflows/ci.yml 2>/dev/null; then
    check "CI uses Python 3.12" "PASS"
else
    check "CI uses Python 3.12" "FAIL"
fi

if grep -q "tool.ruff" pyproject.toml 2>/dev/null; then
    check "ruff configured in pyproject.toml" "PASS"
else
    check "ruff configured in pyproject.toml" "FAIL"
fi

if grep -q "flake8" .github/workflows/ci.yml 2>/dev/null; then
    check "No flake8 in CI" "FAIL"
else
    check "No flake8 in CI" "PASS"
fi

if grep -q "flake8" pyproject.toml 2>/dev/null; then
    check "No flake8 in pyproject.toml" "FAIL"
else
    check "No flake8 in pyproject.toml" "PASS"
fi

if grep -qE "3\.11|py311" pyproject.toml .pre-commit-config.yaml .github/workflows/ci.yml 2>/dev/null; then
    check "No Python 3.11 references" "FAIL"
else
    check "No Python 3.11 references" "PASS"
fi

# --- Gate 3: Database Migrations ---
echo ""
echo "--- Gate 3: Database Migrations ---"
MIGRATION_COUNT=$(ls ivgs-api/migrations/versions/0*.py 2>/dev/null | wc -l)
if [ "$MIGRATION_COUNT" -eq 14 ]; then
    check "Exactly 14 migrations" "PASS"
else
    check "Exactly 14 migrations ($MIGRATION_COUNT found)" "FAIL"
fi

if ls ivgs-api/migrations/versions/001[5-9]*.py 2>/dev/null | grep -q .; then
    check "No extra migrations (0015+)" "FAIL"
else
    check "No extra migrations (0015+)" "PASS"
fi

# --- Gate 4: GPU Configuration ---
echo ""
echo "--- Gate 4: GPU Configuration ---"
if grep -q "node_hardware" ivgs-api/config/gpu_requirements.yaml 2>/dev/null; then
    check "node_hardware section exists" "PASS"
else
    check "node_hardware section exists" "FAIL"
fi

GPU_MODEL_COUNT=$(grep -c "gpu_model" ivgs-api/config/gpu_requirements.yaml 2>/dev/null || echo 0)
if [ "$GPU_MODEL_COUNT" -ge 5 ]; then
    check "GPU model names present ($GPU_MODEL_COUNT)" "PASS"
else
    check "GPU model names present ($GPU_MODEL_COUNT)" "FAIL"
fi

if grep -iqE "A100|A40|A10G|T4|hourly_rate" ivgs-api/config/gpu_requirements.yaml 2>/dev/null; then
    check "No cloud GPU references" "FAIL"
else
    check "No cloud GPU references" "PASS"
fi

# --- Gate 5: Repository Structure ---
echo ""
echo "--- Gate 5: Repository Structure ---"
for dir in ivgs-api ivgs-frontend ivgs-scheduler ivgs-workers ivgs-infra ivgs-models shared docs/adr; do
    if [ -d "$dir" ]; then
        check "Directory: $dir/" "PASS"
    else
        check "Directory: $dir/" "FAIL"
    fi
done

if [ -f "ivgs-models/download_models.sh" ] && [ -x "ivgs-models/download_models.sh" ]; then
    check "Model download script (executable)" "PASS"
else
    check "Model download script (executable)" "FAIL"
fi

# --- Gate 6: Configuration Files ---
echo ""
echo "--- Gate 6: Configuration Files ---"
for f in gpu_requirements.yaml quality_thresholds.yaml retry_policies.yaml timeout_defaults.yaml fallback_policies.yaml; do
    if [ -f "ivgs-api/config/$f" ]; then
        check "Config: ivgs-api/config/$f" "PASS"
    else
        check "Config: ivgs-api/config/$f" "FAIL"
    fi
done

for f in grafana-pipeline.json grafana-gpu.json; do
    if [ -f "configs/grafana/dashboards/$f" ]; then
        check "Dashboard: $f" "PASS"
    else
        check "Dashboard: $f" "FAIL"
    fi
done

# --- Gate 7: CI/CD & Branch Strategy ---
echo ""
echo "--- Gate 7: CI/CD & Branch Strategy ---"
if grep -q "develop" .github/workflows/ci.yml 2>/dev/null; then
    check "CI triggers include develop" "PASS"
else
    check "CI triggers include develop" "FAIL"
fi

if grep -q "Git Workflow" README.md 2>/dev/null; then
    check "Branch strategy in README" "PASS"
else
    check "Branch strategy in README" "FAIL"
fi

if grep -q "staging" .github/workflows/ci.yml 2>/dev/null; then
    check "No staging refs in CI" "FAIL"
else
    check "No staging refs in CI" "PASS"
fi

if grep -iq "timescale" .github/workflows/ci.yml 2>/dev/null; then
    check "No TimescaleDB in CI" "FAIL"
else
    check "No TimescaleDB in CI" "PASS"
fi

if grep -iq "timescale" .env.template 2>/dev/null; then
    check "No TimescaleDB in .env.template" "FAIL"
else
    check "No TimescaleDB in .env.template" "PASS"
fi

# --- Summary ---
echo ""
echo "=========================================="
TOTAL=$((PASS + FAIL))
echo "Results: $PASS/$TOTAL passed, $FAIL failed"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    echo "❌ DEPLOYMENT BLOCKED — $FAIL checks failed"
    exit 1
else
    echo "✅ ALL CHECKS PASSED — Ready for hardware deployment"
    exit 0
fi
