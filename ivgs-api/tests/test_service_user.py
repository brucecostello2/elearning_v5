"""
Phase 4 — User Service Unit Tests.

Tests business logic in app/services/user_service.py:
  - create_user: uniqueness, hashing, role assignment
  - get_user_by_id / get_user_by_username
  - list_users: pagination
  - update_user: role, password, is_active
  - delete_user
"""

import pytest
from uuid import uuid4

from app.services.user_service import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    update_user,
    delete_user,
)
from app.core.security import verify_password

pytestmark = pytest.mark.asyncio


class TestCreateUser:
    async def test_create_user_success(self, db_session):
        user = await create_user(db_session, "svc_test_user", "Str0ngP@ss1", "operator")
        assert user.username == "svc_test_user"
        assert user.role == "operator"
        assert user.is_active is True
        assert user.id is not None

    async def test_create_user_password_is_hashed(self, db_session):
        user = await create_user(db_session, "svc_hash_user", "Str0ngP@ss1", "viewer")
        assert user.password_hash != "Str0ngP@ss1"
        assert verify_password("Str0ngP@ss1", user.password_hash)

    async def test_create_user_duplicate_username_raises(self, db_session):
        await create_user(db_session, "svc_dup_user", "Str0ngP@ss1", "operator")
        with pytest.raises(ValueError, match="already exists"):
            await create_user(db_session, "svc_dup_user", "An0therP@ss", "viewer")

    async def test_create_user_admin_role(self, db_session):
        user = await create_user(db_session, "svc_admin_user", "Str0ngP@ss1", "admin")
        assert user.role == "admin"


class TestGetUser:
    async def test_get_user_by_id_found(self, db_session):
        user = await create_user(db_session, "svc_get_id", "Str0ngP@ss1", "operator")
        found = await get_user_by_id(db_session, user.id)
        assert found is not None
        assert found.id == user.id

    async def test_get_user_by_id_not_found(self, db_session):
        found = await get_user_by_id(db_session, uuid4())
        assert found is None

    async def test_get_user_by_username_found(self, db_session):
        await create_user(db_session, "svc_get_name", "Str0ngP@ss1", "operator")
        found = await get_user_by_username(db_session, "svc_get_name")
        assert found is not None
        assert found.username == "svc_get_name"

    async def test_get_user_by_username_not_found(self, db_session):
        found = await get_user_by_username(db_session, "nonexistent_user_xyz")
        assert found is None


class TestListUsers:
    async def test_list_users_returns_tuple(self, db_session):
        users, total = await list_users(db_session)
        assert isinstance(users, list)
        assert isinstance(total, int)

    async def test_list_users_pagination(self, db_session):
        # Create several users
        for i in range(5):
            await create_user(db_session, f"svc_list_{i}", "Str0ngP@ss1", "viewer")
        
        users_p1, total = await list_users(db_session, page=1, per_page=2)
        assert len(users_p1) == 2
        assert total >= 5
        
        users_p2, _ = await list_users(db_session, page=2, per_page=2)
        assert len(users_p2) == 2
        # No overlap
        ids_p1 = {u.id for u in users_p1}
        ids_p2 = {u.id for u in users_p2}
        assert ids_p1.isdisjoint(ids_p2)


class TestUpdateUser:
    async def test_update_role(self, db_session):
        user = await create_user(db_session, "svc_upd_role", "Str0ngP@ss1", "viewer")
        updated = await update_user(db_session, user, role="operator")
        assert updated.role == "operator"

    async def test_update_password(self, db_session):
        user = await create_user(db_session, "svc_upd_pass", "Str0ngP@ss1", "operator")
        old_hash = user.password_hash
        updated = await update_user(db_session, user, password="NewStr0ng@2")
        assert updated.password_hash != old_hash
        assert verify_password("NewStr0ng@2", updated.password_hash)

    async def test_update_is_active(self, db_session):
        user = await create_user(db_session, "svc_upd_active", "Str0ngP@ss1", "operator")
        assert user.is_active is True
        updated = await update_user(db_session, user, is_active=False)
        assert updated.is_active is False

    async def test_update_no_change(self, db_session):
        user = await create_user(db_session, "svc_upd_none", "Str0ngP@ss1", "operator")
        updated = await update_user(db_session, user)
        assert updated.role == "operator"  # unchanged


class TestDeleteUser:
    async def test_delete_user(self, db_session):
        user = await create_user(db_session, "svc_del_user", "Str0ngP@ss1", "viewer")
        uid = user.id
        await delete_user(db_session, user)
        found = await get_user_by_id(db_session, uid)
        assert found is None
