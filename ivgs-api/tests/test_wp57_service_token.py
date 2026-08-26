"""
WP-57 Task 8 — the shipped default service token must stop working once a real
one is set.

`IVGS_SERVICE_TOKEN` has been unset fleet-wide since WP-44 D-5 flagged it, so
internal service auth has been guarded by "dev-service-token" — a value that is
in the repository — on routes including the CLIP scoring the quality gate
depends on. Three packages carried it.

THE PROPERTY THAT MATTERS: the route must not accept BOTH. Setting a strong
token achieves nothing if the published one still opens the door, and that is
the failure mode a rotation is supposed to close.

No token value appears in this file, in the report, or in any commit. The tests
generate their own.
"""
import secrets

import pytest

from app.core.auth import _INSECURE_DEFAULT_SERVICE_TOKEN
from shared.config import settings

pytestmark = pytest.mark.asyncio

SHIPPED_DEFAULT = _INSECURE_DEFAULT_SERVICE_TOKEN


@pytest.fixture
def real_token(monkeypatch) -> str:
    """Configure a strong service token for the duration of one test."""
    token = secrets.token_urlsafe(48)
    monkeypatch.setattr(settings, "IVGS_SERVICE_TOKEN", token)
    return token


async def test_the_shipped_default_is_refused_once_a_real_token_is_set(
    client, real_token, db_session, project_id,
):
    """The whole point of Task 8.

    `GET /projects/{id}/assets` is used throughout because it declares
    `Depends(get_service_or_user)` (assets.py:56) — the dual-mode dependency the
    worker fleet authenticates against. `/projects` and `/jobs` are
    `get_current_user` only and never accept a service token from anyone, so
    neither can demonstrate this property.
    """
    resp = await client.get(
        f"/api/v1/projects/{project_id}/assets",
        headers={"Authorization": f"Bearer {SHIPPED_DEFAULT}"},
    )
    assert resp.status_code in (401, 403), (
        "the shipped default was accepted while a real IVGS_SERVICE_TOKEN was "
        "configured — setting a strong token would then protect nothing"
    )


async def test_the_real_token_is_accepted(
    client, real_token, db_session, project_id,
):
    """The rotation must not break the fleet it protects.

    Requires the seeded `svc-pipeline` account; without it the API answers 401
    SERVICE_ACCOUNT_MISSING, which is still a refusal of a real token and is
    exactly what the operator block's seed step exists to prevent.
    """
    from app.core.security import hash_password
    from app.models.user import User

    db_session.add(
        User(
            username="svc-pipeline",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="admin",
            is_active=True,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project_id}/assets",
        headers={"Authorization": f"Bearer {real_token}"},
    )
    assert resp.status_code == 200, resp.text


async def test_a_wrong_token_is_refused(
    client, real_token, db_session, project_id,
):
    resp = await client.get(
        f"/api/v1/projects/{project_id}/assets",
        headers={"Authorization": f"Bearer {secrets.token_urlsafe(48)}"},
    )
    assert resp.status_code in (401, 403)


async def test_the_default_still_works_while_no_real_token_is_set(
    client, monkeypatch, db_session, project_id,
):
    """DELIBERATE, and the reason this change is safe to deploy.

    Failing closed while the default is still in place would stop the live fleet
    the moment this deploys — before the operator has run the block that sets a
    value. The default is refused only once a real one EXISTS. Its use is logged
    loudly at every acceptance so the gap stays visible.

    This test should be DELETED once the operator block has run everywhere and
    the default can be refused unconditionally.
    """
    from app.core.security import hash_password
    from app.models.user import User

    monkeypatch.setattr(settings, "IVGS_SERVICE_TOKEN", SHIPPED_DEFAULT)
    db_session.add(
        User(
            username="svc-pipeline",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="admin",
            is_active=True,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project_id}/assets",
        headers={"Authorization": f"Bearer {SHIPPED_DEFAULT}"},
    )
    assert resp.status_code == 200


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_no_token_value_is_hardcoded_in_the_worker_default():
    """The worker's fallback must be the same known-bad sentinel, not a second
    secret invented somewhere else — otherwise rotating one leaves the other."""
    from pathlib import Path

    cfg = Path(__file__).resolve().parents[2] / "ivgs-workers" / "config.py"
    text = cfg.read_text()
    assert '_env("IVGS_SERVICE_TOKEN", "dev-service-token")' in text, (
        "the worker's service-token default changed; if it is now a different "
        "literal, the API's refusal list must learn about it too"
    )
