"""
CLI script to seed the internal service account (svc-pipeline).

Usage:
    docker compose exec api python -m app.scripts.seed_service_account

Idempotent. Creates the svc-pipeline user if absent. The worker fleet authenticates to the API
with the shared IVGS_SERVICE_TOKEN, which the API's get_service_or_user dependency resolves to
this account. It never logs in by password (a random throwaway is set and discarded).

Run once during deployment, after migrations, alongside create_admin / seed_prompts.

Role note: seeded as 'admin' because that is the only cross-project role in the current
{admin, operator, viewer} enum; operator/viewer are ownership-scoped. Downgrade to a dedicated
least-privilege 'service' role when AD-01's RBAC lands (user_role enum ALTER).
"""
import asyncio
import logging
import secrets
import sys

from shared.database import get_db_context
from shared.logging_config import setup_logging
from app.services.user_service import create_user, get_user_by_username

setup_logging(service_name="ivgs-seed-service-account")
logger = logging.getLogger(__name__)

SERVICE_USERNAME = "svc-pipeline"
SERVICE_ROLE = "admin"


async def main() -> None:
    async with get_db_context() as db:
        existing = await get_user_by_username(db, SERVICE_USERNAME)
        if existing:
            logger.info("Service account '%s' already exists — skipping", SERVICE_USERNAME)
            print(f"Service account '{SERVICE_USERNAME}' already exists.")
            return
        throwaway = secrets.token_urlsafe(48)  # never disclosed; auth is via IVGS_SERVICE_TOKEN
        user = await create_user(
            db, username=SERVICE_USERNAME, password=throwaway, role=SERVICE_ROLE,
        )
        print("Service account created:")
        print(f"  Username: {user.username}")
        print(f"  Role:     {user.role}")
        print(f"  ID:       {user.id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error("Failed to seed service account: %s", e)
        sys.exit(1)
