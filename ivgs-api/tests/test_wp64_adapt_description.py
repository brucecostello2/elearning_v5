"""
WP-64 Task 3 — the description follows the medium, explicitly and never silently.

MEASURED IN THE TREE, 2026-08-26, before a line of this was written.

A scene's `visual_description` is authored ONCE, by Stage 2, for whatever
`media_type` Stage 2 chose. After that nothing rewrites it, ever:

  * `update_scene` (`ivgs-api/app/api/v1/storyboard.py:143`) persists a
    `media_type` change with no rewrite -- `StoryboardService.update_scene` is a
    `setattr` loop over the fields the caller sent;
  * `video_generation_task._generate_video_prompt` interpolates that same
    still-authored description into the cinematographer prompt
    (`ivgs-workers/tasks/video_generation_task.py:245`);
  * `animation_generation_task._params_from_binding` hands it to Wan2.2-Animate
    verbatim as the render prompt (`:389`).

So switching a scene to video or animation dispatched the RIGHT ENGINE INTO A
FROZEN IDEA. This module gates the repair, and most of what it gates is what the
repair must NOT do: it must not write the scene row, and it must not fire while
a run holds the project.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.services import adaptation_service as svc

STILL_DESCRIPTION = (
    "The same desk and lamp; two partial-product rows already written above a "
    "second ruled line, the answer row beneath it still empty, the pencil "
    "resting at the foot of the ones column, muted blue-grey illustration style"
)

MOVING_ANSWER = (
    "The same desk and lamp, camera holding steady over the sheet; the pencil "
    "begins at the ones column and traces downward, then the answer row fills "
    "in beneath the ruled line, muted blue-grey illustration style"
)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class FakeModel:
    """Records the prompt it was given and returns what it was told to."""

    def __init__(self, content: str = MOVING_ANSWER, finish: str = "stop"):
        self.content = content
        self.finish = finish
        self.prompts: list[str] = []
        self.endpoints: list[str] = []
        self.models: list[str] = []

    async def __call__(self, prompt, *, endpoint, model):
        self.prompts.append(prompt)
        self.endpoints.append(endpoint)
        self.models.append(model)
        return {
            "content": self.content,
            "finish_reason": self.finish,
            "usage": {"total_tokens": 123},
            "model": model,
        }


def _transport(payload: dict, status: int = 200):
    """An `httpx.AsyncClient` replacement that answers one POST from `payload`.

    Used only where the code under test is `_call_model` itself. Everywhere
    else the tests replace `_call_model`, because what they are asserting is
    what the SERVICE does with an answer, not how the answer is fetched.
    """

    class _Resp:
        status_code = status
        text = "stub"

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _Resp()

    return _Client


@pytest.fixture
def fake_model():
    m = FakeModel()
    with patch.object(svc, "_call_model", m):
        yield m


@pytest.fixture
def fake_binding():
    async def _resolve(db, project_id):
        return {
            "model": "llama-3.3-70b",
            "endpoint": "http://vllm.test",
            "binding": "llama-3.3-70b-storyboard [vllm] tier=prototype",
            "model_id": str(uuid.uuid4()),
            "engine": "vllm",
        }

    with patch.object(svc, "_resolve_binding", _resolve):
        yield


@pytest_asyncio.fixture
async def adaptation_prompt(db_session):
    """The tracked template, published as the active global row."""
    from pathlib import Path

    from app.models.prompt import Prompt

    text = (
        Path(__file__).resolve().parents[1]
        / "seed" / "default_prompts" / "scene_media_adaptation.j2"
    ).read_text(encoding="utf-8").strip()
    row = Prompt(
        id=uuid.uuid4(), prompt_type="scene_media_adaptation", prompt_text=text,
        version=1, is_active=True, created_by="test",
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest_asyncio.fixture
async def scene(db_session, operator_token):
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.storyboard_scene import StoryboardScene

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="WP-64 adaptation",
        state="STORYBOARD_GENERATION", created_by=owner,
        created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    row = StoryboardScene(
        id=uuid.uuid4(), project_id=project.id, scene_index=3,
        narration_text=(
            "Now, let's add the two answers together. Add them up, and write "
            "the total on the bottom row."
        ),
        visual_description=STILL_DESCRIPTION,
        media_type="image", duration_seconds=10.0,
        created_at=now, updated_at=now,
    )
    db_session.add(row)
    await db_session.commit()
    return {"project_id": str(project.id), "scene_id": str(row.id)}


URL = "/api/v1/projects/{p}/scenes/{s}/adapt-description"


# ---------------------------------------------------------------------------
# Task 3(b) — it returns the rewrite; it NEVER writes the scene
# ---------------------------------------------------------------------------


class TestItProposesAndNeverWrites:
    async def test_it_returns_the_rewrite(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["adapted_description"] == MOVING_ANSWER
        assert body["target_media_type"] == "video_clip"
        assert body["current_media_type"] == "image"
        assert body["current_description"] == STILL_DESCRIPTION

    async def test_the_scene_row_is_byte_for_byte_unchanged(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        """THE CENTRAL ASSERTION OF THIS MODULE.

        A feature that silently replaced the operator's own words the moment
        they changed a dropdown would destroy authored intent with no diff and
        no undo. Saving is the existing PATCH, made by a human who has read the
        proposal.
        """
        from app.models.storyboard_scene import StoryboardScene

        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "animation"},
            headers=_h(operator_token),
        )
        db_session.expire_all()
        row = await db_session.scalar(
            select(StoryboardScene).where(
                StoryboardScene.id == uuid.UUID(scene["scene_id"])
            )
        )
        assert row.visual_description == STILL_DESCRIPTION
        assert row.media_type == "image"

    async def test_the_response_says_so_in_its_own_payload(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        """`scene_written` is in the body so the contract is readable from the
        response, not only from documentation."""
        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.json()["scene_written"] is False


# ---------------------------------------------------------------------------
# Task 3(a) — the model, the prompt and what reaches it
# ---------------------------------------------------------------------------


class TestWhatReachesTheModel:
    async def test_the_prompt_carries_narration_description_and_target(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        sent = fake_model.prompts[0]
        assert "Add them up" in sent, "the narration must reach the model"
        assert STILL_DESCRIPTION in sent
        assert "Target medium: video_clip" in sent

    async def test_the_model_is_the_storyboard_binding(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        """THE MODEL DOES NOT MOVE. Storyboard and transcript stay on Llama
        until M3.3 (reference-run correctness annotation section 2), and this
        resolves the same binding the worker resolves rather than naming a
        model of its own."""
        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert fake_model.models[0] == "llama-3.3-70b"

    async def test_it_refuses_under_a_prompt_that_lost_the_contract(
        self, client, operator_token, scene, db_session, fake_model, fake_binding,
    ):
        """A prompt without the no-text rule returns rewrites full of drawn
        digits, and they look exactly like good ones."""
        from app.models.prompt import Prompt

        db_session.add(Prompt(
            id=uuid.uuid4(), prompt_type="scene_media_adaptation",
            prompt_text="Rewrite {{ project_title }} {{ scene_label }} "
                        "{{ target_media_type }} {{ current_media_type }} "
                        "{{ narration_text }} {{ current_description }}",
            version=1, is_active=True, created_by="test",
        ))
        await db_session.commit()

        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 502, resp.text
        assert "contract" in resp.json()["detail"]["error"]["message"]
        assert not fake_model.prompts, "the model must not be called at all"

    async def test_no_active_prompt_is_a_refusal_not_an_improvisation(
        self, client, operator_token, scene, fake_model, fake_binding,
    ):
        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 502
        assert "no active" in resp.json()["detail"]["error"]["message"]

    async def test_a_truncated_rewrite_is_refused_not_offered(self):
        """WP-58's Stage-2 lesson. A rewrite that hit the ceiling ends
        mid-sentence and nothing in the text says so.

        Driven against the REAL `_call_model` with a stubbed transport, not
        through the route: the ceiling check lives inside `_call_model`, and a
        test that replaced that function would be asserting on its own stub.
        """
        with patch.object(svc.httpx, "AsyncClient", _transport({
            "choices": [{
                "message": {"content": "The pencil begins at the ones"},
                "finish_reason": "length",
            }],
        })):
            with pytest.raises(svc.AdaptationError) as exc:
                await svc._call_model(
                    "p", endpoint="http://vllm.test", model="llama-3.3-70b",
                )
        assert "ceiling" in str(exc.value)

    async def test_an_empty_completion_is_refused(self):
        with patch.object(svc.httpx, "AsyncClient", _transport({
            "choices": [{"message": {"content": "   "}, "finish_reason": "stop"}],
        })):
            with pytest.raises(svc.AdaptationError) as exc:
                await svc._call_model(
                    "p", endpoint="http://vllm.test", model="llama-3.3-70b",
                )
        assert "empty completion" in str(exc.value)

    async def test_a_complete_answer_comes_back(self):
        with patch.object(svc.httpx, "AsyncClient", _transport({
            "choices": [{
                "message": {"content": MOVING_ANSWER}, "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 42},
        })):
            answer = await svc._call_model(
                "p", endpoint="http://vllm.test", model="llama-3.3-70b",
            )
        assert answer["content"] == MOVING_ANSWER
        assert answer["usage"]["total_tokens"] == 42


# ---------------------------------------------------------------------------
# Task 3(c) — guarded like every dispatch-capable surface
# ---------------------------------------------------------------------------


class TestTheInFlightGuardReachesHere:
    async def test_it_refuses_409_while_a_run_holds_the_project(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        """It dispatches no stage and is guarded anyway: it consumes capacity on
        the same LLM the run is using, and it reads rows that run may be about
        to overwrite."""
        from app.models.render_job import RenderJob

        db_session.add(RenderJob(
            id=uuid.uuid4(), project_id=uuid.UUID(scene["project_id"]),
            job_type="storyboard_generation", status="running",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error"]["code"] == "PIPELINE_ALREADY_RUNNING"

    async def test_the_refusal_spends_no_model_time(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        """The guard runs BEFORE the model call, not after it."""
        from app.models.render_job import RenderJob

        db_session.add(RenderJob(
            id=uuid.uuid4(), project_id=uuid.UUID(scene["project_id"]),
            job_type="image_generation", status="pending",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert fake_model.prompts == []

    async def test_a_finished_run_does_not_block(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        from app.models.render_job import RenderJob

        db_session.add(RenderJob(
            id=uuid.uuid4(), project_id=uuid.UUID(scene["project_id"]),
            job_type="storyboard_generation", status="success",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Task 3(d) — the audit row
# ---------------------------------------------------------------------------


class TestTheAdaptationIsAudited:
    async def test_a_row_is_written_naming_both_texts(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        from app.models.audit_log import AuditLog

        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "animation"},
            headers=_h(operator_token),
        )
        rows = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.action_type == "SCENE_DESCRIPTION_ADAPTED"
            )
        )).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.resource_id == uuid.UUID(scene["scene_id"])
        assert row.before_payload["visual_description"] == STILL_DESCRIPTION
        assert row.after_payload["adapted_description"] == MOVING_ANSWER
        assert row.after_payload["target_media_type"] == "animation"
        assert row.after_payload["prompt_version"] == 1

    async def test_the_row_records_that_nothing_was_written(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        """Recorded as a fact rather than left to be inferred from the absence
        of a scene diff."""
        from app.models.audit_log import AuditLog

        await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        row = (await db_session.execute(
            select(AuditLog).where(
                AuditLog.action_type == "SCENE_DESCRIPTION_ADAPTED"
            )
        )).scalars().first()
        assert row.after_payload["scene_written"] is False


# ---------------------------------------------------------------------------
# Refusals, and the ones that must NOT be 500s
# ---------------------------------------------------------------------------


class TestRefusals:
    async def test_an_unknown_media_type_is_a_422_from_the_schema(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "TALKING_HEAD"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 422, resp.text
        assert fake_model.prompts == []

    async def test_a_missing_scene_is_404(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        resp = await client.post(
            URL.format(p=scene["project_id"], s=uuid.uuid4()),
            json={"target_media_type": "image"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 404

    async def test_a_scene_with_no_description_is_400_not_a_blank_prompt(
        self, client, operator_token, scene, adaptation_prompt,
        fake_model, fake_binding, db_session,
    ):
        from app.models.storyboard_scene import StoryboardScene

        row = await db_session.scalar(
            select(StoryboardScene).where(
                StoryboardScene.id == uuid.UUID(scene["scene_id"])
            )
        )
        row.visual_description = ""
        await db_session.commit()

        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 400
        assert fake_model.prompts == []

    async def test_a_viewer_cannot_adapt(
        self, client, viewer_token, scene, adaptation_prompt,
        fake_model, fake_binding,
    ):
        resp = await client.post(
            URL.format(p=scene["project_id"], s=scene["scene_id"]),
            json={"target_media_type": "video_clip"},
            headers=_h(viewer_token),
        )
        assert resp.status_code == 403
        assert fake_model.prompts == []


# ---------------------------------------------------------------------------
# The output cleaner — formatting only, never content
# ---------------------------------------------------------------------------


class TestTheOutputCleaner:
    def test_it_removes_a_chat_preamble(self):
        assert svc.clean_output(
            "Here is the rewritten description: the pencil traces downward"
        ) == "the pencil traces downward"

    def test_it_removes_a_code_fence(self):
        assert svc.clean_output(
            "```\nthe pencil traces downward\n```"
        ) == "the pencil traces downward"

    def test_it_removes_wrapping_quotes(self):
        assert svc.clean_output('"the pencil traces downward"') == (
            "the pencil traces downward"
        )

    def test_it_leaves_ordinary_prose_alone(self):
        """Conservative on purpose: an over-eager cleaner that ate a sentence
        would be a silent content edit, which is the class of defect this whole
        module exists to avoid."""
        text = (
            'The pencil begins at the "ones" column and traces downward, then '
            "the answer row fills in."
        )
        assert svc.clean_output(text) == text

    def test_it_does_not_strip_an_internal_quotation(self):
        text = 'The presenter says "carry the one" as the hand moves.'
        assert svc.clean_output(text) == text
