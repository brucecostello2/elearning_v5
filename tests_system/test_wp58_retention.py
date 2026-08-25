"""
WP-58 — backup retention: the configured value must govern, and the prune must
be incapable of deleting the last surviving copy of unregenerable material.

WHY THESE TESTS DRIVE THE REAL SCRIPTS RATHER THAN A COPY.

WP-54's lesson is that a mechanism must be shown CAPABLE OF ACTING. A test that
asserts "the script contains the string BACKUP_RETENTION_ASSETS_DAYS" would have
passed against the broken code too, because the broken code contained
`BACKUP_RETENTION_DAYS` and looked equally reasonable. So every test here
sources the actual file from `scripts/`, with only the trailing `main "$@"`
suppressed, and then runs the real functions against a TEMPORARY tree.

NOTHING HERE TOUCHES /mnt/backup. Every path is a pytest `tmp_path`. Deleting a
real snapshot to test a retention change would be the exact failure this package
exists to prevent.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _source_and_run(
    script_name: str, snippet: str, env: dict, args: str = "",
) -> str:
    """Source a backup script with its auto-`main` suppressed, then run `snippet`.

    `sed` neutralises the final `main "$@"` (or bare `main`) so sourcing does not
    execute a backup. Everything else — variable resolution, function bodies — is
    the real file on disk.
    """
    script = SCRIPTS / script_name
    # `args` exists for wal_archive.sh, which is a postgres archive_command and
    # declares `readonly WAL_SOURCE_PATH="${1:?...}"` at the top. Sourced with no
    # positional arguments it exits on that guard before reaching the retention
    # line, so the harness must supply the two it expects.
    program = (
        f'source <(sed -e \'s|^main "$@"$|:|\' -e \'s|^main$|:|\' "{script}") {args} '
        f">/dev/null 2>&1\n{snippet}\n"
    )
    full_env = {**os.environ, **env}
    proc = subprocess.run(
        ["bash", "-c", program],
        capture_output=True, text=True, cwd=str(SCRIPTS), env=full_env,
    )
    return proc.stdout.strip()


def _dated_tree(root: Path, days_old: list[int]) -> Path:
    """Build snapshot directories aged N days back from today."""
    import datetime
    root.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    for n in days_old:
        d = today - datetime.timedelta(days=n)
        snap = root / d.isoformat()
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "payload").write_text(f"content-{n}")
        stamp = int(
            datetime.datetime.combine(d, datetime.time(12, 0)).timestamp()
        )
        os.utime(snap, (stamp, stamp))
    return root


# ---------------------------------------------------------------------------
# Task 1 / Task 2 — the configured value governs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "script,variable,value",
    [
        ("backup.sh", "BACKUP_RETENTION_DB_DAYS", "11"),
        ("asset_backup.sh", "BACKUP_RETENTION_ASSETS_DAYS", "13"),
        ("config_backup.sh", "BACKUP_RETENTION_CONFIG_DAYS", "77"),
    ],
)
def test_each_script_reads_its_own_class_variable(script, variable, value):
    out = _source_and_run(script, 'echo "${BACKUP_RETENTION_DAYS}"', {variable: value})
    assert out == value, (
        f"{script} ignored {variable}={value} and resolved {out!r}. That is the "
        "WP-58 defect: the configured value never reaches the prune."
    )


def test_wal_archive_reads_the_configured_wal_variable():
    """Task 2. wal_archive.sh DOES prune — it read a name nothing set."""
    out = _source_and_run(
        "wal_archive.sh", 'echo "${WAL_RETENTION_DAYS}"',
        {"BACKUP_RETENTION_WAL_DAYS": "5"},
        args="/tmp/wp58-probe-wal /tmp/wp58-probe-wal",
    )
    assert out == "5"


def test_one_class_cannot_govern_another():
    """The defect the fix must not introduce.

    All three scripts used to read the single name BACKUP_RETENTION_DAYS. Had
    that been "fixed" by exporting it, setting 14 for assets would have started
    killing database backups at 14 days instead of 30 — worse than the original.
    """
    env = {"BACKUP_RETENTION_ASSETS_DAYS": "3"}
    assert _source_and_run("asset_backup.sh", 'echo "${BACKUP_RETENTION_DAYS}"', env) == "3"
    assert _source_and_run("backup.sh", 'echo "${BACKUP_RETENTION_DAYS}"', env) == "30"
    assert _source_and_run("config_backup.sh", 'echo "${BACKUP_RETENTION_DAYS}"', env) == "90"


def test_the_prune_actually_deletes_by_the_configured_number(tmp_path):
    """Not the resolution — the ACT. Snapshots older than the configured number
    must be gone and newer ones must survive."""
    nas = _dated_tree(tmp_path / "assets", [30, 20, 10, 1])
    out = _source_and_run(
        "asset_backup.sh",
        'cleanup_old_backups >/dev/null 2>&1; ls -1 "${BACKUP_NAS_DIR}"',
        {"BACKUP_NAS_DIR": str(nas), "BACKUP_RETENTION_ASSETS_DAYS": "14"},
    )
    survivors = set(out.split())
    assert len(survivors) == 2, f"expected the two newest to survive, got {survivors}"
    remaining = sorted(p.name for p in nas.iterdir())
    assert len(remaining) == 2


# ---------------------------------------------------------------------------
# Task 3 — the prune cannot delete the last surviving copy
# ---------------------------------------------------------------------------

def test_prune_never_matches_the_monthly_tree(tmp_path):
    """The trap this design had to avoid.

    The prune is `find <nas> -maxdepth 1 -type d -mtime +N`. Any sibling
    directory is a candidate — including the indefinite-retention tree. Aged
    well past retention, `monthly/` must still be there.
    """
    import datetime
    nas = _dated_tree(tmp_path / "assets", [30, 1])
    monthly = nas / "monthly" / "2026-01"
    monthly.mkdir(parents=True)
    (monthly / "logo.png").write_text("the only copy")
    old = int((datetime.datetime.now() - datetime.timedelta(days=400)).timestamp())
    os.utime(nas / "monthly", (old, old))

    _source_and_run(
        "asset_backup.sh", 'cleanup_old_backups >/dev/null 2>&1',
        {"BACKUP_NAS_DIR": str(nas), "BACKUP_RETENTION_ASSETS_DAYS": "14"},
    )
    assert (nas / "monthly").is_dir(), (
        "the daily prune deleted the indefinite-retention tree — this is the "
        "exact outcome Task 3 exists to make impossible"
    )
    assert (monthly / "logo.png").read_text() == "the only copy"


def test_link_dest_never_selects_the_monthly_tree(tmp_path):
    """`monthly` sorts after every `2026-..` name, so a descending sort would
    have picked it as the hard-link base for every future backup."""
    nas = _dated_tree(tmp_path / "assets", [2, 1])
    (nas / "monthly" / "2026-01").mkdir(parents=True)

    out = _source_and_run(
        "asset_backup.sh", 'determine_link_dest',
        {"BACKUP_NAS_DIR": str(nas)},
    )
    assert "monthly" not in out, f"determine_link_dest chose the monthly tree: {out!r}"


def test_promoted_month_survives_the_daily_prune_of_its_source(tmp_path):
    """THE CONDITION, CONSTRUCTED END TO END.

    A library asset arrives in a daily snapshot; the month is promoted; the
    daily snapshot ages past retention and is pruned. The asset must still be
    readable — and with hard links, `rm -rf` on the daily only decremented a
    link count.
    """
    import datetime
    nas = tmp_path / "assets"
    today = datetime.date.today().isoformat()
    daily = nas / today / "seaweedfs-volume"
    daily.mkdir(parents=True)
    library_object = daily / "1.dat"
    library_object.write_text("an uploaded logo that nothing can regenerate")

    # Promote, using the real function.
    _source_and_run(
        "asset_backup.sh", 'promote_monthly_snapshot >/dev/null 2>&1',
        {"BACKUP_NAS_DIR": str(nas), "TARGET_DIR": str(nas / today)},
    )
    month = datetime.date.today().strftime("%Y-%m")
    promoted = nas / "monthly" / month / "seaweedfs-volume" / "1.dat"
    assert promoted.exists(), "promotion did not produce a monthly snapshot"

    # It is the SAME inode — the promotion cost no bytes.
    assert promoted.stat().st_ino == library_object.stat().st_ino, (
        "promotion copied instead of hard-linking; indefinite retention would "
        "then cost a full copy per month"
    )

    # Age the daily past retention and prune for real.
    old = int((datetime.datetime.now() - datetime.timedelta(days=400)).timestamp())
    os.utime(nas / today, (old, old))
    _source_and_run(
        "asset_backup.sh", 'cleanup_old_backups >/dev/null 2>&1',
        {"BACKUP_NAS_DIR": str(nas), "BACKUP_RETENTION_ASSETS_DAYS": "14"},
    )

    assert not (nas / today).exists(), "the daily snapshot should have been pruned"
    assert promoted.exists(), "THE LAST SURVIVING COPY WAS DELETED"
    assert promoted.read_text() == "an uploaded logo that nothing can regenerate"


def test_promotion_is_idempotent(tmp_path):
    """Beat runs daily; only the first run of a month may promote, or every day
    would overwrite the month's snapshot with a later one."""
    import datetime
    nas = tmp_path / "assets"
    today = datetime.date.today().isoformat()
    (nas / today).mkdir(parents=True)
    (nas / today / "first").write_text("first run of the month")

    env = {"BACKUP_NAS_DIR": str(nas), "TARGET_DIR": str(nas / today)}
    _source_and_run("asset_backup.sh", 'promote_monthly_snapshot >/dev/null 2>&1', env)
    (nas / today / "second").write_text("a later day")
    _source_and_run("asset_backup.sh", 'promote_monthly_snapshot >/dev/null 2>&1', env)

    month = datetime.date.today().strftime("%Y-%m")
    promoted = nas / "monthly" / month
    assert (promoted / "first").exists()
    assert not (promoted / "second").exists(), (
        "a second promotion overwrote the month's snapshot"
    )


# ---------------------------------------------------------------------------
# Task 4 — the artifact naming convention, enforced rather than conventional
# ---------------------------------------------------------------------------

CHECKER = SCRIPTS / "check-image-artifacts.sh"
NAME_LIB = SCRIPTS / "lib" / "artifact_name.sh"


def _check_store(store: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(CHECKER), str(store)],
        capture_output=True, text=True,
    )


def test_a_conforming_store_passes(tmp_path):
    store = tmp_path / "artifacts"
    store.mkdir()
    (store / "brucecostello2_ivgs-workers_v5.15.0-library.tar.zst").write_text("x")
    (store / "brucecostello2_ivgs-api_v5.6.0-m2.tar.gz").write_text("x")
    result = _check_store(store)
    assert result.returncode == 0, result.stderr


def test_a_nonconforming_name_is_rejected(tmp_path):
    """THE INCIDENT, RECONSTRUCTED.

    `ivgs-workers-v5.15.0-library.tar.zst` is the exact name WP-56 banked by
    hand. Three nodes had their .env tag bumped and then refused to recreate on
    a missing image. Silently accepting the name is what allowed that; the
    checker must fail, and must name the offending file.
    """
    store = tmp_path / "artifacts"
    store.mkdir()
    (store / "brucecostello2_ivgs-api_v5.6.0-m2.tar.zst").write_text("x")
    (store / "ivgs-workers-v5.15.0-library.tar.zst").write_text("x")

    result = _check_store(store)
    assert result.returncode == 1, (
        "a non-conforming artifact name was accepted — this is the 2026-08-25 "
        "failed fleet deploy, waiting to happen again"
    )
    assert "ivgs-workers-v5.15.0-library.tar.zst" in result.stderr
    assert "brucecostello2_ivgs-api_v5.6.0-m2.tar.zst" not in result.stderr


def test_the_name_is_derived_in_one_place_from_the_image_reference():
    """`artifact_name_for` is the single definition every path must use."""
    out = subprocess.run(
        ["bash", "-c",
         f'source "{NAME_LIB}"; '
         'artifact_name_for ghcr.io/brucecostello2/ivgs-workers:v5.15.0-library'],
        capture_output=True, text=True,
    ).stdout.strip()
    assert out == "brucecostello2_ivgs-workers_v5.15.0-library"


def test_artifact_require_fails_before_a_node_is_touched(tmp_path):
    """The deploy gate. A missing artifact must fail HERE, naming the expected
    path, rather than on three remote nodes after their tags were changed."""
    store = tmp_path / "artifacts"
    store.mkdir()
    result = subprocess.run(
        ["bash", "-c",
         f'source "{NAME_LIB}"; '
         'artifact_require ghcr.io/brucecostello2/ivgs-workers:v9.9.9-absent'],
        capture_output=True, text=True,
        env={**os.environ, "IVGS_IMAGE_ARTIFACTS": str(store)},
    )
    assert result.returncode == 1
    assert "brucecostello2_ivgs-workers_v9.9.9-absent.tar.zst" in result.stderr

    (store / "brucecostello2_ivgs-workers_v9.9.9-absent.tar.zst").write_text("x")
    ok = subprocess.run(
        ["bash", "-c",
         f'source "{NAME_LIB}"; '
         'artifact_require ghcr.io/brucecostello2/ivgs-workers:v9.9.9-absent'],
        capture_output=True, text=True,
        env={**os.environ, "IVGS_IMAGE_ARTIFACTS": str(store)},
    )
    assert ok.returncode == 0
    assert ok.stdout.strip().endswith(
        "brucecostello2_ivgs-workers_v9.9.9-absent.tar.zst"
    )


def test_the_live_artifact_store_conforms():
    """The store on this node, as it actually is. Guards against the next
    hand-rolled `docker save | zstd -o <name>`."""
    result = subprocess.run(
        ["bash", str(CHECKER)], capture_output=True, text=True,
    )
    if "artifact store not found" in result.stderr:
        pytest.skip("artifact store not mounted on this host")
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Task 4 — the rate-limit variables that reached nothing
# ---------------------------------------------------------------------------

def test_rate_limits_read_their_configured_variables(monkeypatch):
    """Second instance of the retention defect: three RATE_LIMIT_* variables set
    in .env since they were written, and no code read any of them."""
    import importlib
    monkeypatch.setenv("RATE_LIMIT_AUTH_LOGIN", "7/minute")
    monkeypatch.setenv("RATE_LIMIT_JOB_TRIGGERS", "2/second")
    monkeypatch.setenv("RATE_LIMIT_CONTENT_CRUD", "500/hour")
    import app.middleware.rate_limit as rl
    importlib.reload(rl)
    try:
        assert rl.RATE_LIMITS["login"] == (7, 60)
        assert rl.RATE_LIMITS["job_trigger"] == (2, 1)
        assert rl.RATE_LIMITS["default"] == (500, 3600)
    finally:
        importlib.reload(rl)


def test_an_unparseable_rate_limit_does_not_become_no_limit(monkeypatch):
    """A limiter that fails OPEN on bad configuration is worse than one that is
    not configurable at all."""
    import importlib
    monkeypatch.setenv("RATE_LIMIT_AUTH_LOGIN", "not-a-rate")
    monkeypatch.setenv("RATE_LIMIT_JOB_TRIGGERS", "0/minute")
    monkeypatch.setenv("RATE_LIMIT_CONTENT_CRUD", "60/fortnight")
    import app.middleware.rate_limit as rl
    importlib.reload(rl)
    try:
        assert rl.RATE_LIMITS["login"] == (5, 60)
        assert rl.RATE_LIMITS["job_trigger"] == (10, 60)
        assert rl.RATE_LIMITS["default"] == (60, 60)
    finally:
        importlib.reload(rl)
