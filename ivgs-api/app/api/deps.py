"""
API dependency re-exports.

Convenience module that collects common FastAPI dependencies
from their canonical locations.
"""
from app.core.auth import get_current_user  # noqa: F401
from shared.database import get_session as get_db  # noqa: F401


async def require_admin(user=None):
    """Placeholder for admin requirement dependency."""
    pass
