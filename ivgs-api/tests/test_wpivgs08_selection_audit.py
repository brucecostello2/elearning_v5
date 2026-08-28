"""WP-IVGS-08 Task 5 — a preset changed model bindings with no audit trail.

WP-66 measured it: the selection ROUTE wrote `audit_log`; the service layer did
not. Two callers reach `manual_override` and only the route audited, so
`PresetService.apply_to_project` rebound a project's models invisibly.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services import model_selection
from shared.models.model_store import (
    Model, ModelEngine, ModelStage, ModelState, ModelTier,
)

pytestmark = pytest.mark.asyncio


async def _user(db):
    from app.models.user import User
    u = User(username=f"wpivgs08-{uuid.uuid4().hex[:8]}", password_hash="x", role="admin")
    db.add(u); await db.commit(); await db.refresh(u)
    return u.id


async def _project(db):
    from app.models.project import Project
    pr = Project(name=f"wpivgs08-audit-{uuid.uuid4().hex[:6]}", state="DRAFT")
    db.add(pr); await db.commit(); await db.refresh(pr)
    return pr.id


async def _model(db, name, stage=ModelStage.IMAGE_GENERATION):
    m = Model(name=name, display_name=name, stage=stage,
              engine=ModelEngine.COMFYUI, tier=ModelTier.BOTH,
              state=ModelState.APPROVED, enabled=True)
    db.add(m); await db.commit(); await db.refresh(m)
    return m


class TestTheServiceLayerAuditsWhatItWrites:
    async def test_a_service_level_selection_write_produces_an_audit_row(
        self, db_session
    ):
        """THE DEFECT. Called with no route in sight -- exactly how the preset
        path reaches it."""
        project_id = await _project(db_session)
        m = await _model(db_session, f"flux-wpivgs08-a-{uuid.uuid4().hex[:6]}")
        actor = await _user(db_session)

        await model_selection.manual_override(
            db_session, project_id=project_id, scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PROTOTYPE,
            model_id=m.id, rationale="preset 'house style' v3",
            actor_user_id=actor,
        )
        await db_session.commit()

        rows = (await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == project_id)
        )).scalars().all()
        assert len(rows) == 1, "the service write must produce exactly one row"
        r = rows[0]
        assert r.action_type == "MODEL_SELECTION_SET"
        assert r.user_id == actor
        assert r.after_payload["model"] == m.name
        assert r.after_payload["rationale"] == "preset 'house style' v3"

    async def test_the_row_names_what_it_REPLACED(self, db_session):
        """An audit that says only what a binding became cannot answer 'what
        changed?' -- which is the question it exists for."""
        project_id = await _project(db_session)
        first = await _model(db_session, f"flux-wpivgs08-b1-{uuid.uuid4().hex[:6]}")
        second = await _model(db_session, f"flux-wpivgs08-b2-{uuid.uuid4().hex[:6]}")
        for m in (first, second):
            await model_selection.manual_override(
                db_session, project_id=project_id, scene_id=None,
                stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PROTOTYPE,
                model_id=m.id, rationale="r",
            )
        await db_session.commit()

        rows = (await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == project_id)
            .order_by(AuditLog.timestamp)
        )).scalars().all()
        assert len(rows) == 2
        assert rows[0].before_payload["previous_model"] is None
        assert rows[1].before_payload["previous_model"] == first.name
        assert rows[1].after_payload["model"] == second.name

    async def test_a_null_actor_is_recorded_not_refused(self, db_session):
        """`audit_log.user_id` is nullable. A background preset application
        records a NULL actor -- still infinitely better than no row."""
        project_id = await _project(db_session)
        m = await _model(db_session, f"flux-wpivgs08-c-{uuid.uuid4().hex[:6]}")
        await model_selection.manual_override(
            db_session, project_id=project_id, scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PROTOTYPE,
            model_id=m.id, rationale="r",
        )
        await db_session.commit()
        row = (await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == project_id)
        )).scalar_one()
        assert row.user_id is None

    async def test_the_route_no_longer_duplicates_the_event(self):
        """Pinned against the source: two writers would double-count every
        route selection and leave two definitions of the payload."""
        from pathlib import Path
        import app.api.v1.model_store as ms
        assert "MODEL_SELECTION_SET" not in Path(ms.__file__).read_text()
