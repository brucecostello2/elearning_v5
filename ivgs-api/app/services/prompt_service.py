"""
Prompt service: 3-tier hierarchy resolution, Jinja2 rendering, versioning.

Per §9.1–9.4:
- Resolution order: Scene → Project → Global (first active match)
- Every edit creates a new version; is_active toggled
- Jinja2 template rendering with project/scene context variables
- Prompt Playground test stub (real vLLM call in Phase 5)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.schemas.prompt import EffectivePrompt

logger = logging.getLogger(__name__)

# Jinja2 environment for prompt template rendering
jinja_env = Environment(
    loader=BaseLoader(),
    undefined=__import__("jinja2").DebugUndefined,
    autoescape=False,
)

# Template variables available per §9.4
TEMPLATE_VARIABLES = {
    "project_title",
    "project_description",
    "target_audience",
    "scene_number",
    "scene_title",
    "narration_text",
    "visual_description",
    "target_language",
    "max_duration_seconds",
    "total_runtime_seconds",
}


class PromptService:
    """Business logic for prompt management with 3-tier hierarchy."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_global_prompts(
        self,
        prompt_type: Optional[str] = None,
    ) -> List[Prompt]:
        """List global prompts (project_id IS NULL, scene_id IS NULL)."""
        query = select(Prompt).where(
            Prompt.project_id.is_(None),
            Prompt.scene_id.is_(None),
        )
        if prompt_type:
            query = query.where(Prompt.prompt_type == prompt_type)
        query = query.order_by(Prompt.prompt_type, Prompt.version.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_project_prompts(
        self,
        project_id: UUID,
        prompt_type: Optional[str] = None,
    ) -> List[Prompt]:
        """List project-level prompts."""
        query = select(Prompt).where(
            Prompt.project_id == project_id,
            Prompt.scene_id.is_(None),
        )
        if prompt_type:
            query = query.where(Prompt.prompt_type == prompt_type)
        query = query.order_by(Prompt.prompt_type, Prompt.version.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def resolve_effective_prompts(
        self,
        project_id: UUID,
        scene_id: Optional[UUID] = None,
    ) -> List[EffectivePrompt]:
        """
        Resolve effective prompts for all 10 types using 3-tier hierarchy.

        Resolution order per §9.1: Scene → Project → Global.
        Returns one EffectivePrompt per prompt_type showing which tier it resolved from.
        """
        from shared.models.enums import PromptType

        effective = []
        for pt in PromptType:
            prompt = await self._resolve_single(project_id, scene_id, pt.value)
            if prompt:
                effective.append(
                    EffectivePrompt(
                        prompt_type=pt.value,
                        prompt_id=prompt.id,
                        prompt_text=prompt.prompt_text,
                        version=prompt.version,
                        source=prompt.scope,
                        scene_id=prompt.scene_id,
                    )
                )
        return effective

    async def _resolve_single(
        self,
        project_id: UUID,
        scene_id: Optional[UUID],
        prompt_type: str,
    ) -> Optional[Prompt]:
        """
        Resolve a single prompt_type through the 3-tier hierarchy.

        1. Scene-level (if scene_id provided): active prompt for this type+scene
        2. Project-level: active prompt for this type+project
        3. Global: active prompt for this type with no project/scene
        """
        # Tier 1: Scene-level
        if scene_id:
            result = await self.db.execute(
                select(Prompt).where(
                    Prompt.prompt_type == prompt_type,
                    Prompt.project_id == project_id,
                    Prompt.scene_id == scene_id,
                    Prompt.is_active.is_(True),
                )
            )
            prompt = result.scalar_one_or_none()
            if prompt:
                return prompt

        # Tier 2: Project-level
        result = await self.db.execute(
            select(Prompt).where(
                Prompt.prompt_type == prompt_type,
                Prompt.project_id == project_id,
                Prompt.scene_id.is_(None),
                Prompt.is_active.is_(True),
            )
        )
        prompt = result.scalar_one_or_none()
        if prompt:
            return prompt

        # Tier 3: Global
        result = await self.db.execute(
            select(Prompt).where(
                Prompt.prompt_type == prompt_type,
                Prompt.project_id.is_(None),
                Prompt.scene_id.is_(None),
                Prompt.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_prompt(
        self,
        prompt_type: str,
        prompt_text: str,
        change_note: str,
        created_by: str,
        project_id: Optional[UUID] = None,
        scene_id: Optional[UUID] = None,
    ) -> Prompt:
        """
        Create a new prompt version.

        Steps:
        1. Get current max version for this type+scope
        2. Deactivate all existing active versions for this type+scope
        3. Create new version with is_active=True
        """
        # Determine scope filter
        scope_filter = [Prompt.prompt_type == prompt_type]
        if scene_id:
            scope_filter.append(Prompt.scene_id == scene_id)
            scope_filter.append(Prompt.project_id == project_id)
        elif project_id:
            scope_filter.append(Prompt.project_id == project_id)
            scope_filter.append(Prompt.scene_id.is_(None))
        else:
            scope_filter.append(Prompt.project_id.is_(None))
            scope_filter.append(Prompt.scene_id.is_(None))

        # Get max version
        max_version_result = await self.db.execute(
            select(func.max(Prompt.version)).where(*scope_filter)
        )
        max_version = max_version_result.scalar() or 0

        # Deactivate existing active versions for this type+scope
        await self.db.execute(
            update(Prompt)
            .where(*scope_filter, Prompt.is_active.is_(True))
            .values(is_active=False)
        )

        # Create new version
        prompt = Prompt(
            project_id=project_id,
            scene_id=scene_id,
            prompt_type=prompt_type,
            prompt_text=prompt_text,
            version=max_version + 1,
            is_active=True,
            created_by=created_by,
            change_note=change_note,
        )
        self.db.add(prompt)
        await self.db.commit()
        await self.db.refresh(prompt)

        logger.info(
            f"Prompt created: type={prompt_type} scope={prompt.scope} "
            f"version={prompt.version} by={created_by}"
        )
        return prompt

    async def restore_version(
        self,
        prompt_id: UUID,
    ) -> Optional[Prompt]:
        """
        Restore a previous prompt version — set is_active=True for that version.

        Deactivates the currently active version for the same type+scope.
        """
        result = await self.db.execute(
            select(Prompt).where(Prompt.id == prompt_id)
        )
        prompt = result.scalar_one_or_none()
        if prompt is None:
            return None

        # Build scope filter
        scope_filter = [Prompt.prompt_type == prompt.prompt_type]
        if prompt.scene_id:
            scope_filter.append(Prompt.scene_id == prompt.scene_id)
            scope_filter.append(Prompt.project_id == prompt.project_id)
        elif prompt.project_id:
            scope_filter.append(Prompt.project_id == prompt.project_id)
            scope_filter.append(Prompt.scene_id.is_(None))
        else:
            scope_filter.append(Prompt.project_id.is_(None))
            scope_filter.append(Prompt.scene_id.is_(None))

        # Deactivate current active version
        await self.db.execute(
            update(Prompt)
            .where(*scope_filter, Prompt.is_active.is_(True))
            .values(is_active=False)
        )

        # Activate the requested version
        prompt.is_active = True
        await self.db.commit()
        await self.db.refresh(prompt)

        logger.info(
            f"Prompt version restored: id={prompt_id} type={prompt.prompt_type} "
            f"version={prompt.version}"
        )
        return prompt

    async def get_version_history(
        self,
        prompt_type: str,
        project_id: Optional[UUID] = None,
        scene_id: Optional[UUID] = None,
    ) -> List[Prompt]:
        """Get version history for a prompt type+scope."""
        scope_filter = [Prompt.prompt_type == prompt_type]
        if scene_id:
            scope_filter.append(Prompt.scene_id == scene_id)
            scope_filter.append(Prompt.project_id == project_id)
        elif project_id:
            scope_filter.append(Prompt.project_id == project_id)
            scope_filter.append(Prompt.scene_id.is_(None))
        else:
            scope_filter.append(Prompt.project_id.is_(None))
            scope_filter.append(Prompt.scene_id.is_(None))

        result = await self.db.execute(
            select(Prompt)
            .where(*scope_filter)
            .order_by(Prompt.version.desc())
        )
        return list(result.scalars().all())

    def render_template(
        self,
        prompt_text: str,
        variables: Dict[str, str],
    ) -> str:
        """
        Render a Jinja2 prompt template with provided variables.

        Variables per §9.4: project_title, project_description, target_audience,
        scene_number, scene_title, narration_text, visual_description,
        target_language, max_duration_seconds, total_runtime_seconds.
        """
        try:
            template = jinja_env.from_string(prompt_text)
            return template.render(**variables)
        except TemplateSyntaxError as e:
            raise ValueError(f"Jinja2 syntax error in prompt: {e}")
        except UndefinedError as e:
            raise ValueError(f"Undefined variable in prompt: {e}")

    async def test_prompt(
        self,
        prompt_text: str,
        model_id: str,
        parameters: Optional[Dict] = None,
        template_variables: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Prompt Playground: test a prompt against a self-hosted model.

        Phase 3 stub: returns rendered prompt and a placeholder response.
        Phase 5: will call vLLM/Ollama through LLMProvider interface.
        """
        # Render template if variables provided
        rendered = prompt_text
        if template_variables:
            rendered = self.render_template(prompt_text, template_variables)

        # Stub response — real vLLM call in Phase 5
        logger.info(f"Prompt Playground test: model={model_id} prompt_length={len(rendered)}")
        return {
            "rendered_prompt": rendered,
            "model_id": model_id,
            "model_response": (
                "[Phase 3 stub] This is a placeholder response. "
                "In Phase 5, this will call the self-hosted vLLM/Ollama model. "
                f"Model requested: {model_id}. "
                f"Prompt length: {len(rendered)} chars."
            ),
            "usage": {
                "prompt_tokens": len(rendered.split()),
                "completion_tokens": 0,
                "total_tokens": len(rendered.split()),
            },
        }
