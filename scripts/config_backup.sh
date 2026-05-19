#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — Configuration Backup Script
# =============================================================================
# Spec reference: §14.1 Table 14-1 — Backup Schedule (Row 4: Config backup)
#
# Type:      Config backup
# Scope:     YAML + .env files
# Method:    rsync + GPG encrypt
# Schedule:  Daily at 04:00
# Target:    /mnt/backup/ivgs/config/
# Retention: 90 days
#
# Backs up:
#   - configs/prometheus/*.yml
#   - configs/grafana/**/*
#   - configs/nginx/*
#   - configs/cron/*
#   - docker-compose*.yml
#   - .env* files
#   - scripts/*.sh
#   - alembic.ini + alembic/ directory
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly TIMESTAMP="$(date +%Y-%m-%d)"
readonly LOG_FILE="/var/log/ivgs/config_backup.log"
readonly LOG_DIR="/var/log/ivgs"

IVGS_ROOT="${IVGS_ROOT:-/opt/ivgs}"
BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/config}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-90}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://localhost:9091}"

readonly STAGING_DIR="/tmp/ivgs-config-backup-${TIMESTAMP}"
readonly ARCHIVE_FILE="/tmp/ivgs-config-${TIMESTAMP}.tar.gz"
readonly ENCRYPTED_FILE="${ARCHIVE_FILE}.gpg"
readonly NAS_TARGET="${BACKUP_NAS_DIR}/${TIMESTAMP}/"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_entry() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    mkdir -p "${LOG_DIR}"
    echo "{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"config-backup\",\"script\":\"${SCRIPT_NAME}\",\"message\":\"${message}\"}" >> "${LOG_FILE}"
    echo "[${level}] ${message}"
}

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
cleanup() {
    rm -rf "${STAGING_DIR}" "${ARCHIVE_FILE}" "${ENCRYPTED_FILE}" 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    log_entry "INFO" "Running pre-flight checks"

    if [ -z "${BACKUP_GPG_RECIPIENT:-}" ]; then
        log_entry "ERROR" "BACKUP_GPG_RECIPIENT is not set"
        exit 1
    fi

    if [ ! -d "${IVGS_ROOT}" ]; then
        log_entry "ERROR" "IVGS root directory not found: ${IVGS_ROOT}"
        exit 1
    fi

    if [ ! -d "${BACKUP_NAS_DIR}" ]; then
        log_entry "ERROR" "NAS config backup directory not available: ${BACKUP_NAS_DIR}"
        exit 1
    fi

    for cmd in rsync gpg tar sha256sum; do
        if ! command -v "${cmd}" &>/dev/null; then
            log_entry "ERROR" "Required command not found: ${cmd}"
            exit 1
        fi
    done

    log_entry "INFO" "Pre-flight checks passed"
}

# ---------------------------------------------------------------------------
# Collect config files
# ---------------------------------------------------------------------------
collect_configs() {
    log_entry "INFO" "Collecting configuration files from ${IVGS_ROOT}"

    mkdir -p "${STAGING_DIR}"

    # Config directories
    local config_paths=(
        "configs/prometheus"
        "configs/grafana"
        "configs/nginx"
        "configs/cron"
    )

    for path in "${config_paths[@]}"; do
        if [ -d "${IVGS_ROOT}/${path}" ]; then
            mkdir -p "${STAGING_DIR}/${path}"
            rsync --archive --quiet "${IVGS_ROOT}/${path}/" "${STAGING_DIR}/${path}/"
            log_entry "INFO" "Collected: ${path}"
        fi
    done

    # Docker Compose files
    for f in "${IVGS_ROOT}"/docker-compose*.yml; do
        [ -f "$f" ] && cp "$f" "${STAGING_DIR}/"
    done

    # Environment files (redact secrets for safety)
    for f in "${IVGS_ROOT}"/.env*; do
        if [ -f "$f" ]; then
            # Copy but redact password/secret values
            sed -E 's/(PASSWORD|SECRET|KEY|TOKEN)=.+/\1=<REDACTED>/g' "$f" \
                > "${STAGING_DIR}/$(basename "$f")"
        fi
    done

    # Also store a non-redacted encrypted copy
    for f in "${IVGS_ROOT}"/.env*; do
        if [ -f "$f" ]; then
            mkdir -p "${STAGING_DIR}/env-encrypted"
            gpg --batch --yes --trust-model always \
                --recipient "${BACKUP_GPG_RECIPIENT}" \
                --output "${STAGING_DIR}/env-encrypted/$(basename "$f").gpg" \
                --encrypt "$f" 2>/dev/null || true
        fi
    done

    # Scripts
    if [ -d "${IVGS_ROOT}/scripts" ]; then
        mkdir -p "${STAGING_DIR}/scripts"
        rsync --archive --quiet "${IVGS_ROOT}/scripts/" "${STAGING_DIR}/scripts/"
    fi

    # Alembic configuration
    if [ -f "${IVGS_ROOT}/alembic.ini" ]; then
        cp "${IVGS_ROOT}/alembic.ini" "${STAGING_DIR}/"
    fi
    if [ -d "${IVGS_ROOT}/alembic" ]; then
        mkdir -p "${STAGING_DIR}/alembic"
        rsync --archive --quiet "${IVGS_ROOT}/alembic/" "${STAGING_DIR}/alembic/"
    fi

    local file_count
    file_count="$(find "${STAGING_DIR}" -type f | wc -l)"
    log_entry "INFO" "Collected ${file_count} config files"
}

# ---------------------------------------------------------------------------
# Create encrypted archive
# ---------------------------------------------------------------------------
create_encrypted_archive() {
    log_entry "INFO" "Creating encrypted archive"

    # Create tarball
    tar -czf "${ARCHIVE_FILE}" -C "$(dirname "${STAGING_DIR}")" "$(basename "${STAGING_DIR}")"

    # Encrypt
    gpg --batch --yes --trust-model always \
        --recipient "${BACKUP_GPG_RECIPIENT}" \
        --output "${ENCRYPTED_FILE}" \
        --encrypt "${ARCHIVE_FILE}"

    rm -f "${ARCHIVE_FILE}"

    local size
    size="$(stat -c%s "${ENCRYPTED_FILE}" 2>/dev/null || echo 0)"
    log_entry "INFO" "Encrypted archive created: ${size} bytes"
}

# ---------------------------------------------------------------------------
# Sync to NAS
# ---------------------------------------------------------------------------
sync_to_nas() {
    log_entry "INFO" "Syncing config backup to NAS"

    mkdir -p "${NAS_TARGET}"

    # Copy encrypted archive
    cp "${ENCRYPTED_FILE}" "${NAS_TARGET}/"

    # Compute and store checksum
    sha256sum "${ENCRYPTED_FILE}" > "${NAS_TARGET}/config_backup.sha256"

    log_entry "INFO" "Config backup synced to NAS: ${NAS_TARGET}"
}

# ---------------------------------------------------------------------------
# Retention cleanup (90 days)
# ---------------------------------------------------------------------------
cleanup_old() {
    log_entry "INFO" "Cleaning config backups older than ${BACKUP_RETENTION_DAYS} days"

    local deleted=0
    if [ -d "${BACKUP_NAS_DIR}" ]; then
        while IFS= read -r -d '' dir; do
            rm -rf "${dir}"
            ((deleted++)) || true
        done < <(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d \
            -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    fi

    log_entry "INFO" "Cleaned ${deleted} old config backups"
}

# ---------------------------------------------------------------------------
# Push metrics
# ---------------------------------------------------------------------------
push_status() {
    local status="$1"
    cat <<EOF | curl --silent --max-time 10 --data-binary @- \
        "${PROMETHEUS_PUSHGATEWAY}/metrics/job/ivgs_config_backup/instance/node-01" 2>/dev/null || true
# TYPE ivgs_backup_last_status gauge
ivgs_backup_last_status{backup_type="config",target_path="${BACKUP_NAS_DIR}",node="node-01"} ${status}
# TYPE ivgs_backup_last_timestamp gauge
ivgs_backup_last_timestamp{backup_type="config"} $(date +%s)
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local start_time
    start_time="$(date +%s)"

    log_entry "INFO" "=== IVGS v5 Config Backup Starting ==="

    preflight
    collect_configs
    create_encrypted_archive
    sync_to_nas
    cleanup_old

    push_status 1

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))

    log_entry "INFO" "=== Config Backup Completed (${duration}s) ==="
}

main "$@"
