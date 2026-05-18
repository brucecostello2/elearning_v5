#!/usr/bin/env bash
# tier_migration_manual.sh — force tier migration for a project or specific files
# Usage:
#   bash tier_migration_manual.sh --project 42 --target warm
#   bash tier_migration_manual.sh --outputs "1001,1002,1003" --target cold
set -euo pipefail

TARGET_TIER=""
PROJECT_ID=""
OUTPUT_IDS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)  PROJECT_ID="$2"; shift 2 ;;
    --outputs)  OUTPUT_IDS="$2"; shift 2 ;;
    --target)   TARGET_TIER="$2"; shift 2 ;;
    *)          echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[ -z "$TARGET_TIER" ] && { echo "ERROR: --target required"; exit 1; }

python3 - <

.github/workflows/phase4-tests.ymlname: Phase 4 Tests

on:
  pull_request:
    paths: ["app/services/**", "app/tasks/**", "migrations/**"]
  push:
    branches: [main, release/*]

jobs:
  phase4-unit:
    runs-on: ubuntu-22.04
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ivgs
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: ivgs_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-retries 10

    env:
      DATABASE_URL: postgresql://ivgs:testpass@localhost:5432/ivgs_test
      SEAWEEDFS_MASTER_URL: http://localhost:9333
      SEAWEEDFS_FILER_URL: http://localhost:8888
      NAS_BACKUP_PATH: /tmp/test-backup

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-test.txt

      - name: Start SeaweedFS mock
        run: |
          # Use weed-mock Docker image for unit test isolation
          docker run -d --name weed-mock -p 9333:9333 -p 8888:8888 \
            chrislusf/seaweedfs:latest server -dir=/tmp/weed-data
          sleep 3

      - name: Run Alembic migrations
        run: alembic upgrade head

      - name: Run Phase 4 unit tests
        run: |
          pytest tests/phase4/ -v \
            --cov=app/services \
            --cov=app/tasks \
            --cov-report=term-missing \
            -k "not integration"

      - name: Lint Phase 4 services
        run: |
          ruff check app/services/seaweedfs_client.py \
            app/services/retention_service.py \
            app/services/tier_migration_service.py \
            app/services/backup_service.py
