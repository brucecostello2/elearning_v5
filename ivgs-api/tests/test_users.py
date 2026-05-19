"""
User CRUD endpoint tests.

Covers: list, create, get, update, delete users with RBAC enforcement.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_user, make_auth_header


# ===================================================================
# List Users
# ===================================================================


@pytest.mark.asyncio
async def test_list_users_as_admin(client: AsyncClient, admin_user):
    """Admin can list all users."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert "pages" in data
    assert "has_more" in data


@pytest.mark.asyncio
async def test_list_users_as_operator_forbidden(client: AsyncClient, operator_user):
    """Operator cannot list users — 403 PERMISSION_DENIED."""
    user, _ = operator_user
    headers = make_auth_header(user)

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_list_users_as_viewer_forbidden(client: AsyncClient, viewer_user):
    """Viewer cannot list users — 403 PERMISSION_DENIED."""
    user, _ = viewer_user
    headers = make_auth_header(user)

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403


# ===================================================================
# Create User
# ===================================================================


@pytest.mark.asyncio
async def test_create_user_as_admin(client: AsyncClient, admin_user):
    """Admin can create a new user."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.post(
        "/api/v1/users",
        json={
            "username": "newuser1",
            "password": "NewUser123",
            "role": "operator",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser1"
    assert data["role"] == "operator"
    assert data["is_active"] is True
    assert "password_hash" not in data  # Password hash never exposed


@pytest.mark.asyncio
async def test_create_user_duplicate_username(client: AsyncClient, admin_user):
    """Creating a user with an existing username returns 409."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.post(
        "/api/v1/users",
        json={
            "username": user.username,
            "password": "DupePass123",
            "role": "viewer",
        },
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_user_weak_password(client: AsyncClient, admin_user):
    """Weak password (no uppercase/digit) returns 422."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.post(
        "/api/v1/users",
        json={
            "username": "weakuser",
            "password": "weakpassword",
            "role": "viewer",
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_invalid_role(client: AsyncClient, admin_user):
    """Invalid role returns 422."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.post(
        "/api/v1/users",
        json={
            "username": "badrole",
            "password": "GoodPass123",
            "role": "superadmin",
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_as_operator_forbidden(client: AsyncClient, operator_user):
    """Operator cannot create users — 403."""
    user, _ = operator_user
    headers = make_auth_header(user)

    response = await client.post(
        "/api/v1/users",
        json={
            "username": "blocked",
            "password": "Blocked123",
            "role": "viewer",
        },
        headers=headers,
    )
    assert response.status_code == 403


# ===================================================================
# Update User
# ===================================================================


@pytest.mark.asyncio
async def test_update_user_role(client: AsyncClient, admin_user, db_session):
    """Admin can change a user's role."""
    admin, _ = admin_user
    target, _ = await create_test_user(
        db_session, username="target_role", role="viewer"
    )
    headers = make_auth_header(admin)

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"role": "operator"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == "operator"


@pytest.mark.asyncio
async def test_update_user_deactivate(client: AsyncClient, admin_user, db_session):
    """Admin can deactivate a user account."""
    admin, _ = admin_user
    target, _ = await create_test_user(
        db_session, username="target_deactivate", role="operator"
    )
    headers = make_auth_header(admin)

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"is_active": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_nonexistent_user(client: AsyncClient, admin_user):
    """Updating a non-existent user returns 404."""
    user, _ = admin_user
    headers = make_auth_header(user)

    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.patch(
        f"/api/v1/users/{fake_id}",
        json={"role": "viewer"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "RESOURCE_NOT_FOUND"


# ===================================================================
# Delete User
# ===================================================================


@pytest.mark.asyncio
async def test_delete_user_as_admin(client: AsyncClient, admin_user, db_session):
    """Admin can delete a user."""
    admin, _ = admin_user
    target, _ = await create_test_user(
        db_session, username="target_delete", role="viewer"
    )
    headers = make_auth_header(admin)

    response = await client.delete(
        f"/api/v1/users/{target.id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert "deleted" in response.json()["message"]


@pytest.mark.asyncio
async def test_delete_user_as_operator_forbidden(
    client: AsyncClient, operator_user, db_session
):
    """Operator cannot delete users — 403."""
    operator, _ = operator_user
    target, _ = await create_test_user(
        db_session, username="target_nodelete", role="viewer"
    )
    headers = make_auth_header(operator)

    response = await client.delete(
        f"/api/v1/users/{target.id}",
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_user(client: AsyncClient, admin_user):
    """Deleting a non-existent user returns 404."""
    user, _ = admin_user
    headers = make_auth_header(user)

    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.delete(
        f"/api/v1/users/{fake_id}",
        headers=headers,
    )
    assert response.status_code == 404
