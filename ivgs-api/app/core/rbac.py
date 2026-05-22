"""
Role-Based Access Control dependencies per §16.2.

Roles:
- Admin: Full system access
- Operator: Own projects CRUD, upload, project/scene prompts, trigger renders
- Viewer: Read-only gallery, video player, download final renders

Usage:
    @router.get("/admin-only", dependencies=[Depends(require_admin)])
    async def admin_endpoint(): ...
"""
import logging

from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.core.auth import get_current_user
from shared.models.enums import UserRole

logger = logging.getLogger(__name__)


def _require_role(*allowed_roles: UserRole):
    """
    Factory that returns a FastAPI dependency enforcing role membership.

    Raises 403 PERMISSION_DENIED if the authenticated user's role is not
    in the allowed set.
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in [r.value for r in allowed_roles]:
            logger.warning(
                f"RBAC denied: user={current_user.username} role={current_user.role} "
                f"required={[r.value for r in allowed_roles]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": (
                            f"Role '{current_user.role}' is not permitted for this operation. "
                            f"Required: {', '.join(r.value for r in allowed_roles)}"
                        ),
                    }
                },
            )
        return current_user

    return role_checker


# Pre-built dependency instances for common role checks
require_admin = _require_role(UserRole.ADMIN)
require_operator_or_admin = _require_role(UserRole.ADMIN, UserRole.OPERATOR)
require_any_authenticated = _require_role(
    UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER
)
