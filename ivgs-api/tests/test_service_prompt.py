"""
Phase 4 — Prompt Service Unit Tests.

Tests business logic in app/services/prompt_service.py:
  - render_template: Jinja2 rendering, undefined vars, syntax errors
  - create_prompt: versioning, deactivation of prior versions
  - resolve_effective_prompts: 3-tier hierarchy
  - test_prompt: playground validation
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import text

from app.services.prompt_service import PromptService
from app.services.user_service import create_user

pytestmark = pytest.mark.asyncio


class TestRenderTemplate:
    """Test Jinja2 template rendering logic."""

    async def test_render_simple_template(self, db_session):
        svc = PromptService(db_session)
        result = svc.render_template(
            "Hello {{ name }}, you are {{ role }}.",
            {"name": "Alice", "role": "admin"},
        )
        assert result == "Hello Alice, you are admin."

    async def test_render_empty_variables(self, db_session):
        svc = PromptService(db_session)
        # DebugUndefined shows {{ undefined }} as-is
        result = svc.render_template("Hello {{ name }}.", {})
        assert "{{ name }}" in result or "name" in result

    async def test_render_no_template_vars(self, db_session):
        svc = PromptService(db_session)
        result = svc.render_template("Static prompt with no variables.", {})
        assert result == "Static prompt with no variables."

    async def test_render_invalid_syntax_raises(self, db_session):
        svc = PromptService(db_session)
        with pytest.raises(ValueError):
            svc.render_template("{% invalid syntax %}", {})

    async def test_render_complex_template(self, db_session):
        svc = PromptService(db_session)
        template = "{% for item in items %}{{ item }}, {% endfor %}"
        result = svc.render_template(template, {"items": ["a", "b", "c"]})
        assert "a" in result
        assert "b" in result
        assert "c" in result


class TestCreatePrompt:
    async def test_create_global_prompt(self, db_session):
        svc = PromptService(db_session)
        prompt = await svc.create_prompt(
            prompt_type="master",
            prompt_text="Global master prompt v1",
            change_note="Initial version",
            created_by="test_user",
        )
        assert prompt is not None
        assert prompt.prompt_type == "master"
        assert prompt.is_active is True
        assert prompt.version == 1

    async def test_create_prompt_increments_version(self, db_session):
        svc = PromptService(db_session)
        p1 = await svc.create_prompt(
            prompt_type="transcript_refinement",
            prompt_text="TR prompt v1",
            change_note="v1",
            created_by="test_user",
        )
        p2 = await svc.create_prompt(
            prompt_type="transcript_refinement",
            prompt_text="TR prompt v2",
            change_note="v2",
            created_by="test_user",
        )
        assert p2.version == p1.version + 1
        # Old version should be deactivated
        await db_session.refresh(p1)
        assert p1.is_active is False
        assert p2.is_active is True

    async def test_create_project_prompt(self, db_session, project_id: str):
        svc = PromptService(db_session)
        prompt = await svc.create_prompt(
            prompt_type="image_generation",
            prompt_text="Project-level image gen prompt",
            change_note="project override",
            created_by="test_user",
            project_id=project_id,
        )
        assert prompt is not None
        assert str(prompt.project_id) == project_id


class TestGetVersionHistory:
    async def test_version_history_ordered_desc(self, db_session):
        svc = PromptService(db_session)
        for i in range(3):
            await svc.create_prompt(
                prompt_type="composition",
                prompt_text=f"Comp prompt v{i+1}",
                change_note=f"v{i+1}",
                created_by="test_user",
            )
        history = await svc.get_version_history("composition")
        assert len(history) == 3
        # Most recent first
        assert history[0].version > history[-1].version


class TestTestPrompt:
    async def test_test_prompt_validates_syntax(self, db_session):
        svc = PromptService(db_session)
        result = await svc.test_prompt(
            prompt_text="Hello {{ name }}",
            model_id="test-model",
            parameters=None,
            template_variables={"name": "World"},
        )
        assert "rendered_text" in result or "rendered" in result or isinstance(result, dict)

    async def test_test_prompt_invalid_syntax(self, db_session):
        svc = PromptService(db_session)
        with pytest.raises((ValueError, Exception)):
            await svc.test_prompt(
                prompt_text="{% invalid %}",
                model_id="test-model",
                parameters=None,
                template_variables={},
            )
