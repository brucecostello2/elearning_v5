#!/usr/bin/env bash
#
# apply-node-config.sh - apply a staged node-IP registry change (admin commissioning).
#
# The /admin "Node Configuration" page (ivgs-api) only STAGES changes: it writes a
# pending file under /ivgs and never touches .env or docker. This host-side script
# is the deliberate "apply" step. It:
#   1. reads the pending file,
#   2. backs up ivgs-infra/.env,
#   3. rewrites the NODE_0x_IP registry lines in .env (atomic; preserves the rest),
#   4. recreates the stack so the new IPs take effect (node-01 briefly goes offline),
#   5. clears the pending file.
#
# Usage:
#   scripts/apply-node-config.sh             # show changes, confirm, rewrite .env, restart
#   scripts/apply-node-config.sh --yes       # skip the confirmation prompt
#   scripts/apply-node-config.sh --no-restart # rewrite .env only; you restart later
#
set -euo pipefail

REPO_ROOT="${IVGS_REPO_ROOT:-/opt/ivgs}"
INFRA_DIR="$REPO_ROOT/ivgs-infra"
ENV_FILE="$INFRA_DIR/.env"
PENDING="${IVGS_NODE_CONFIG_PENDING_PATH:-/opt/ivgs/rollback-storage/node-config.pending.json}"
DC_FILES=(-f docker-compose.node01.yml -f docker-compose.override.node01.yml -f docker-compose.monitoring.yml)

ASSUME_YES=0
DO_RESTART=1
for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --no-restart) DO_RESTART=0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

[ -f "$PENDING" ] || { echo "No pending node-config change at $PENDING - nothing to apply."; exit 0; }
[ -f "$ENV_FILE" ] || { echo "ERROR: env file not found at $ENV_FILE" >&2; exit 1; }

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ENV_FILE.bak.apply-node-config.$TS"
cp -p "$ENV_FILE" "$BACKUP"

# Rewrite the NODE_0x_IP lines in .env from the pending file (atomic). Prints the changes.
CHANGED="$(python3 - "$PENDING" "$ENV_FILE" <<'PY'
import ipaddress, json, os, re, sys, tempfile
pending_path, env_path = sys.argv[1], sys.argv[2]
with open(pending_path, encoding="utf-8") as fh:
    nodes = (json.load(fh) or {}).get("nodes", {})
valid = {}
for node_id, ip in nodes.items():
    if not re.fullmatch(r"node-0[1-6]", str(node_id)):
        continue
    ip = str(ip).strip()
    ipaddress.IPv4Address(ip)  # raises ValueError if invalid
    valid["NODE_" + str(node_id).split("-")[1] + "_IP"] = ip
if not valid:
    sys.stderr.write("NO_VALID_ENTRIES\n"); sys.exit(3)
with open(env_path, encoding="utf-8") as fh:
    lines = fh.readlines()
seen, changes = set(), []
for i, line in enumerate(lines):
    m = re.match(r"^(NODE_0[1-6]_IP)=(.*)$", line.rstrip("\n"))
    if m and m.group(1) in valid:
        key, old, new = m.group(1), m.group(2), valid[m.group(1)]
        if old != new:
            changes.append(f"{key}: {old} -> {new}")
        lines[i] = f"{key}={new}\n"
        seen.add(key)
for key, ip in valid.items():
    if key not in seen:
        lines.append(f"{key}={ip}\n")
        changes.append(f"{key}: (added) -> {ip}")
directory = os.path.dirname(env_path) or "."
fd, tmp = tempfile.mkstemp(prefix=".env.", dir=directory)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.writelines(lines)
os.replace(tmp, env_path)
sys.stdout.write("\n".join(changes) if changes else "NO_CHANGES")
PY
)"

echo "Backup of .env written to: $BACKUP"
if [ "$CHANGED" = "NO_CHANGES" ]; then
  echo "No NODE_0x_IP changes (pending matched current .env)."
else
  echo "Applied to $ENV_FILE:"
  printf '%s\n' "$CHANGED" | sed 's/^/  /'
fi

if [ "$DO_RESTART" -eq 1 ]; then
  if [ "$ASSUME_YES" -ne 1 ]; then
    echo
    echo "This will recreate the stack (docker compose up -d). node-01 will briefly go offline."
    read -r -p "Proceed with restart now? [y/N] " ans
    case "$ans" in
      y|Y|yes|YES) ;;
      *) echo "Skipped restart. .env is updated; run the stack 'up -d' when ready (pending file kept)."; exit 0 ;;
    esac
  fi
  ( cd "$INFRA_DIR" && docker compose "${DC_FILES[@]}" up -d )
  rm -f "$PENDING"
  echo "Stack recreated and pending change cleared."
else
  echo ".env updated (no restart requested). Run the stack 'up -d' to apply; pending file kept until you do."
fi
