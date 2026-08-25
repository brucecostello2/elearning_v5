"""
IVGS v5 — Seed Fallback Policies
========================================

Seeds default fallback policies into the fallback_policies table (Table 23)
from ivgs-api/config/fallback_policies.yaml.

Scene types: action, talking_head, broll, title_card
Strategy columns: level_1_strategy, level_2_strategy, level_3_strategy,
                  level_4_strategy

Usage:
    python -m ivgs_api.app.scripts.seed_fallback_policies

    Or via docker-compose:
    docker-compose exec api python -m ivgs_api.app.scripts.seed_fallback_policies
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Path to fallback policies YAML
YAML_PATH = Path(__file__).resolve().parents[2] / "config" / "fallback_policies.yaml"

# Valid values for validation
VALID_SCENE_TYPES = {"action", "talking_head", "broll", "title_card"}
VALID_STRATEGIES = {"ai_video", "animated_still", "zoom_pan", "static_image"}


async def seed_fallback_policies(
    db_session_factory: Any | None = None,
    yaml_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Seed fallback policies from YAML into the database.

    Reads ivgs-api/config/fallback_policies.yaml and inserts/upserts each
    policy into the fallback_policies table (Table 23).

    Args:
        db_session_factory: Optional async session factory override.
        yaml_path: Optional YAML file path override.
        force: If True, replace existing policies. If False, skip existing.

    Returns:
        Dict with seeding statistics.
    """
    config_path = yaml_path or YAML_PATH
    log = logger.bind(script="seed_fallback_policies")

    # Load YAML
    if not config_path.exists():
        log.error("yaml_not_found", path=str(config_path))
        return {"status": "error", "message": f"YAML not found: {config_path}"}

    with open(config_path) as f:
        data = yaml.safe_load(f)

    policies = data.get("fallback_policies", [])
    if not policies:
        log.warning("no_policies_in_yaml")
        return {"status": "error", "message": "No policies found in YAML"}

    # Validate
    for policy in policies:
        scene_type = policy.get("scene_type")
        if scene_type not in VALID_SCENE_TYPES:
            log.error("invalid_scene_type", scene_type=scene_type)
            return {
                "status": "error",
                "message": f"Invalid scene_type: {scene_type}",
            }

        for level in ["level_1_strategy", "level_2_strategy",
                       "level_3_strategy", "level_4_strategy"]:
            strategy = policy.get(level)
            if strategy not in VALID_STRATEGIES:
                log.error(
                    "invalid_strategy",
                    scene_type=scene_type,
                    level=level,
                    strategy=strategy,
                )
                return {
                    "status": "error",
                    "message": f"Invalid {level}: {strategy}",
                }

    # Get DB session factory
    if db_session_factory is None:
        # WP-54. Was `from ivgs_api.app.database import get_async_session_factory`.
        # Wrong twice: there is no `ivgs_api` package (the directory is
        # `ivgs-api`, a hyphen), and there is no `app/database.py` or
        # `get_async_session_factory` anywhere in the tree either -- so no
        # rename could have fixed it. `shared.database.async_session_factory`
        # is the real `async_sessionmaker` this call site wants, and it is what
        # `shared.database` itself uses at lines 57 and 76.
        from shared.database import async_session_factory

        db_session_factory = async_session_factory

    # Seed policies
    inserted = 0
    updated = 0
    skipped = 0

    async with db_session_factory() as session:
        async with session.begin():
            from sqlalchemy import text

            for policy in policies:
                scene_type = policy["scene_type"]

                # Check if exists
                result = await session.execute(
                    text(
                        "SELECT 1 FROM fallback_policies "
                        "WHERE scene_type = :scene_type"
                    ),
                    {"scene_type": scene_type},
                )
                exists = result.fetchone() is not None

                if exists and not force:
                    skipped += 1
                    log.info(
                        "policy_skipped_exists",
                        scene_type=scene_type,
                    )
                    continue

                if exists and force:
                    # Update existing
                    await session.execute(
                        text(
                            "UPDATE fallback_policies SET "
                            "level_1_strategy = :l1, "
                            "level_2_strategy = :l2, "
                            "level_3_strategy = :l3, "
                            "level_4_strategy = :l4 "
                            "WHERE scene_type = :scene_type"
                        ),
                        {
                            "scene_type": scene_type,
                            "l1": policy["level_1_strategy"],
                            "l2": policy["level_2_strategy"],
                            "l3": policy["level_3_strategy"],
                            "l4": policy["level_4_strategy"],
                        },
                    )
                    updated += 1
                    log.info("policy_updated", scene_type=scene_type)
                else:
                    # Insert new
                    await session.execute(
                        text(
                            "INSERT INTO fallback_policies "
                            "(scene_type, level_1_strategy, "
                            "level_2_strategy, level_3_strategy, "
                            "level_4_strategy) "
                            "VALUES (:scene_type, :l1, :l2, :l3, :l4)"
                        ),
                        {
                            "scene_type": scene_type,
                            "l1": policy["level_1_strategy"],
                            "l2": policy["level_2_strategy"],
                            "l3": policy["level_3_strategy"],
                            "l4": policy["level_4_strategy"],
                        },
                    )
                    inserted += 1
                    log.info("policy_inserted", scene_type=scene_type)

    result = {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total_policies": len(policies),
    }

    log.info("seed_completed", **result)
    return result


def main() -> None:
    """Entry point for command-line execution."""
    force = "--force" in sys.argv
    result = asyncio.run(seed_fallback_policies(force=force))
    print(f"Seed result: {result}")


if __name__ == "__main__":
    main()
