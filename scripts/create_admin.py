#!/usr/bin/env python3
# =============================================================================
# IVGS v5 — Create Initial Admin User
# =============================================================================
# Spec reference: Appendix D.4 — Seed Data Requirements
#                 §16.1 Table 16-1 — bcrypt cost factor 12
#
# Usage:
#   python scripts/create_admin.py --email admin@ivgs.local --password <secret>
#   python scripts/create_admin.py  (interactive prompt)
#
# This script:
#   1. Connects to PostgreSQL using DATABASE_URL env var
#   2. Creates an admin user with bcrypt-hashed password (cost 12)
#   3. Assigns the 'admin' role per §16.2 Table 16-2
#   4. Writes an audit_log entry per §16.3
# =============================================================================

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

import bcrypt
import psycopg


def create_admin(email: str, password: str, database_url: str) -> str:
    """
    Create admin user in PostgreSQL.

    Args:
        email: Admin email address
        password: Plain-text password (will be bcrypt hashed)
        database_url: PostgreSQL connection string

    Returns:
        User ID of created admin
    """
    # Hash password with bcrypt cost factor 12 per §16.1 Table 16-1
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")

    user_id = str(uuid4())
    now = datetime.now(timezone.utc)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Check if user already exists
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing:
                print(f"Admin user already exists with ID: {existing[0]}")
                return existing[0]

            # Create admin user
            cur.execute(
                """
                INSERT INTO users (id, email, password_hash, role, created_at, updated_at)
                VALUES (%s, %s, %s, 'admin', %s, %s)
                """,
                (user_id, email, password_hash, now, now),
            )

            # Write audit log entry per §16.3
            cur.execute(
                """
                INSERT INTO audit_log (id, user_id, action, entity_type, entity_id,
                                       after_state, client_ip, created_at)
                VALUES (%s, %s, 'create', 'user', %s, %s, '127.0.0.1', %s)
                """,
                (
                    str(uuid4()),
                    user_id,
                    user_id,
                    f'{{"email": "{email}", "role": "admin"}}',
                    now,
                ),
            )

        conn.commit()

    return user_id


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create initial IVGS admin user (Appendix D.4)"
    )
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password (prompted if omitted)")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL URL (default: $DATABASE_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        return 1

    email = args.email or input("Admin email: ").strip()
    if not email:
        print("Error: email is required", file=sys.stderr)
        return 1

    password = args.password or getpass.getpass("Admin password: ")
    if len(password) < 12:
        print("Error: password must be at least 12 characters", file=sys.stderr)
        return 1

    # Confirm password if interactive
    if not args.password:
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: passwords do not match", file=sys.stderr)
            return 1

    user_id = create_admin(email, password, args.database_url)
    print(f"✓ Admin user created: {email} (ID: {user_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
