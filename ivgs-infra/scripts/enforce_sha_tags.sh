#!/bin/bash
# Enforce SHA-256 digest pinning for all Docker image tags.
# Run as CI step before deployment.

set -euo pipefail

COMPOSE_FILES=(
    docker-compose.node01.yml
    docker-compose.node02.yml
    docker-compose.node03.yml
    docker-compose.node04.yml
    docker-compose.node05.yml
    docker-compose.node06.yml
)

ERRORS=0

for file in "${COMPOSE_FILES[@]}"; do
    if grep -q ':-latest' "$file"; then
        echo "ERROR: $file contains ':latest' fallback tag"
        grep -n ':-latest' "$file"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check env vars
for var in IVGS_API_TAG IVGS_SCHEDULER_TAG IVGS_FRONTEND_TAG IVGS_WORKER_TAG; do
    val="${!var:-}"
    if [[ -z "$val" ]]; then
        echo "ERROR: $var is not set"
        ERRORS=$((ERRORS + 1))
    elif [[ "$val" == "latest" ]]; then
        echo "ERROR: $var is set to 'latest' — must use SHA digest"
        ERRORS=$((ERRORS + 1))
    fi
done

if [[ $ERRORS -gt 0 ]]; then
    echo "FAILED: $ERRORS SHA pinning violations found"
    exit 1
fi

echo "PASSED: All image tags are properly pinned"
