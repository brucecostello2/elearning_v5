"""
WP-60 Task 12 — defects found executing WP-59's own operator blocks.

Each of these pins a property that a `--dry-run` flag is supposed to guarantee
and did not. They drive the REAL scripts, not a reimplementation of them.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text()


def _code(name: str) -> str:
    """The script with comment lines removed.

    These tests reason about CONTROL FLOW, and this package's scripts carry
    long comments that quote the very call names being asserted absent. Without
    this the assertions match prose.
    """
    return "\n".join(
        line for line in _read(name).splitlines()
        if not line.lstrip().startswith("#")
    )


# ---------------------------------------------------------------------------
# 12(a) — a dry run must not be able to proceed
# ---------------------------------------------------------------------------

class TestDryRunCannotReachADestructivePrompt:
    def test_confirm_restore_returns_before_prompting_on_a_dry_run(self):
        """The ordering defect, asserted structurally.

        `confirm_restore` gated only on SKIP_CONFIRMATION, so `--dry-run`
        walked into the interactive "Type 'RESTORE'" prompt under a banner
        announcing it was about to destroy the live database. The operator
        Ctrl-C'd there and WP-59 §8.7 step 4 was never executed.
        """
        body = _code("restore.sh")
        start = body.index("confirm_restore() {")
        end = body.index("\n}", start)
        fn = body[start:end]

        dry_gate = fn.index('if [ "${DRY_RUN}" = true ]; then')
        prompt = fn.index("read -rp")
        assert dry_gate < prompt, (
            "the DRY_RUN gate must come before the prompt, not after it"
        )
        # And it must RETURN, not merely warn.
        assert "return 0" in fn[dry_gate:prompt]

    def test_a_dry_run_completes_with_stdin_closed(self, tmp_path):
        """The behavioural half: with no stdin, a script that prompts hangs or
        fails. This one exits 0."""
        proc = subprocess.run(
            ["bash", str(SCRIPTS / "restore.sh"), "2026-01-01",
             "--pit", "2026-01-01-00:00", "--dry-run"],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "LOG_DIR": str(tmp_path)},
        )
        combined = proc.stdout + proc.stderr
        assert "Type 'RESTORE'" not in combined, (
            "a dry run printed the destructive confirmation prompt"
        )
        # It may exit non-zero on a missing backup date, which is correct and
        # is not what this test is about. What must never appear is the prompt.

    def test_pitr_never_enters_the_logical_restore_sequence(self):
        """12(a)'s harder half. The brief asked whether the banner naming the
        LIVE database on a --pit run was stale or a real targeting defect.

        It was real: main() ran stop_services -> decrypt_and_decompress ->
        drop_and_recreate -> restore_database BEFORE apply_wal_logs, so a real
        --pit run would have dropped and recreated `ivgs` on localhost:5432 to
        rehearse a recovery. --dry-run hid it because all four short-circuit.
        """
        body = _code("restore.sh")
        start = body.index("main() {")
        main = body[start:body.index("\nmain \"$@\"")]

        drop = main.index("    drop_and_recreate")
        # main() has TWO such conditions: the mode announcement near the top,
        # and the dispatch. The dispatch is the last one before the
        # destructive steps.
        pit_branch = main.rindex('if [ -n "${PIT_TARGET}" ]; then', 0, drop)
        assert pit_branch < drop, "the PITR branch must precede the destructive steps"

        # The body of that `if`, up to its own `fi` -- not up to the next
        # destructive call, which sits AFTER the branch and is exactly what
        # the branch must return before reaching.
        branch = main[pit_branch:main.index("\n    fi", pit_branch)]
        assert "apply_wal_logs" in branch
        assert "return 0" in branch, (
            "the PITR branch must return, not fall through into the "
            "logical-restore sequence below it"
        )
        for destructive in ("stop_services", "drop_and_recreate",
                            "restore_database", "restart_services"):
            assert destructive not in branch, (
                f"{destructive} is reachable from inside the PITR branch"
            )

    def test_the_banner_states_the_true_target_on_both_paths(self):
        body = _read("restore.sh")
        assert 'live_database_touched\\":false' in body
        assert 'live_database_touched\\":true' in body


# ---------------------------------------------------------------------------
# 12(b) — dry run and real run must validate the same chain
# ---------------------------------------------------------------------------

class TestBasebackupPreflightExercisesReplication:
    def test_preflight_opens_a_real_replication_connection(self):
        """The pre-flight tested `rolreplication` and `max_wal_senders` -- both
        true -- and never attempted a replication CONNECTION, which is what
        pg_hba governs. So the dry run passed while the real run could not
        connect: strictly fewer preconditions than the path it gates."""
        body = _read("basebackup.sh")
        assert "replication=database" in body, (
            "pre-flight does not open a replication-protocol connection"
        )
        assert "IDENTIFY_SYSTEM" in body

    def test_the_handshake_runs_inside_preflight_not_after_it(self):
        """It must run on the DRY-RUN path too, or it validates nothing the dry
        run claims. `preflight()` is called before the dry-run exit, so being
        inside preflight is the property that matters."""
        body = _code("basebackup.sh")
        start = body.index("preflight() {")
        end = body.index("\ntake_base_backup() {")
        assert "IDENTIFY_SYSTEM" in body[start:end], (
            "the replication handshake is outside preflight(), so a dry run "
            "would skip the one check that distinguishes it from the real path"
        )

    def test_the_replication_hba_row_is_provisioned_not_hand_edited(self):
        """The operator's hand-edit lived in the postgres DATA VOLUME, where a
        data-directory rebuild silently loses it -- taking the weekly base
        backup, and with it PITR, down quietly."""
        hba = (REPO / "configs" / "postgres" / "pg_hba.conf")
        assert hba.exists(), "configs/postgres/pg_hba.conf is missing"
        text = hba.read_text()
        assert "host    replication     ivgs            172.20.0.0/16           scram-sha-256" in text

        base = (REPO / "ivgs-infra" / "docker-compose.node01.yml").read_text()
        assert "-c hba_file=/etc/postgresql/pg_hba.conf" in base, (
            "postgres is not told to use the committed hba file"
        )

    def test_the_hba_flag_is_not_in_an_override(self):
        """Compose REPLACES `command` rather than merging it. Setting the flag
        in the override would have dropped the base's entire -c list, including
        archive_mode=on and archive_command -- WAL archiving would have stopped
        with no error at all."""
        override = (REPO / "ivgs-infra" /
                    "docker-compose.override.node01.yml").read_text()
        import yaml
        parsed = yaml.safe_load(override)
        assert "command" not in parsed["services"]["postgres"]


# ---------------------------------------------------------------------------
# 12(c) — cross-user logging under default hardening
# ---------------------------------------------------------------------------

SOURCING_SCRIPTS = [
    "backup.sh", "asset_backup.sh", "config_backup.sh", "wal_archive.sh",
    "basebackup.sh", "restore.sh", "verify_backup.sh",
]


class TestPerWriterLogFiles:
    @pytest.mark.parametrize("script", SOURCING_SCRIPTS)
    def test_no_script_still_chmods_a_shared_log(self, script):
        """666-in-1777 is forbidden by Ubuntu's default fs.protected_regular=2,
        which ignores the mode entirely. Every `|| true` on those lines hid it
        until the operator hit EACCES running WP-59's own block."""
        body = _read(script)
        assert 'chmod 666 "${LOG_FILE}"' not in body
        assert 'touch "${LOG_FILE}"' not in body

    @pytest.mark.parametrize("script", SOURCING_SCRIPTS)
    def test_every_script_sources_the_one_helper(self, script):
        body = _read(script)
        assert "lib/logfile.sh" in body, f"{script} does not source the helper"
        assert "ivgs_log_file" in body

    def test_the_helper_names_the_file_after_the_writer(self, tmp_path):
        out = subprocess.run(
            ["bash", "-c",
             f'. "{SCRIPTS}/lib/logfile.sh"; ivgs_log_file probe "{tmp_path}"'],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        who = subprocess.run(["id", "-un"], capture_output=True,
                             text=True, check=True).stdout.strip()
        assert out == str(tmp_path / f"probe.{who}.log")
        assert Path(out).exists(), "the helper must create the file it names"

    def test_the_helper_falls_back_rather_than_losing_the_log(self, tmp_path):
        """A script must not die because it could not open a log, and must not
        silently discard it either."""
        unwritable = tmp_path / "nope"
        unwritable.mkdir()
        unwritable.chmod(0o500)
        try:
            proc = subprocess.run(
                ["bash", "-c",
                 f'. "{SCRIPTS}/lib/logfile.sh"; ivgs_log_file probe "{unwritable}"'],
                capture_output=True, text=True, check=True,
            )
        finally:
            unwritable.chmod(0o700)
        assert proc.stdout.strip().startswith("/tmp/") or "ivgs-probe" in proc.stdout
        assert "WARNING" in proc.stderr, "the fallback must be announced, not silent"


# ---------------------------------------------------------------------------
# 12(d) — docker exec heredocs
# ---------------------------------------------------------------------------

def test_no_shipped_script_runs_a_docker_exec_heredoc_without_stdin():
    """`docker exec <c> python - <<'PY'` without -i attaches no stdin, so the
    interpreter reads EOF, executes an EMPTY script, and exits 0. WP-59's §7.6
    blocks did exactly that: a failure rendered as a success."""
    offenders = []
    for path in list(SCRIPTS.rglob("*.sh")) + list(REPO.glob("dev/**/*.sh")):
        for num, line in enumerate(path.read_text().splitlines(), 1):
            if "docker exec" not in line or "<<" not in line:
                continue
            head = line.split("<<", 1)[0]
            if " -i" not in head and " -it" not in head:
                offenders.append(f"{path.relative_to(REPO)}:{num}: {line.strip()}")
    assert not offenders, "docker exec heredoc without -i:\n" + "\n".join(offenders)
