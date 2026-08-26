#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — per-writer log files                          WP-60 Task 12(c)
# =============================================================================
# THE DESIGN THIS REPLACES, AND WHY IT COULD NOT WORK.
#
# Every backup and restore script carried its own copy of the same helper:
#
#     mkdir -p "${LOG_DIR}"
#     touch "${LOG_FILE}" 2>/dev/null || true
#     chmod 666 "${LOG_FILE}" 2>/dev/null || true      # <- the load-bearing line
#     echo "${entry}" >> "${LOG_FILE}"
#
# One shared file per script, made world-writable so that cron (root), the
# backup-worker container (uid 999) and the `dev` user could all append to it.
# 0666 inside a 1777 sticky directory.
#
# Ubuntu ships `fs.protected_regular=2`. That setting FORBIDS opening a regular
# file for write in a world-writable sticky directory when the opener is
# neither the file's owner nor the directory's owner -- REGARDLESS of the file's
# mode. The 666 is not consulted. So the design's one mechanism is the one the
# kernel disables by default, and every `|| true` above hid it:
#
#     $ ls -ld /var/log/ivgs                 drwxrwxrwt  root root
#     $ sysctl fs.protected_regular          fs.protected_regular = 2
#     $ ls -l  /var/log/ivgs/basebackup.log  -rw-r--r-- node_exporter systemd-journal
#
# Measured on node-01, 2026-08-26: `basebackup.log` is owned by a THIRD user
# again, and root cannot append to it. The operator hit EACCES running WP-59's
# own §8.7 block. This is not specific to one file -- 666-in-1777 fails for
# every cross-user writer on any default-hardened Ubuntu.
#
# THE FIX IS TO STOP WRITING ACROSS USERS. Each writer gets its own file, named
# for the identity doing the writing, and therefore owns it. No shared inode, no
# reliance on permissions the kernel overrides, nothing to chmod, and it works
# unchanged inside a container, under cron, under sudo, and as `dev`.
#
# A shared group with setgid would also work and was considered. It was not
# chosen because it needs host-side provisioning (groupadd, usermod, and every
# container's uid joined to it) that a repository cannot carry and a
# data-directory or image rebuild silently loses -- the same class of defect as
# Task 12(b)'s hand-edited pg_hba line.
#
# Reading them is a glob: /var/log/ivgs/backup.*.log
# =============================================================================

# Resolve the log file for this writer.
#   $1 — base name, e.g. "backup", "restore", "wal_archive"
#   $2 — directory (optional; defaults to ${LOG_DIR:-/var/log/ivgs})
#
# Falls back to $TMPDIR when the log directory cannot be created or written --
# a script must not die because it could not open a log, and it must not
# silently discard the log either. The fallback path is announced on stderr.
ivgs_log_file() {
    local base="${1:?ivgs_log_file: base name required}"
    local dir="${2:-${LOG_DIR:-/var/log/ivgs}}"
    local who

    # The writer's identity, in the order most likely to be meaningful to a
    # human reading `ls`. Numeric uid is the fallback because a container often
    # has no passwd entry for its uid.
    who="$(id -un 2>/dev/null)" || who=""
    [ -n "${who}" ] || who="uid$(id -u 2>/dev/null || echo unknown)"
    # Keep it filesystem-safe: an identity is not necessarily a plain word.
    who="$(printf '%s' "${who}" | tr -c 'A-Za-z0-9_.-' '_')"

    mkdir -p "${dir}" 2>/dev/null || true

    local candidate="${dir}/${base}.${who}.log"
    if { : >> "${candidate}"; } 2>/dev/null; then
        printf '%s\n' "${candidate}"
        return 0
    fi

    local fallback="${TMPDIR:-/tmp}/ivgs-${base}.${who}.log"
    printf 'WARNING: cannot write %s; logging to %s instead\n' \
        "${candidate}" "${fallback}" >&2
    printf '%s\n' "${fallback}"
}
