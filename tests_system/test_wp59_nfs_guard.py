"""
WP-59 Task 9 — the NFS destination guard (from WP-57 D-3).

WHY THESE DRIVE THE REAL SCRIPT. Same reasoning as WP-58's retention tests: a
test asserting "the script contains assert_nfs_destination" would pass against
a guard that always returned 0. What has to be shown is that the guard REFUSES
the local filesystem and ACCEPTS an NFS one -- and the first of those is the
half that was missing for months.

WHAT WENT WRONG. `/mnt/backup/ivgs` is an NFS mount. A process that starts
before that mount exists sees the LOCAL ext4 directory shadowed underneath the
mountpoint. Writes succeed. Files appear. Nothing errors. The bytes are on the
root volume and no backup exists. `backup.sh` checked `[ ! -d "$dir" ]`, a PATH
check, which cannot tell the two apart: a shadowed local directory IS a
directory. It failed loudly for the database only because the local tree
happened not to contain `db/`; it contained `assets/`, and 45 GB of July asset
snapshots accumulated on the root volume while the surface said the asset
backup was working.

NOTHING HERE TOUCHES /mnt/backup for a WRITE. The NFS-positive case reads the
real mount because that is the only place a genuine nfs4 filesystem exists on
this node, and it only calls `stat -f` on it.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "lib" / "nfs_guard.sh"
SCRIPTS = REPO / "scripts"

NAS_DIR = "/mnt/backup/ivgs"


def _guard(target: str) -> subprocess.CompletedProcess:
    """Source the real guard and run it against `target`."""
    return subprocess.run(
        ["bash", "-c", f'. "{GUARD}"; assert_nfs_destination "{target}" "test"'],
        capture_output=True, text=True,
    )


def _have_nas() -> bool:
    if not os.path.isdir(NAS_DIR):
        return False
    out = subprocess.run(
        ["stat", "-f", "-c", "%T", NAS_DIR], capture_output=True, text=True)
    return out.stdout.strip() in ("nfs", "nfs4")


class TestGuardBehaviour:
    def test_refuses_a_local_directory(self, tmp_path):
        """The half that was missing. A tmp_path is ext4; the guard must refuse."""
        result = _guard(str(tmp_path))
        assert result.returncode == 1, (
            "the guard accepted a LOCAL directory. This is the shadowed-mount "
            "failure: a write here succeeds onto the root volume and no backup "
            "exists."
        )
        assert "NOT on an NFS filesystem" in result.stderr

    def test_names_the_filesystem_type_it_found(self, tmp_path):
        """A refusal that does not say what it found is not diagnosable at 3am."""
        result = _guard(str(tmp_path))
        assert "fstype" in result.stderr
        # ext2/ext3 is what stat -f reports for ext4.
        assert "ext" in result.stderr or "overlay" in result.stderr or "tmpfs" in result.stderr

    def test_names_the_mount_it_resolved_to(self, tmp_path):
        """Including for a path on `/`, which an earlier draft could not match."""
        result = _guard(str(tmp_path))
        assert "mount   :" in result.stderr
        assert "<no matching" not in result.stderr, (
            "the guard could not resolve the path to a /proc/mounts entry. It "
            "must, or its diagnostic is useless for exactly the local paths it "
            "exists to reject."
        )

    def test_refuses_a_directory_that_does_not_exist(self, tmp_path):
        """And REFUSES TO CREATE IT.

        Creating a directory under a missing NFS mount is precisely how the
        shadowed tree gets written -- `wal_archive.sh`'s own `mkdir -p` built
        the one that took 1.9 GB of WAL.
        """
        missing = tmp_path / "not-there"
        result = _guard(str(missing))
        assert result.returncode == 1
        assert "does not exist" in result.stderr
        assert not missing.exists(), "the guard created the directory it refused"

    def test_writes_nothing_to_stdout(self, tmp_path):
        """Three callers parse their own stdout for KEY=VALUE lines.

        A guard that put prose on stdout would break the parse it exists to
        protect, so every diagnostic goes to stderr.
        """
        result = _guard(str(tmp_path))
        assert result.stdout == ""

    @pytest.mark.skipif(not _have_nas(), reason="no NFS mount at /mnt/backup/ivgs")
    def test_accepts_the_real_nfs_mount(self):
        """The other half: it must not refuse everything.

        A guard that always refused would be trivially 'safe' and would stop
        every backup on the node. Read-only: this calls `stat -f`, nothing else.
        """
        result = _guard(NAS_DIR)
        assert result.returncode == 0, (
            f"the guard refused the real NFS mount: {result.stderr}"
        )
        assert result.stderr == ""


class TestEveryWriterUsesIt:
    """Task 9: EVERY process that writes under /mnt/backup, not just the two
    that were caught."""

    @pytest.mark.parametrize("script", [
        "backup.sh",           # (a) the two nights of failed dumps
        "wal_archive.sh",      # (b) the 1.9 GB WAL split
        "asset_backup.sh",     # the 45 GB of shadowed July snapshots
        "config_backup.sh",    # not caught, same exposure
        "basebackup.sh",       # new in WP-59 -- would have been the third
        "restore.sh",          # reads the WAL archive; a shadowed one replays
                               # a partial history and stops early, silently
    ])
    def test_script_sources_the_guard_and_calls_it(self, script):
        src = (SCRIPTS / script).read_text()
        assert "lib/nfs_guard.sh" in src, (
            f"{script} writes under /mnt/backup and does not source the guard"
        )
        assert "assert_nfs_destination" in src, (
            f"{script} sources the guard and never calls it"
        )

    def test_no_backup_script_still_uses_a_bare_path_check_on_the_nas(self):
        """The `[ ! -d "$NAS_DIR" ]` pattern must not come back.

        It is the check that passed over a shadowed local directory for months.
        """
        for script in ("backup.sh", "asset_backup.sh", "config_backup.sh"):
            src = (SCRIPTS / script).read_text()
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "BACKUP_NAS_DIR" in stripped and stripped.startswith("if [ ! -d"):
                    pytest.fail(
                        f"{script} still gates the NAS on a path check: "
                        f"{stripped!r}. A shadowed local directory is a "
                        f"directory; only the filesystem type distinguishes them."
                    )

    def test_wal_archive_guards_before_it_creates_the_directory(self):
        """Order is the whole point.

        `mkdir -p` on a path whose NFS mount is absent CREATES the shadowed
        local directory, and every subsequent segment lands in it. The guard has
        to run first or it guards nothing.
        """
        src = (SCRIPTS / "wal_archive.sh").read_text()
        body = src[src.index("archive_wal() {"):]
        guard_at = body.index("assert_nfs_destination")
        mkdir_at = body.index('mkdir -p "${WAL_ARCHIVE_DIR}"')
        assert guard_at < mkdir_at, (
            "wal_archive.sh calls mkdir -p before asserting the destination is "
            "the NAS. That ordering is what built the shadowed tree."
        )


class TestMountPropagation:
    """The durable half: a later NFS remount must reach running containers."""

    @pytest.mark.parametrize("compose,mount", [
        ("docker-compose.node01.yml", "/mnt/backup/ivgs/wal"),
        ("docker-compose.override.node01.yml", "/mnt/backup"),
    ])
    def test_backup_family_binds_declare_propagation(self, compose, mount):
        src = (REPO / "ivgs-infra" / compose).read_text()
        assert f"source: {mount}\n" in src, (
            f"{compose} no longer declares {mount} in long bind syntax; a short "
            f"`- {mount}:...` bind cannot carry a propagation setting and "
            f"defaults to rprivate, which is what captured the local inode."
        )
        # The propagation clause must be in the same block as the source.
        block = src[src.index(f"source: {mount}\n"):]
        block = block[: block.index("- type: bind") if "- type: bind" in block[10:] else len(block)]
        assert "propagation: rslave" in block[:600], (
            f"{mount} in {compose} has no `propagation: rslave`. Without it the "
            f"container captures whatever inode is at that path at start time "
            f"and never sees a later NFS mount."
        )

    def test_no_backup_bind_is_left_in_short_syntax(self):
        """A short-form bind cannot carry propagation, so it must not come back."""
        for compose in ("docker-compose.node01.yml",
                        "docker-compose.override.node01.yml"):
            src = (REPO / "ivgs-infra" / compose).read_text()
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("- /mnt/backup"):
                    pytest.fail(
                        f"{compose} has a short-syntax backup bind: {stripped!r}. "
                        f"Short syntax defaults to rprivate propagation."
                    )
