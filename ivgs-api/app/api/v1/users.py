"""
User management endpoints per §5.1.9 — Admin only.

GET    /api/v1/users         — List all users
POST   /api/v1/users         — Create new user
PATCH  /api/v1/users/{id}    — Update user role or password
DELETE /api/v1/users/{id}    — Delete user account
"""
import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.rbac import require_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services import user_service
from app.core.auth import blacklist_all_user_tokens

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List all users (admin only)",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_session),
):
    """List all users with pagination. Admin only per §16.2."""
    users, total = await user_service.list_users(db, page=page, per_page=per_page)
    pages = math.ceil(total / per_page) if per_page > 0 else 0

    return PaginatedResponse[UserResponse](
        data=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user (admin only)",
    dependencies=[Depends(require_admin)],
    responses={
        409: {"description": "Username already exists"},
    },
)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_session),
):
    """
    Create new user. Body: {username, password, role}.
    Admin only per §16.2.
    """
    try:
        user = await user_service.create_user(
            db,
            username=body.username,
            password=body.password,
            role=body.role,
        )
        await db.commit()
        await db.refresh(user)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                }
            },
        )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user by ID (admin only)",
    dependencies=[Depends(require_admin)],
    responses={
        404: {"description": "User not found"},
    },
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
):
    """Get user detail by UUID. Admin only."""
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"User with id '{user_id}' not found",
                }
            },
        )
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user role or password (admin only)",
    dependencies=[Depends(require_admin)],
    responses={
        404: {"description": "User not found"},
    },
)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_session),
):
    """
    Update user role, password, or active status. Admin only per §16.2.

    Password change invalidates all user sessions per §16.3.
    """
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"User with id '{user_id}' not found",
                }
            },
        )

    updated = await user_service.update_user(
        db,
        user=user,
        role=body.role,
        password=body.password,
        is_active=body.is_active,
    )

    # Password change → invalidate all user sessions
    if body.password is not None:
        await blacklist_all_user_tokens(str(user_id))

    await db.commit()
    await db.refresh(updated)
    return UserResponse.model_validate(updated)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete user account (admin only)",
    dependencies=[Depends(require_admin)],
    responses={
        404: {"description": "User not found"},
    },
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
):
    """
    Delete user account. Admin only per §16.2.

    Audit log entries referencing this user will retain user_id = NULL
    (ON DELETE SET NULL).
    """
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"User with id '{user_id}' not found",
                }
            },
        )

    # Invalidate all tokens before deletion
    await blacklist_all_user_tokens(str(user_id))
    await user_service.delete_user(db, user)
    await db.commit()

    return {"message": f"User '{user.username}' deleted successfully"}
