# =============================================================================
# IVGS v5 — Phase 15 Verification Commands
# =============================================================================
# Run these commands to verify the complete Phase 15 implementation.
# All commands assume execution from the /ivgs project root directory.
# =============================================================================

# ---------------------------------------------------------------------------
# 1. Verify all 6 Docker Compose files parse correctly
# ---------------------------------------------------------------------------
for node in node01 node02 node03 node04 node05 node06; do
    docker compose -f "docker-compose.${node}.yml" config --quiet
    echo "✓ docker-compose.${node}.yml — valid"
done
# Expected: all 6 files validate without errors

# ---------------------------------------------------------------------------
# 2. Verify all environment templates exist and contain no real secrets
# ---------------------------------------------------------------------------
for node in node01 node02 node03 node04 node05 node06; do
    test -f ".env.${node}.template" && echo "✓ .env.${node}.template exists"
    grep -c "CHANGE_ME" ".env.${node}.template"
done
# Expected: all 6 templates exist, each contains CHANGE_ME placeholders

# ---------------------------------------------------------------------------
# 3. Verify PROHIBITED markers present in all env templates
# ---------------------------------------------------------------------------
for node in node01 node02 node03 node04 node05 node06; do
    grep -q "OPENAI_API_KEY.*NEVER" ".env.${node}.template" && \
        echo "✓ .env.${node}.template — PROHIBITED markers present"
done
# Expected: all 6 templates contain PROHIBITED section

# ---------------------------------------------------------------------------
# 4. Deploy node-01 (full infrastructure)
# ---------------------------------------------------------------------------
./scripts/deploy-node.sh node01
# Expected: rollback point created, images pulled, stack up, health check pass

# ---------------------------------------------------------------------------
# 5. Deploy all GPU nodes
# ---------------------------------------------------------------------------
for node in node02 node03 node04 node05 node06; do
    ./scripts/deploy-node.sh $node
done
# Expected: each node deploys successfully with health check pass

# ---------------------------------------------------------------------------
# 6. Run compliance scanner
# ---------------------------------------------------------------------------
python scripts/compliance_scanner.py
# Expected: "✓ No prohibited dependencies found"

# ---------------------------------------------------------------------------
# 7. Run integration tests
# ---------------------------------------------------------------------------
pytest tests/integration/ -v
# Expected: all integration tests pass
#   - test_auth_integration.py: 9+ tests pass
#   - test_projects_integration.py: 8+ tests pass
#   - test_pipeline_integration.py: 5+ tests pass
#   - test_gpu_integration.py: 7+ tests pass
#   - test_dlq_integration.py: 4+ tests pass

# ---------------------------------------------------------------------------
# 8. Run E2E tests
# ---------------------------------------------------------------------------
pytest tests/e2e/ -v --timeout=3600
# Expected: full pipeline lifecycle test passes
#   - test_project_lifecycle.py: create → transcript → 7 stages → download
#   - test_localization.py: English project → Spanish variant → download

# ---------------------------------------------------------------------------
# 9. Run GPU smoke tests
# ---------------------------------------------------------------------------
pytest tests/smoke/test_gpu_nodes.py -v
# Expected: all 5 GPU nodes pass model load/inference/teardown

# ---------------------------------------------------------------------------
# 10. Generate API documentation
# ---------------------------------------------------------------------------
./scripts/generate_docs.sh
# Expected: docs/api/openapi.json and docs/api/index.html created

# ---------------------------------------------------------------------------
# 11. Create admin user and seed data
# ---------------------------------------------------------------------------
python scripts/create_admin.py --email admin@ivgs.local --password <secret>
python scripts/seed_data.py
# Expected:
#   "✓ Admin user created"
#   "Prompts seeded: 10/10"
#   "Retention policies: 3/3"
#   "Fallback policies: 4/4"

# ---------------------------------------------------------------------------
# 12. Verify Nginx configuration
# ---------------------------------------------------------------------------
docker compose -f docker-compose.node01.yml exec nginx nginx -t
# Expected: "syntax is ok" and "test is successful"

# ---------------------------------------------------------------------------
# 13. Verify SSL certificates
# ---------------------------------------------------------------------------
openssl verify -CAfile configs/nginx/ssl/ivgs-ca.crt configs/nginx/ssl/ivgs.crt
# Expected: "configs/nginx/ssl/ivgs.crt: OK"

# ---------------------------------------------------------------------------
# 14. Full pre-deployment checklist (Table F-1)
# ---------------------------------------------------------------------------
python scripts/compliance_scanner.py             # Items 1-3
pytest tests/ --cov --cov-report=term-missing    # Items 4-5
docker compose -f docker-compose.node01.yml run --rm fastapi-backend alembic upgrade head  # Item 6
curl -sf http://localhost:8002/fleet             # Item 7 — GPU nodes
curl -sf http://localhost:9090/api/v1/targets    # Item 8 — Prometheus
curl -sf http://localhost:3000/api/dashboards    # Item 9 — Grafana
./scripts/backup.sh && ./scripts/verify_backup.sh $(date +%Y-%m-%d)  # Item 10

# ---------------------------------------------------------------------------
# 15. Verify CI workflows parse correctly
# ---------------------------------------------------------------------------
for workflow in ci compliance-check cd-deploy; do
    python3 -c "import yaml; yaml.safe_load(open('.github/workflows/${workflow}.yml'))"
    echo "✓ ${workflow}.yml — valid YAML"
done
# Expected: all 3 workflow files are valid YAML

# ---------------------------------------------------------------------------
# 16. Count total services across all Docker Compose files
# ---------------------------------------------------------------------------
total=0
for node in node01 node02 node03 node04 node05 node06; do
    count=$(grep -c "^  [a-z].*:" "docker-compose.${node}.yml" 2>/dev/null || echo 0)
    echo "  ${node}: ${count} services"
    total=$((total + count))
done
echo "Total services: $total"
# Expected: ~41 services across 6 nodes
