"""Backup-worker test setup.

The task module reads POSTGRES_DSN_SYNC and SCRIPTS_DIR at import time, so
these must be set before it is imported (conftest runs first). SCRIPTS_DIR
points at an empty dir so backup.sh is missing -> the script runner returns
non-zero -> the task's failure path runs.
"""
import os
import tempfile

os.environ.setdefault(
    "POSTGRES_DSN_SYNC",
    os.environ.get("BACKUP_TEST_DSN", "postgresql://postgres@127.0.0.1:5432/ivgs_test"),
)
os.environ.setdefault("SCRIPTS_DIR", tempfile.mkdtemp(prefix="backup-scripts-empty-"))
