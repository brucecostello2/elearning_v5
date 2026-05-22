"""
User CRUD business logic per §5.1.9.

All user management is admin-only. Provides:
- create_user: Register new user with hashed password
- get_user_by_id: Fetch user by UUID
- get_user_by_username: Fetch user by username
- list_users: Paginated user listing
- update_user: Update role, password, or active status
- delete_user: Soft-delete or hard-delete user
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.security import hash_password

logger = logging.getLogger(__name__)


async def create_user(
    db: AsyncSession,
    username: str,
    password: str,
    role: str,
) -> User:
    """
    Create a new user with hashed password.

    Raises ValueError if username already exists.
    """
    existing = await get_user_by_username(db, username)
    if existing:
        raise ValueError(f"Username '{username}' already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("User created: username=%s role=%s id=%s", username, role, user.id)
    return user


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Fetch a user by UUID primary key."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Fetch a user by unique username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def list_users(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[User], int]:
    """
    List users with pagination.

    Returns:
        (users, total_count)
    """
    # Total count
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    # Paginated results
    offset = (page - 1) * per_page
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    users = list(result.scalars().all())

    return users, total


async def update_user(
    db: AsyncSession,
    user: User,
    role: Optional[str] = None,
    password: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> User:
    """
    Update user fields.

    Returns the updated user object.
    """
    if role is not None:
        logger.info(
            f"User role change: user={user.username} "
            f"old_role={user.role} new_role={role}"
        )
        user.role = role

    if password is not None:
        user.password_hash = hash_password(password)
        logger.info("User password changed: user=%s", user.username)

    if is_active is not None:
        user.is_active = is_active
        logger.info(
            f"User active status changed: user={user.username} "
            f"is_active={is_active}"
        )

    await db.flush()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    """
    Hard-delete a user from the database.

    Audit log entries referencing this user will have user_id set to NULL
    (per ON DELETE SET NULL foreign key).
    """
    logger.info("User deleted: username=%s id=%s", user.username, user.id)
    await db.delete(user)
    await db.flush()
