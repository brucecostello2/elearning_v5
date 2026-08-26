#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — retire dead-container model-accounting keys   WP-60 Task 3(b)
# =============================================================================
# WP-45's block B2 pruned `gpu:node:*` of registrations belonging to containers
# the fleet no longer runs. It did NOT reach the model-accounting families, and
# they were keyed on the same dead identifiers. Measured in db1, 2026-08-26:
#
#   gpu:model_lru:3772bab239e5:gpu0:0     gpu:models:3772bab239e5:gpu0
#   gpu:model_lru:7f479b3018af:gpu0:0     gpu:models:7f479b3018af:gpu0
#   gpu:model_lru:c326eab3def1:gpu0:0     gpu:models:c326eab3def1:gpu0   ...
#
# alongside the real `node-03:gpu0` / `node-04:gpu0` entries. A container hex id
# is not a node: before WP-45 gave nodes stable names, every container restart
# minted a new identity and left its model residency behind. The stale entries
# make `gpu:model_fleet:*` claim a model is resident on hosts that do not exist,
# which is what `get_nodes_with_model` -- the warm-start preference -- reads.
#
# SAME DISCIPLINE AS WP-45 B2: back up every key's contents to a timestamped
# file first, print exactly what would go, and delete only when told to.
#
# Usage:
#   scripts/prune-scheduler-model-keys.sh              # DRY RUN (default)
#   scripts/prune-scheduler-model-keys.sh --apply      # back up, then delete
#
# A node id is KEPT when it appears in `gpu:nodes:all` -- the registry's own
# list of who is registered. Nothing else is consulted, so this cannot delete a
# live node's keys because of a naming assumption.
# =============================================================================
set -uo pipefail

REDIS_CONTAINER="${REDIS_CONTAINER:-ivgs-redis}"
REDIS_DB="${REDIS_DB:-1}"
BACKUP_DIR="${BACKUP_DIR:-/opt/ivgs/rollback-storage/scheduler-model-keys}"
APPLY="false"
[ "${1:-}" = "--apply" ] && APPLY="true"

rcli() { docker exec "${REDIS_CONTAINER}" redis-cli -n "${REDIS_DB}" "$@"; }

if ! docker exec "${REDIS_CONTAINER}" true 2>/dev/null; then
    echo "ABORT: cannot reach container ${REDIS_CONTAINER}" >&2
    exit 1
fi

# --- Who is actually registered. The only authority used here. --------------
LIVE_NODES="$(rcli SMEMBERS gpu:nodes:all | tr -d '\r' | sed '/^$/d')"
if [ -z "${LIVE_NODES}" ]; then
    echo "ABORT: gpu:nodes:all is empty. Refusing to prune - with no live set" >&2
    echo "       every key below would look dead, including the real ones." >&2
    exit 2
fi
echo "Registered nodes (kept):"
echo "${LIVE_NODES}" | sed 's/^/  /'
echo

# --- Candidates -------------------------------------------------------------
# gpu:models:{node_id}          -> field 3 is the node id
# gpu:model_loads:{node}:{gpu}:{n} and gpu:model_lru:{...} -> same, positionally
STALE=""
for pattern in 'gpu:models:*' 'gpu:model_loads:*' 'gpu:model_lru:*'; do
    while IFS= read -r key; do
        [ -z "${key}" ] && continue
        # strip the family prefix, then take "<host>:<gpuN>" as the node id
        rest="${key#gpu:models:}"; rest="${rest#gpu:model_loads:}"; rest="${rest#gpu:model_lru:}"
        host="${rest%%:*}"
        after="${rest#*:}"
        gpu="${after%%:*}"
        node_id="${host}:${gpu}"
        if ! echo "${LIVE_NODES}" | grep -qxF "${node_id}"; then
            STALE="${STALE}${key}"$'\n'
        fi
    done < <(rcli --scan --pattern "${pattern}" | tr -d '\r')
done
STALE="$(echo "${STALE}" | sed '/^$/d' | sort -u)"

if [ -z "${STALE}" ]; then
    echo "Nothing to prune: every model-accounting key belongs to a registered node."
    exit 0
fi

COUNT="$(echo "${STALE}" | wc -l)"
echo "Keys belonging to node ids that are NOT registered (${COUNT}):"
echo "${STALE}" | sed 's/^/  /'
echo

if [ "${APPLY}" != "true" ]; then
    echo "DRY RUN - nothing was written or deleted. Re-run with --apply to back up and delete."
    exit 0
fi

# --- Back up BEFORE deleting, WP-45 B2 discipline ---------------------------
mkdir -p "${BACKUP_DIR}"
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
OUT="${BACKUP_DIR}/model-keys-${STAMP}.txt"
{
    echo "# IVGS scheduler model-accounting keys, captured before prune"
    echo "# ${STAMP}  db=${REDIS_DB}  container=${REDIS_CONTAINER}"
    echo "# registered nodes at capture:"
    echo "${LIVE_NODES}" | sed 's/^/#   /'
    while IFS= read -r key; do
        [ -z "${key}" ] && continue
        t="$(rcli TYPE "${key}" | tr -d '\r')"
        echo "--- ${key} (${t})"
        case "${t}" in
            set)   rcli SMEMBERS "${key}" ;;
            hash)  rcli HGETALL  "${key}" ;;
            zset)  rcli ZRANGE   "${key}" 0 -1 WITHSCORES ;;
            *)     rcli GET      "${key}" ;;
        esac
    done <<< "${STALE}"
} > "${OUT}" 2>&1

if [ ! -s "${OUT}" ]; then
    echo "ABORT: backup file ${OUT} is empty. Nothing deleted." >&2
    exit 3
fi
echo "Backed up to ${OUT} ($(wc -c < "${OUT}") bytes)"

# --- Delete, and remove the dead node from any fleet-residency set ----------
DELETED=0
while IFS= read -r key; do
    [ -z "${key}" ] && continue
    rest="${key#gpu:models:}"; rest="${rest#gpu:model_loads:}"; rest="${rest#gpu:model_lru:}"
    host="${rest%%:*}"; after="${rest#*:}"; gpu="${after%%:*}"
    node_id="${host}:${gpu}"
    # gpu:model_fleet:{model} is a set OF NODE IDS: the dead node must come out
    # of each one, or the warm-start preference keeps pointing at a host that
    # does not exist.
    while IFS= read -r fleet_key; do
        [ -z "${fleet_key}" ] && continue
        rcli SREM "${fleet_key}" "${node_id}" >/dev/null
    done < <(rcli --scan --pattern 'gpu:model_fleet:*' | tr -d '\r')
    rcli DEL "${key}" >/dev/null && DELETED=$((DELETED + 1))
done <<< "${STALE}"

echo "Deleted ${DELETED} key(s)."
echo
echo "Remaining model-accounting keys:"
rcli --scan --pattern 'gpu:model*' | tr -d '\r' | sort | sed 's/^/  /'
echo
echo "Empty fleet sets (a model no live node has resident) are expected and harmless."
