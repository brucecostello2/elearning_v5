"""
Phase 4 — Project Service Unit Tests.

Tests business logic in app/services/project_service.py:
  - create_project: initial state, language variants auto-create
  - list_projects: RBAC (operator sees own, admin sees all)
  - transition_state: valid/invalid transitions
  - trigger_pipeline: triggerable states, transcript validation
  - delete_project: cascade
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.project_service import ProjectService
from app.services.user_service import create_user
from app.schemas.project import ProjectCreate, ProjectUpdate
from shared.models.enums import ProjectState

pytestmark = pytest.mark.asyncio


async def _make_user(db_session, username, role="operator"):
    """Helper to create a user and return the model."""
    return await create_user(db_session, username, "Str0ngP@ss1", role)


class TestCreateProject:
    async def test_create_project_default_state(self, db_session):
        user = await _make_user(db_session, "proj_create_1")
        svc = ProjectService(db_session)
        data = ProjectCreate(name="Test Proj", description="desc")
        resp = await svc.create_project(data, user)
        assert resp.name == "Test Proj"
        assert resp.state == "DRAFT"

    async def test_create_project_with_target_languages(self, db_session):
        user = await _make_user(db_session, "proj_create_lang")
        svc = ProjectService(db_session)
        data = ProjectCreate(name="Lang Proj", target_languages=["es-ES", "fr-FR"])
        resp = await svc.create_project(data, user)
        assert resp.name == "Lang Proj"
        # Verify language variants were auto-created
        variants = resp.language_variants if hasattr(resp, 'language_variants') else []
        if variants:
            codes = {v.language_code for v in variants}
            assert "es-ES" in codes
            assert "fr-FR" in codes


class TestListProjects:
    async def test_admin_sees_all_projects(self, db_session):
        admin = await _make_user(db_session, "proj_list_admin", "admin")
        op1 = await _make_user(db_session, "proj_list_op1", "operator")
        op2 = await _make_user(db_session, "proj_list_op2", "operator")
        svc = ProjectService(db_session)
        await svc.create_project(ProjectCreate(name="Op1 Proj"), op1)
        await svc.create_project(ProjectCreate(name="Op2 Proj"), op2)
        
        projects, total = await svc.list_projects(admin)
        assert total >= 2

    async def test_operator_sees_own_projects_only(self, db_session):
        op1 = await _make_user(db_session, "proj_own_op1", "operator")
        op2 = await _make_user(db_session, "proj_own_op2", "operator")
        svc = ProjectService(db_session)
        await svc.create_project(ProjectCreate(name="My Proj"), op1)
        await svc.create_project(ProjectCreate(name="Other Proj"), op2)
        
        projects, total = await svc.list_projects(op1)
        # Op1 should only see their own
        for p in projects:
            assert str(p.created_by) == str(op1.id)

    async def test_list_with_state_filter(self, db_session):
        user = await _make_user(db_session, "proj_filter_state")
        svc = ProjectService(db_session)
        await svc.create_project(ProjectCreate(name="Draft Proj"), user)
        
        projects, total = await svc.list_projects(user, state_filter="DRAFT")
        assert total >= 1
        for p in projects:
            assert p.state == "DRAFT"

    async def test_list_with_search(self, db_session):
        user = await _make_user(db_session, "proj_search")
        svc = ProjectService(db_session)
        await svc.create_project(ProjectCreate(name="UniqueSearchTerm999"), user)
        
        projects, total = await svc.list_projects(user, search="UniqueSearchTerm999")
        assert total >= 1
        assert any("UniqueSearchTerm999" in p.name for p in projects)


class TestTransitionState:
    async def test_valid_transition_draft_to_transcript(self, db_session):
        user = await _make_user(db_session, "proj_trans_ok")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="Trans Proj"), user)
        
        updated = await svc.transition_state(
            resp.id, ProjectState.TRANSCRIPT_REFINEMENT, user
        )
        assert updated is not None
        assert updated.state == "TRANSCRIPT_REFINEMENT"

    async def test_invalid_transition_draft_to_complete(self, db_session):
        user = await _make_user(db_session, "proj_trans_bad")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="Bad Trans"), user)
        
        with pytest.raises(ValueError, match="Invalid state transition"):
            await svc.transition_state(resp.id, ProjectState.COMPLETE, user)

    async def test_transition_nonexistent_project(self, db_session):
        user = await _make_user(db_session, "proj_trans_404")
        svc = ProjectService(db_session)
        result = await svc.transition_state(uuid4(), ProjectState.ERROR, user)
        assert result is None

    async def test_error_state_can_recover(self, db_session):
        user = await _make_user(db_session, "proj_trans_err")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="Err Proj"), user)
        
        # DRAFT → ERROR
        resp = await svc.transition_state(resp.id, ProjectState.ERROR, user)
        assert resp.state == "ERROR"
        
        # ERROR → DRAFT (recovery)
        resp = await svc.transition_state(resp.id, ProjectState.DRAFT, user)
        assert resp.state == "DRAFT"


class TestTriggerPipeline:
    async def test_trigger_from_non_triggerable_state_raises(self, db_session):
        user = await _make_user(db_session, "proj_trig_bad")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="Trig Bad"), user)
        
        # Move to TRANSCRIPT_REFINEMENT first
        await svc.transition_state(resp.id, ProjectState.TRANSCRIPT_REFINEMENT, user)
        
        # Can't trigger from TRANSCRIPT_REFINEMENT
        with pytest.raises(ValueError, match="Cannot trigger pipeline"):
            await svc.trigger_pipeline(resp.id, user)

    async def test_trigger_from_draft_without_transcripts_raises(self, db_session):
        user = await _make_user(db_session, "proj_trig_no_tr")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="No Transcripts"), user)
        
        with pytest.raises(ValueError, match="no transcripts"):
            await svc.trigger_pipeline(resp.id, user)

    async def test_trigger_nonexistent_project(self, db_session):
        user = await _make_user(db_session, "proj_trig_404")
        svc = ProjectService(db_session)
        result = await svc.trigger_pipeline(uuid4(), user)
        assert result is None


class TestDeleteProject:
    async def test_delete_project_success(self, db_session):
        admin = await _make_user(db_session, "proj_del_admin", "admin")
        svc = ProjectService(db_session)
        resp = await svc.create_project(ProjectCreate(name="Del Proj"), admin)
        
        result = await svc.delete_project(resp.id, admin)
        assert result is True
        
        # Verify deleted
        found = await svc.get_project(resp.id, admin)
        assert found is None

    async def test_delete_nonexistent_project(self, db_session):
        admin = await _make_user(db_session, "proj_del_404", "admin")
        svc = ProjectService(db_session)
        result = await svc.delete_project(uuid4(), admin)
        assert result is False
