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
import hmac
import logging

from fastapi import Depends, Header, HTTPException, status

from app.models.user import User
from app.core.auth import get_current_user, get_service_or_user
from shared.config import settings
from shared.models.enums import UserRole

logger = logging.getLogger(__name__)


async def require_mbcp_ingest(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    """AD-04 seam-1 receiver auth: a valid MBCP service token.

    MBCP's ``AD01Export`` posts with an ``X-Service-Token`` header; this
    matches that contract (not Bearer). Machine-to-machine — the caller is the
    external certifier, so this returns nothing. Constant-time compare against
    ``IVGS_MBCP_INGEST_TOKEN`` (distinct from the internal pipeline token).
    """
    if not x_service_token or not hmac.compare_digest(
        x_service_token, settings.IVGS_MBCP_INGEST_TOKEN
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_INGEST_TOKEN",
                    "message": "A valid X-Service-Token is required.",
                }
            },
        )


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


async def require_service_or_privileged_user(
    current_user: User = Depends(get_service_or_user),
) -> User:
    """Dual-mode gate for worker-called *and* human-mutating endpoints
    (e.g. asset upload — the rbac contract makes it operator-or-admin).

    Accepts the internal service token (resolves to svc-pipeline, seeded
    admin) or a user with operator/admin role; denies viewer with 403.
    Distinct from ``get_service_or_user``, which authenticates but does not
    enforce role — a viewer JWT passed that check and could upload.
    """
    allowed = (UserRole.ADMIN.value, UserRole.OPERATOR.value)
    if current_user.role not in allowed:
        logger.warning(
            f"RBAC denied: user={current_user.username} role={current_user.role} "
            f"required={list(allowed)}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": (
                        f"Role '{current_user.role}' is not permitted for this "
                        f"operation. Required: {', '.join(allowed)}"
                    ),
                }
            },
        )
    return current_user
require_any_authenticated = _require_role(
    UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER
)
