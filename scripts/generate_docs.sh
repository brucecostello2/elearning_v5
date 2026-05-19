#!/bin/bash
# generate_docs.sh — Export OpenAPI 3.1 spec from FastAPI (§19.4)
set -euo pipefail

OUTPUT_DIR="${1:-/ivgs/docs/api}"
mkdir -p "$OUTPUT_DIR"

echo "Generating OpenAPI 3.1 specification..."

# Export OpenAPI JSON
docker compose -f docker-compose.node01.yml exec -T ivgs-api \
    python -c "
import json
from app.main import app
spec = app.openapi()
print(json.dumps(spec, indent=2))
" > "$OUTPUT_DIR/openapi.json"

# Convert to YAML
docker compose -f docker-compose.node01.yml exec -T ivgs-api \
    python -c "
import json, yaml
with open('/tmp/openapi.json') as f:
    spec = json.load(f)
print(yaml.dump(spec, default_flow_style=False))
" < "$OUTPUT_DIR/openapi.json" > "$OUTPUT_DIR/openapi.yaml"

echo "OpenAPI spec exported to:"
echo "  JSON: $OUTPUT_DIR/openapi.json"
echo "  YAML: $OUTPUT_DIR/openapi.yaml"

echo "Done."
