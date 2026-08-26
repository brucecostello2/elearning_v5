#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — NFS destination guard (WP-59 Task 9, from WP-57 D-3)
# =============================================================================
# Source this, then call:
#
#     assert_nfs_destination "/mnt/backup/ivgs/db" "database backup"
#
# WHAT WENT WRONG, TWICE, AND WHY A PATH CHECK CANNOT CATCH IT
# ------------------------------------------------------------
# `/mnt/backup/ivgs` is an NFS mount from 192.168.1.7. A process that starts
# BEFORE that mount exists -- or a container whose bind was taken before it --
# sees the LOCAL ext4 directory shadowed underneath the mountpoint. Writes
# succeed. Files appear. Everything reports healthy. The bytes are on the root
# volume and no backup exists.
#
# Two processes were caught doing exactly this on 2026-08-25/26:
#
#   (a) ivgs-backup-worker. Two nights of database dumps failed with exit 6,
#       "NAS backup directory not available: /mnt/backup/ivgs/db". Fixed by
#       `--force-recreate` -- a routine recreate did NOT do it, because compose
#       saw no config change and left the container alone.
#   (b) postgres' archive_command. Its /mnt/wal-archive bind captured the local
#       ext4 inode and archived segments 5B..D0 -- 1.9 GB -- into the shadowed
#       tree until the container was recreated at 2026-08-26 00:43 UTC. The
#       operator merged the stranded segments back and the archive is an
#       unbroken 03..D1 run again.
#
# (a) FAILED LOUDLY ONLY BY LUCK. `backup.sh` checked `[ ! -d "$dir" ]` -- a
# PATH check -- and the shadowed local tree happened not to contain `db/`. It
# DID contain `assets/`, which is why 45 GB of July asset snapshots accumulated
# on the root volume for months while the surface said the asset backup was
# working. The same check would have passed silently for the database too if
# the local directory had existed. A path check asks "is there a directory
# here", which is not the question. The question is "is this directory ON THE
# NAS", and only the filesystem type can answer it.
#
# THE CHECK IS `stat -f`, NOT A STRING MATCH ON THE PATH.
# `stat -f -c %T <dir>` reports the filesystem type of the filesystem
# containing the directory: `nfs` for both NFSv3 and NFSv4 mounts, `ext2/ext3`
# for the local volume. It is resolved by the kernel at call time, so it cannot
# be fooled by a mountpoint that exists but is not mounted. /proc/mounts is
# consulted as a second opinion where it is available, because it also names
# the SERVER, which a bare "nfs" does not.
#
# Callers must treat a refusal as a RECORDED FAILURE, not a skip. Every caller
# below exits non-zero through its own failure path so its backup_records row
# is marked failed and its Prometheus gauge goes to 0.
# =============================================================================

# Return the filesystem type of the filesystem containing $1, or "" if the
# path does not exist. Never prints a diagnostic; callers own the wording.
nfs_guard_fstype() {
    local target="$1"
    [ -e "${target}" ] || return 1
    stat -f -c %T "${target}" 2>/dev/null
}

# The /proc/mounts line whose mountpoint is the LONGEST prefix of $1. This is
# how the kernel resolves a path to a mount, and it is why a naive
# `grep " ${dir} "` is wrong: /mnt/backup/ivgs/db is not itself a mountpoint,
# /mnt/backup/ivgs is.
nfs_guard_mount_line() {
    local target="$1"
    awk -v t="${target}/" '
        {
            # "/" is its own mountpoint and must not become "//", or the root
            # filesystem never matches and the diagnostic below reads
            # "<no matching entry>" for every local path -- which is exactly
            # the case an operator most needs named.
            mp = ($2 == "/") ? "/" : $2 "/"
            if (index(t, mp) == 1 && length(mp) > best_len) {
                best_len = length(mp); best = $0
            }
        }
        END { if (best != "") print best }
    ' /proc/mounts 2>/dev/null
}

# assert_nfs_destination <directory> <description>
#
# Returns 0 when <directory> exists and lives on an NFS filesystem.
# Returns 1 otherwise, having written the reason to STDERR only. Not stdout:
# three of the callers parse their own stdout for KEY=VALUE lines, and a
# guard that injected prose into that stream would break the parse it is
# supposed to protect.
assert_nfs_destination() {
    local target="$1"
    local what="${2:-backup destination}"
    local fstype mount_line

    if [ ! -d "${target}" ]; then
        printf 'NFS GUARD: %s directory does not exist: %s\n' "${what}" "${target}" >&2
        printf 'NFS GUARD: refusing to create it. Creating a directory under a\n' >&2
        printf '           missing NFS mount is exactly how the shadowed local\n' >&2
        printf '           tree gets written (WP-57 D-3).\n' >&2
        return 1
    fi

    fstype="$(nfs_guard_fstype "${target}")" || fstype=""
    mount_line="$(nfs_guard_mount_line "${target}")"

    case "${fstype}" in
        nfs|nfs4)
            return 0
            ;;
    esac

    printf 'NFS GUARD: %s is NOT on an NFS filesystem.\n' "${what}" >&2
    printf 'NFS GUARD:   path    : %s\n' "${target}" >&2
    printf 'NFS GUARD:   fstype  : %s (expected nfs / nfs4)\n' "${fstype:-unknown}" >&2
    printf 'NFS GUARD:   mount   : %s\n' "${mount_line:-<no matching /proc/mounts entry>}" >&2
    printf 'NFS GUARD: This is the shadowed-local-disk failure (WP-57 D-3): the\n' >&2
    printf '           NFS export is not visible to this process, so a write here\n' >&2
    printf '           would succeed onto the root volume and no backup would\n' >&2
    printf '           exist. Refusing, and recording the failure.\n' >&2
    printf 'NFS GUARD: Fix: confirm the host mount, then recreate this container\n' >&2
    printf '           with --force-recreate. A plain recreate does nothing --\n' >&2
    printf '           compose sees no config change and leaves it alone.\n' >&2
    return 1
}
