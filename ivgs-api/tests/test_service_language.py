"""
Phase 4 — Language Service Unit Tests.

Tests business logic in app/services/language_service.py:
  - list_variants: ordered by language_code
  - create_variant: duplicate detection, state initialization
  - get_variant: found/not found
  - retry_variant: state validation (only from 'failed')
"""

import pytest
from uuid import uuid4

from app.services.language_service import LanguageService

pytestmark = pytest.mark.asyncio


class TestListVariants:
    async def test_list_variants_empty(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        variants = await svc.list_variants(project_id)
        assert isinstance(variants, list)

    async def test_list_variants_ordered(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        await svc.create_variant(project_id, "fr-FR")
        await svc.create_variant(project_id, "de-DE")
        await svc.create_variant(project_id, "ar-SA")
        variants = await svc.list_variants(project_id)
        codes = [v.language_code for v in variants]
        assert codes == sorted(codes)


class TestCreateVariant:
    async def test_create_variant_success(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        variant = await svc.create_variant(project_id, "es-ES")
        assert variant.language_code == "es-ES"
        assert variant.state == "pending"
        assert variant.project_id is not None

    async def test_create_variant_duplicate_raises(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        await svc.create_variant(project_id, "ja-JP")
        with pytest.raises((ValueError, Exception)):
            await svc.create_variant(project_id, "ja-JP")

    async def test_create_variant_with_prompt_override(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        variant = await svc.create_variant(
            project_id, "zh-CN", translation_prompt_override="Use formal Chinese"
        )
        assert variant.language_code == "zh-CN"


class TestGetVariant:
    async def test_get_variant_found(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        created = await svc.create_variant(project_id, "en-GB")
        found = await svc.get_variant(project_id, created.id)
        assert found is not None
        assert found.language_code == "en-GB"

    async def test_get_variant_not_found(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        found = await svc.get_variant(project_id, uuid4())
        assert found is None

    async def test_get_variant_wrong_project(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        created = await svc.create_variant(project_id, "en-US")
        found = await svc.get_variant(uuid4(), created.id)
        assert found is None


class TestRetryVariant:
    async def test_retry_pending_variant_raises(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        variant = await svc.create_variant(project_id, "fr-FR")
        # Retry on pending should fail (only from 'failed')
        with pytest.raises((ValueError, Exception)):
            await svc.retry_variant(project_id, variant.id)

    async def test_retry_nonexistent_variant(self, db_session, project_id: str):
        svc = LanguageService(db_session)
        result = await svc.retry_variant(project_id, uuid4())
        assert result is None
