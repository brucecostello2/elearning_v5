"""
CLI script to create the initial admin user.

Usage:
    python -m app.scripts.create_admin --username admin --password Admin123! --role admin

This is run once during initial deployment (before the API is serving requests)
to bootstrap the first admin account.
"""
import argparse
import asyncio
import logging
import sys

from shared.database import get_db_context
from shared.logging_config import setup_logging
from app.services.user_service import create_user, get_user_by_username

setup_logging(service_name="ivgs-admin-cli")
logger = logging.getLogger(__name__)


async def main(username: str, password: str, role: str) -> None:
    """Create the admin user if it doesn't already exist."""
    async with get_db_context() as db:
        existing = await get_user_by_username(db, username)
        if existing:
            logger.info("User '%s' already exists — skipping creation", username)
            print(f"User '{username}' already exists.")
            return

        user = await create_user(db, username=username, password=password, role=role)
        print("User created successfully:")
        print(f"  Username: {user.username}")
        print(f"  Role:     {user.role}")
        print(f"  ID:       {user.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create initial IVGS admin user")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "operator", "viewer"],
        help="User role (default: admin)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.username, args.password, args.role))
    except Exception as e:
        logger.error("Failed to create admin user: %s", e)
        sys.exit(1)
