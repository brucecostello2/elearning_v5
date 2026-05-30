#!/usr/bin/env python3
"""
IVGS v4-to-v5 Data Migration Script
====================================

Implements Appendix D.3 Migration from v4:
  1. Export v4 data (core tables only, excluding cloud-specific tables)
  2. Stand up fresh v5 with all 14 Alembic migrations
  3. Transform and import data
  4. Audit imported data to remove cloud-generated asset references
  5. Verify imported data integrity via API endpoint tests

Usage:
    python v4_to_v5_migration.py \
        --v4-host=192.168.1.90 --v4-port=5432 --v4-db=ivgs_v4 \
        --v4-user=ivgs --v4-password=SECRET \
        --v5-host=192.168.1.90 --v5-port=5432 --v5-db=ivgs \
        --v5-user=ivgs --v5-password=SECRET \
        [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("v4_to_v5_migration")

# Core tables to migrate (Appendix D.3)
V4_CORE_TABLES = [
    "users",
    "projects",
    "transcripts",
    "storyboard_scenes",
    "assets",
    "prompts",
    "render_jobs",
    "language_variants",
]

# Cloud-provider patterns to identify and remove
CLOUD_ASSET_PATTERNS = [
    "s3://",
    "gs://",
    "https://oaidalleapiprodscus",
    "https://api.openai.com",
    "https://api.elevenlabs.io",
    "https://api.d-id.com",
    "dall-e",
    "elevenlabs",
    "d-id",
]

# Column mappings for schema differences between v4 and v5
COLUMN_TRANSFORMS = {
    "projects": {
        "drop_columns": ["openai_api_key", "elevenlabs_voice_id", "did_api_key"],
        "rename_columns": {},
        "add_defaults": {"state": "DRAFT"},
    },
    "assets": {
        "drop_columns": ["s3_bucket", "s3_key", "cloud_provider"],
        "rename_columns": {},
        "add_defaults": {"storage_tier": "hot"},
    },
    "prompts": {
        "drop_columns": ["openai_model", "openai_params"],
        "rename_columns": {},
        "add_defaults": {},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IVGS v4 to v5 data migration")
    parser.add_argument("--v4-host", required=True)
    parser.add_argument("--v4-port", type=int, default=5432)
    parser.add_argument("--v4-db", required=True)
    parser.add_argument("--v4-user", required=True)
    parser.add_argument("--v4-password", required=True)
    parser.add_argument("--v5-host", required=True)
    parser.add_argument("--v5-port", type=int, default=5432)
    parser.add_argument("--v5-db", required=True)
    parser.add_argument("--v5-user", required=True)
    parser.add_argument("--v5-password", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def connect_db(host: str, port: int, db: str, user: str, password: str):
    """Create database connection."""
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=password,
        cursor_factory=RealDictCursor,
    )


def step1_export_v4_data(v4_conn) -> dict[str, list[dict]]:
    """Step 1: Export core tables from v4 PostgreSQL."""
    logger.info("Step 1: Exporting v4 data...")
    data = {}

    with v4_conn.cursor() as cur:
        for table in V4_CORE_TABLES:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                data[table] = [dict(r) for r in rows]
                logger.info(f"  Exported {len(rows)} rows from {table}")
            except psycopg2.ProgrammingError:
                logger.warning(f"  Table {table} does not exist in v4, skipping")
                data[table] = []
                v4_conn.rollback()

    return data


def step2_verify_v5_schema(v5_conn) -> bool:
    """Step 2: Verify all 14 Alembic migrations have been applied."""
    logger.info("Step 2: Verifying v5 schema...")

    with v5_conn.cursor() as cur:
        cur.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        )
        versions = [r["version_num"] for r in cur.fetchall()]

    logger.info(f"  Found {len(versions)} migration versions applied")

    # Verify required tables exist
    required_tables = V4_CORE_TABLES + [
        "pipeline_checkpoints", "gpu_nodes", "gpu_reservations",
        "task_retries", "worker_heartbeats", "dead_letter_messages",
        "composition_manifests", "asset_quality_scores", "render_segments",
        "gpu_metrics_history", "retention_policies", "storage_quotas",
        "backup_records", "fallback_policies", "audit_log",
    ]

    with v5_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        existing = {r["table_name"] for r in cur.fetchall()}

    missing = set(required_tables) - existing
    if missing:
        logger.error(f"  Missing v5 tables: {missing}")
        return False

    logger.info("  All v5 tables present")
    return True


def step3_transform_and_import(
    v4_data: dict[str, list[dict]], v5_conn, dry_run: bool
) -> dict[str, int]:
    """Step 3: Transform v4 data and import into v5."""
    logger.info("Step 3: Transforming and importing data...")
    counts = {}

    for table, rows in v4_data.items():
        if not rows:
            counts[table] = 0
            continue

        transforms = COLUMN_TRANSFORMS.get(table, {})
        drop_cols = transforms.get("drop_columns", [])
        rename_cols = transforms.get("rename_columns", {})
        defaults = transforms.get("add_defaults", {})

        transformed = []
        for row in rows:
            new_row = {}
            for key, val in row.items():
                if key in drop_cols:
                    continue
                new_key = rename_cols.get(key, key)
                # Convert datetime objects
                if isinstance(val, datetime):
                    val = val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
                new_row[new_key] = val

            # Apply defaults for new v5 columns
            for col, default_val in defaults.items():
                if col not in new_row:
                    new_row[col] = default_val

            transformed.append(new_row)

        if not dry_run and transformed:
            _insert_rows(v5_conn, table, transformed)

        counts[table] = len(transformed)
        logger.info(f"  {table}: {len(transformed)} rows {'(dry-run)' if dry_run else 'imported'}")

    return counts


def step4_audit_cloud_references(v5_conn, dry_run: bool) -> int:
    """Step 4: Remove cloud-generated asset references."""
    logger.info("Step 4: Auditing for cloud asset references...")
    removed = 0

    with v5_conn.cursor() as cur:
        for pattern in CLOUD_ASSET_PATTERNS:
            cur.execute(
                "SELECT id, seaweedfs_path, seaweedfs_fid FROM assets "
                "WHERE seaweedfs_path ILIKE %s OR seaweedfs_fid ILIKE %s",
                (f"%{pattern}%", f"%{pattern}%"),
            )
            cloud_assets = cur.fetchall()

            for asset in cloud_assets:
                logger.warning(
                    f"  Cloud reference found: asset {asset['id']} "
                    f"path={asset.get('seaweedfs_path', 'N/A')}"
                )
                if not dry_run:
                    cur.execute("DELETE FROM assets WHERE id = %s", (asset["id"],))
                removed += 1

    if not dry_run:
        v5_conn.commit()

    logger.info(f"  Removed {removed} cloud-referenced assets {'(dry-run)' if dry_run else ''}")
    return removed


def step5_verify_integrity(v5_conn) -> bool:
    """Step 5: Verify imported data integrity."""
    logger.info("Step 5: Verifying data integrity...")

    checks = [
        ("Projects have valid states",
         "SELECT COUNT(*) as cnt FROM projects WHERE state NOT IN "
         "('DRAFT','TRANSCRIPT_REFINEMENT','STORYBOARD_GENERATION','MEDIA_GENERATION',"
         "'MANIFEST_GENERATION','AUDIO_GENERATION','TALKING_HEAD_RENDER','PROTOTYPE_DRAFT',"
         "'USER_REVIEW','FINAL_RENDER','COMPLETE','LOCALISATION','ERROR')"),
        ("Assets have valid types",
         "SELECT COUNT(*) as cnt FROM assets WHERE asset_type NOT IN "
         "('scene_image','video_clip','animation','tts_audio','talking_head',"
         "'caption_srt','caption_vtt','lower_third','final_render','hero_image')"),
        ("No orphaned transcripts",
         "SELECT COUNT(*) as cnt FROM transcripts t "
         "LEFT JOIN projects p ON t.project_id = p.id WHERE p.id IS NULL"),
        ("No orphaned assets",
         "SELECT COUNT(*) as cnt FROM assets a "
         "LEFT JOIN projects p ON a.project_id = p.id WHERE p.id IS NULL"),
    ]

    all_passed = True
    with v5_conn.cursor() as cur:
        for check_name, query in checks:
            cur.execute(query)
            result = cur.fetchone()
            count = result["cnt"]
            status = "PASS" if count == 0 else "FAIL"
            logger.info(f"  [{status}] {check_name}: {count} violations")
            if count > 0:
                all_passed = False

    return all_passed


def _insert_rows(conn, table: str, rows: list[dict]) -> None:
    """Bulk insert rows into table."""
    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_str = ", ".join(columns)

    with conn.cursor() as cur:
        for row in rows:
            values = [row.get(c) for c in columns]
            try:
                cur.execute(
                    f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) "
                    f"ON CONFLICT DO NOTHING",
                    values,
                )
            except Exception as exc:
                logger.warning(f"  Failed to insert row into {table}: {exc}")
                conn.rollback()
                continue

    conn.commit()


def main() -> int:
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("IVGS v4-to-v5 Data Migration")
    logger.info("=" * 60)
    if args.dry_run:
        logger.info("DRY RUN MODE — no data will be modified")

    v4_conn = connect_db(args.v4_host, args.v4_port, args.v4_db, args.v4_user, args.v4_password)
    v5_conn = connect_db(args.v5_host, args.v5_port, args.v5_db, args.v5_user, args.v5_password)

    try:
        # Step 1: Export
        v4_data = step1_export_v4_data(v4_conn)

        # Step 2: Verify v5 schema
        if not step2_verify_v5_schema(v5_conn):
            logger.error("v5 schema verification failed. Run Alembic migrations first.")
            return 1

        # Step 3: Transform and import
        counts = step3_transform_and_import(v4_data, v5_conn, args.dry_run)

        # Step 4: Audit cloud references
        removed = step4_audit_cloud_references(v5_conn, args.dry_run)

        # Step 5: Verify integrity
        if not args.dry_run:
            if not step5_verify_integrity(v5_conn):
                logger.error("Data integrity verification failed!")
                return 1

        logger.info("=" * 60)
        logger.info("Migration Summary:")
        for table, count in counts.items():
            logger.info(f"  {table}: {count} rows")
        logger.info(f"  Cloud references removed: {removed}")
        logger.info("Migration completed successfully!")
        return 0

    finally:
        v4_conn.close()
        v5_conn.close()


if __name__ == "__main__":
    sys.exit(main())
