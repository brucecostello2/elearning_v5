#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — RESTORE REHEARSAL   (WP-59 Task 10, from WP-57 D-5)
# =============================================================================
# Proves the recovery promise by performing it, into a scratch cluster, and
# then throwing the scratch cluster away.
#
# WHY A REHEARSAL AND NOT A DOCUMENT
# ----------------------------------
# The checkpoint-only recovery promise (WP-57 §6) was INFERRED from reading
# backup.sh, never demonstrated. Nobody on this system has restored a backup.
# An untested restore is a belief, and the failure mode of a belief is that it
# is discovered to be wrong at the worst possible moment.
#
# THE ISOLATION MECHANISM, STATED EXPLICITLY
# ------------------------------------------
# The live database is not touched in any step, and the mechanism is not
# discipline -- it is a SEPARATE POSTGRESQL CLUSTER:
#
#   * a throwaway `postgres:17.2` container with its own PGDATA on its own
#     temporary directory, its own postmaster, its own shared buffers;
#   * no published port, reached only by `docker exec`, so nothing outside can
#     even address it;
#   * it is never given the live cluster's socket or data directory.
#
# The only thing this script does to the LIVE cluster is four `SELECT count(*)`
# statements to compare against. There is no code path here that can write to
# it.
#
# AND THAT ISOLATION IS LOAD-BEARING, NOT BELT-AND-BRACES.
# `backup.sh` runs `pg_dump ... --clean --if-exists --create`, so line 22 of
# every dump this system has ever taken is:
#
#     DROP DATABASE IF EXISTS ivgs;
#
# followed by CREATE DATABASE ivgs and `\connect ivgs`. Feeding that file to
# psql against the live cluster DESTROYS THE LIVE DATABASE, whatever `-d` names
# on the command line -- the `\connect` overrides it. A rehearsal that ran
# "into a new database" on the live cluster would have been the single most
# destructive thing in this package. Hence: a different cluster, and a filter,
# and a gate on the filter.
#
# Usage:
#   ./restore_rehearsal.sh                 # rehearse the most recent dump
#   ./restore_rehearsal.sh 2026-08-23      # rehearse a specific date
#   ./restore_rehearsal.sh --keep          # leave the scratch cluster running
#
# Exit codes:
#   0 — rehearsal completed, row counts recorded
#   1 — pre-flight failure
#   2 — decrypt/decompress failed
#   3 — scratch cluster did not become ready
#   4 — restore into the scratch database failed
#   5 — the filtered dump still contained a database-level statement (REFUSED)
# =============================================================================

set -euo pipefail

REHEARSAL_DB="${REHEARSAL_DB:-ivgs_restore_rehearsal}"
SCRATCH_CONTAINER="${SCRATCH_CONTAINER:-ivgs-restore-rehearsal}"
SCRATCH_IMAGE="${SCRATCH_IMAGE:-postgres:17.2}"
BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/db}"
BACKUP_WORKER="${BACKUP_WORKER:-ivgs-backup-worker}"
LIVE_CONTAINER="${LIVE_CONTAINER:-ivgs-postgres}"
LIVE_DB="${POSTGRES_DB:-ivgs}"
LIVE_USER="${POSTGRES_USER:-ivgs}"
KEEP="false"
RESTORE_DATE=""

for arg in "$@"; do
    case "$arg" in
        --keep) KEEP="true" ;;
        --help|-h) sed -n '2,55p' "$0"; exit 0 ;;
        [0-9]*) RESTORE_DATE="$arg" ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

WORKDIR="$(mktemp -d /tmp/ivgs-rehearsal-XXXXXX)"
SCRATCH_PGDATA="${WORKDIR}/pgdata"
SCRATCH_PASSWORD="rehearsal-$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"

say() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*"; }

# Milliseconds, not seconds. This database's dump is ~5.8 MB of SQL and every
# phase finishes well inside a second; `date +%s` would record the whole
# rehearsal as "0s", which is a number that proves nothing and would age badly
# the first time the database is ten times bigger.
now_ms() { date +%s%3N; }
ms() { printf '%d.%03ds' "$(( $1 / 1000 ))" "$(( $1 % 1000 ))"; }

cleanup() {
    local rc=$?
    if [ "${KEEP}" = "true" ]; then
        say "--keep given: leaving ${SCRATCH_CONTAINER} and ${WORKDIR} in place."
        say "Remove with: docker rm -f ${SCRATCH_CONTAINER} && sudo rm -rf ${WORKDIR}"
        return
    fi
    say "Tearing down the scratch cluster."
    # DROP the scratch database first, so the teardown is observable as the
    # thing Task 10 asked for and not merely a container going away.
    docker exec "${SCRATCH_CONTAINER}" psql -U postgres -d postgres \
        -c "DROP DATABASE IF EXISTS ${REHEARSAL_DB};" >/dev/null 2>&1 || true
    docker rm -f "${SCRATCH_CONTAINER}" >/dev/null 2>&1 || true
    sudo rm -rf "${WORKDIR}" 2>/dev/null || rm -rf "${WORKDIR}" 2>/dev/null || true
    exit "${rc}"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
say "IVGS restore rehearsal — scratch cluster only, live database untouched."

# --- Pick the dump ---------------------------------------------------------
if [ -z "${RESTORE_DATE}" ]; then
    RESTORE_DATE="$(sudo ls -1 "${BACKUP_NAS_DIR}" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort | tail -1)"
fi
if [ -z "${RESTORE_DATE}" ]; then
    echo "No dated backup directories found in ${BACKUP_NAS_DIR}" >&2
    exit 1
fi
DUMP_GPG="${BACKUP_NAS_DIR}/${RESTORE_DATE}/ivgs_backup.sql.gz.gpg"
say "Rehearsing dump: ${DUMP_GPG}"

# --- Decrypt, in the container that holds the keyring ----------------------
# The GPG private key lives in /etc/ivgs/gpg-backup-keyring, owned by uid 999
# and mounted only into ivgs-backup-worker. Decrypting THERE and streaming the
# plaintext here means the key never leaves the container it was placed in, and
# the plaintext never lands on the NAS.
say "Decrypting and decompressing (inside ${BACKUP_WORKER})..."
t0=$(now_ms)
if ! docker exec "${BACKUP_WORKER}" sh -c \
        "gpg --batch --quiet --decrypt '${DUMP_GPG}' 2>/dev/null | gunzip" \
        > "${WORKDIR}/dump.sql"; then
    echo "Decrypt/decompress failed for ${DUMP_GPG}" >&2
    exit 2
fi
t_decrypt=$(( $(now_ms) - t0 ))
DUMP_BYTES="$(stat -c%s "${WORKDIR}/dump.sql")"
say "Decrypted in $(ms ${t_decrypt}) — ${DUMP_BYTES} bytes of SQL."

# --- Filter out the database-level statements ------------------------------
# Everything before and including `\connect <db>` is cluster-level: DROP
# DATABASE, CREATE DATABASE, and the reconnect. Removing it turns the file into
# "restore these objects into whatever database I am connected to", which is
# what a restore into a differently-named database needs.
say "Filtering cluster-level statements (DROP/CREATE DATABASE, \\connect)..."
awk 'seen { print } /^\\connect / { seen = 1 }' "${WORKDIR}/dump.sql" > "${WORKDIR}/objects.sql"

if [ ! -s "${WORKDIR}/objects.sql" ]; then
    echo "Filter produced an empty file — the dump has no \\connect line." >&2
    echo "Refusing rather than guessing at its structure." >&2
    exit 5
fi

# THE GATE. Not a comment saying the filter works -- a check that it did.
if grep -nEi '^[[:space:]]*(DROP|CREATE)[[:space:]]+DATABASE|^\\connect' \
        "${WORKDIR}/objects.sql" >/dev/null; then
    echo "REFUSING: the filtered dump still contains a database-level statement." >&2
    grep -nEi '^[[:space:]]*(DROP|CREATE)[[:space:]]+DATABASE|^\\connect' \
        "${WORKDIR}/objects.sql" | head >&2
    exit 5
fi
say "Filter verified: no DROP/CREATE DATABASE and no \\connect remain."

# --- Start the scratch cluster ---------------------------------------------
# --memory=512m mirrors verify_backup.sh: node-01 is a 16 GB VM that its
# Proxmox host has OOM-killed before (dev/CLAUDE.md §7). A rehearsal must not
# be able to take the node down.
# No -p: the scratch cluster is unreachable from outside the docker host.
say "Starting scratch cluster (${SCRATCH_IMAGE}, 512 MB, no published port)..."
mkdir -p "${SCRATCH_PGDATA}"
docker rm -f "${SCRATCH_CONTAINER}" >/dev/null 2>&1 || true
docker run -d --name "${SCRATCH_CONTAINER}" \
    -e POSTGRES_PASSWORD="${SCRATCH_PASSWORD}" \
    -e PGDATA=/var/lib/postgresql/data/pgdata \
    -v "${SCRATCH_PGDATA}:/var/lib/postgresql/data" \
    --memory=512m --memory-swap=512m \
    "${SCRATCH_IMAGE}" >/dev/null

t0=$(now_ms)
ready=false
for _ in $(seq 1 60); do
    if docker exec "${SCRATCH_CONTAINER}" pg_isready -U postgres >/dev/null 2>&1; then
        ready=true; break
    fi
    sleep 1
done
if [ "${ready}" != "true" ]; then
    echo "Scratch cluster did not become ready in 60s" >&2
    docker logs --tail 30 "${SCRATCH_CONTAINER}" >&2 || true
    exit 3
fi
t_start=$(( $(now_ms) - t0 ))
say "Scratch cluster ready in $(ms ${t_start})."

# --- Restore ---------------------------------------------------------------
say "Creating ${REHEARSAL_DB} and restoring..."
docker exec "${SCRATCH_CONTAINER}" psql -U postgres -d postgres -q \
    -c "CREATE DATABASE ${REHEARSAL_DB};"

t0=$(now_ms)
if ! docker exec -i "${SCRATCH_CONTAINER}" \
        psql -U postgres -d "${REHEARSAL_DB}" -q -v ON_ERROR_STOP=1 \
        < "${WORKDIR}/objects.sql" > "${WORKDIR}/restore.out" 2>&1; then
    echo "Restore into ${REHEARSAL_DB} FAILED. Last 30 lines:" >&2
    tail -30 "${WORKDIR}/restore.out" >&2
    exit 4
fi
t_restore=$(( $(now_ms) - t0 ))
say "Restore completed in $(ms ${t_restore})."

# Prove we are where we think we are. A restore that silently landed somewhere
# else is the exact failure this script's isolation exists to prevent, so it is
# asserted rather than assumed.
WHERE="$(docker exec "${SCRATCH_CONTAINER}" psql -U postgres -d "${REHEARSAL_DB}" -tAc 'SELECT current_database();')"
if [ "${WHERE}" != "${REHEARSAL_DB}" ]; then
    echo "Restored into '${WHERE}', expected '${REHEARSAL_DB}'." >&2
    exit 4
fi
say "Confirmed: objects are in ${WHERE}, in the scratch cluster."

# --- Compare -----------------------------------------------------------------
say ""
say "Row counts — scratch restore vs LIVE (live is read with SELECT only):"
printf '%-24s %12s %12s %10s\n' "table" "restored" "live" "delta"
printf '%-24s %12s %12s %10s\n' "------------------------" "------------" "------------" "----------"

TABLES="${REHEARSAL_TABLES:-projects storyboard_scenes assets render_jobs}"
MISMATCH=0
for t in ${TABLES}; do
    r="$(docker exec "${SCRATCH_CONTAINER}" psql -U postgres -d "${REHEARSAL_DB}" \
            -tAc "SELECT count(*) FROM ${t};" 2>/dev/null || echo "ERR")"
    l="$(docker exec "${LIVE_CONTAINER}" psql -U "${LIVE_USER}" -d "${LIVE_DB}" \
            -tAc "SELECT count(*) FROM ${t};" 2>/dev/null || echo "ERR")"
    if [ "${r}" = "ERR" ] || [ "${l}" = "ERR" ]; then
        printf '%-24s %12s %12s %10s\n' "${t}" "${r}" "${l}" "?"
        MISMATCH=$((MISMATCH + 1))
        continue
    fi
    printf '%-24s %12s %12s %+10d\n' "${t}" "${r}" "${l}" "$(( l - r ))"
done

say ""
# A DELTA IS NOT A FAILURE, AND SAYING SO MATTERS. The dump is from the
# backup's instant; live has moved on since. What a delta must never be is
# NEGATIVE in a way that means the restore lost rows the dump contained -- and
# what it must never be is unexplained. The report records both numbers and the
# dump's date so the difference is attributable.
say "A positive delta is live growth since ${RESTORE_DATE} and is expected."
say "A negative delta means the restore produced rows the live database"
say "does not have, which would need explaining before this rehearsal counts."

say ""
say "Timings:  decrypt $(ms ${t_decrypt}) | cluster start $(ms ${t_start}) | restore $(ms ${t_restore})"
say "Total recovery time for the data phase: $(ms $(( t_decrypt + t_start + t_restore )))"
say ""
say "Dump date: ${RESTORE_DATE}   SQL size: ${DUMP_BYTES} bytes"
say "Live database was read with SELECT only; no statement in this script can write to it."
