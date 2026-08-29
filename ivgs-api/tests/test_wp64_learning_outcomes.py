"""
WP-64 Task 6 — the storyboard model could not reason from the learning outcomes
because the project never carried them.

MEASURED, 2026-08-26. Everything the project hands Stage 2 is assembled in
`_build_stage_input` and rendered by `stage2_storyboard._render_user_prompt`
(`ivgs-workers/tasks/stage2_storyboard.py:127-137`), which passes NINE named
variables: project_title, project_description, target_audience,
max_duration_seconds, total_runtime_seconds, combined_transcript,
transcript_count, target_scene_count, language_code. "What should the viewer be
able to do at the end" is not among them and was nowhere in the system, so no
wording of the prompt could make the model reason from it.

TASK 6(c), AND WHICH BRANCH WAS TAKEN. That render call is inside one of the
eight stage task bodies AD-05 section 8 freezes, so a tenth variable cannot be
added. `project_description` IS one of the nine, and the ORCHESTRATOR
(`pipeline_orchestrator_v2.py`, not a stage body) is where the storyboard
stage's input is composed. So the outcomes travel as their own key from the API
to the orchestrator and are folded into `project_description` there, between two
explicit delimiter lines, FOR THE STORYBOARD BRANCH ONLY. The real fix -- a
`learning_outcomes` template variable -- is ledgered P2.65b/P2.66.

⛔ **SUPERSEDED IN PART BY WP-IVGS-12, 2026-08-29 — P2.66 IS CLOSED AND THE
FOLD IS RETIRED.** The paragraph above describes the FALLBACK and it was
accurate while the fallback was the carrier. It is no longer the carrier.

⛳ The cage was only ever on the USER template. `_resolve_prompts`
(`stage2_storyboard.py:86-111`) reads `task_input.system_prompt` FIRST and falls
back to its `.j2`; `_resolve_prompts_from_api` returns `(None, user_text)` by
construction so the API branch never overrides it; and
`StoryboardGenerationInput.system_prompt` is filled by `_build_stage_input`,
which is NOT a frozen body and set neither prompt field. So migration 0047 gives
the SYSTEM prompt its own version lineage and the orchestrator renders it with
`learning_outcomes` as a first-class Jinja variable. No frozen edit was needed
and none was made.

**These tests are RE-AIMED, NOT WEAKENED.** They still gate the same three
risks, at the new path: the field must reach the dispatch (unchanged, and those
tests are untouched); the outcomes must reach the MODEL (now asserted through
the rendered system prompt instead of through a delimiter); and the frozen
render call must still be untouched — that assertion is unchanged and is now
worth MORE, because it is the proof this package took the wrapper rather than
the edit.
"""
from __future__ import annotations

import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

REPO = pathlib.Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO / "ivgs-workers" / "tasks" / "pipeline_orchestrator_v2.py"
TEMPLATE = (
    REPO / "ivgs-api" / "seed" / "default_prompts" / "storyboard_generation.j2"
)

OUTCOMES = (
    "By the end, the viewer can follow the carrying step as it happens.\n"
    "By the end, the viewer can name the place value of each column."
)


class Broker:
    def __init__(self):
        self.sent: list[dict] = []
        self.control = MagicMock()

    def send_task(self, name, args=None, kwargs=None, queue=None, **_ignored):
        self.sent.append({"name": name, "kwargs": kwargs, "queue": queue})
        result = MagicMock()
        result.id = f"celery-{len(self.sent)}"
        return result


@pytest.fixture
def broker():
    b = Broker()
    with patch("app.services.celery_producer.celery_app", b):
        yield b


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Task 6(a) — the column, and what create/update do with it
# ---------------------------------------------------------------------------


class TestTheProjectCarriesItsOutcomes:
    async def test_create_persists_them(self, client, operator_token):
        resp = await client.post(
            "/api/v1/projects",
            json={
                "name": "WP-64 outcomes",
                "max_runtime_seconds": 300,
                "learning_outcomes": OUTCOMES,
            },
            headers=_h(operator_token),
        )
        assert resp.status_code in (200, 201), resp.text
        assert resp.json()["learning_outcomes"] == OUTCOMES

    async def test_they_are_optional(self, client, operator_token):
        """A project without them is not a defect and must not be one."""
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "no outcomes", "max_runtime_seconds": 300},
            headers=_h(operator_token),
        )
        assert resp.status_code in (200, 201), resp.text
        assert resp.json()["learning_outcomes"] is None

    async def test_they_are_editable_afterwards(
        self, client, operator_token, project_id,
    ):
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"learning_outcomes": OUTCOMES},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["learning_outcomes"] == OUTCOMES

    async def test_they_can_be_cleared(
        self, client, operator_token, project_id,
    ):
        """An empty box means "there are none", which is a real answer."""
        await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"learning_outcomes": OUTCOMES},
            headers=_h(operator_token),
        )
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"learning_outcomes": None},
            headers=_h(operator_token),
        )
        assert resp.json()["learning_outcomes"] is None

    async def test_editing_them_does_not_touch_existing_scenes(
        self, client, operator_token, project_id, db_session,
    ):
        """NOT RETROACTIVE, and the GUI says so where it is edited.

        Scenes are rows a completed run wrote. This asserts the property the
        notice claims, so the notice cannot become a lie by accident.
        """
        from app.models.storyboard_scene import StoryboardScene

        now = datetime.now(timezone.utc)
        scene = StoryboardScene(
            id=uuid.uuid4(), project_id=uuid.UUID(project_id), scene_index=0,
            narration_text="n", visual_description="a still, authored earlier",
            media_type="image", duration_seconds=5.0,
            created_at=now, updated_at=now,
        )
        db_session.add(scene)
        await db_session.commit()

        scene_id = scene.id

        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"learning_outcomes": OUTCOMES},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text

        # Read the scene back through the API rather than through this
        # session's identity map, so what is asserted is what the server would
        # serve rather than an object this test already holds.
        after = await client.get(
            f"/api/v1/projects/{project_id}/scenes", headers=_h(operator_token),
        )
        rows = [s for s in after.json() if s["id"] == str(scene_id)]
        assert len(rows) == 1
        assert rows[0]["visual_description"] == "a still, authored earlier"
        assert rows[0]["media_type"] == "image"


# ---------------------------------------------------------------------------
# Task 6(c) — they reach the dispatch, as their own key
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def project_with_outcomes(db_session, operator_token):
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.transcript import Transcript

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="WP-64 outcomes dispatch", state="DRAFT",
        description="A short lesson on long multiplication.",
        learning_outcomes=OUTCOMES, max_runtime_seconds=300,
        created_by=owner, created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(Transcript(
        id=uuid.uuid4(), project_id=project.id, sequence_order=1,
        refined_text="t", created_at=now, updated_at=now,
    ))
    await db_session.commit()
    return str(project.id)


class TestTheyReachTheDispatch:
    async def test_the_trigger_carries_them(
        self, client, operator_token, project_with_outcomes, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{project_with_outcomes}/trigger",
            headers=_h(operator_token),
        )
        assert resp.status_code in (200, 202), resp.text
        ctx = broker.sent[0]["kwargs"]["job_context_dict"]
        assert ctx["learning_outcomes"] == OUTCOMES

    async def test_they_travel_as_their_own_key_not_merged_at_the_api(
        self, client, operator_token, project_with_outcomes, broker,
    ):
        """The ONE place that merges them is the orchestrator's storyboard
        branch. Merging here would put a block of pedagogy into every stage's
        project_description, including the FLUX prompt writer's."""
        await client.post(
            f"/api/v1/projects/{project_with_outcomes}/trigger",
            headers=_h(operator_token),
        )
        ctx = broker.sent[0]["kwargs"]["job_context_dict"]
        assert ctx["project_description"] == (
            "A short lesson on long multiplication."
        )
        assert "LEARNING OUTCOMES" not in ctx["project_description"]

    async def test_a_project_without_them_carries_no_empty_key(
        self, client, operator_token, db_session, broker,
    ):
        """Omitted rather than sent empty, so nothing downstream has an absence
        to reason about."""
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.transcript import Transcript

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        now = datetime.now(timezone.utc)
        project = Project(
            id=uuid.uuid4(), name="no outcomes", state="DRAFT",
            created_by=owner, created_at=now, updated_at=now,
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(Transcript(
            id=uuid.uuid4(), project_id=project.id, sequence_order=1,
            refined_text="t", created_at=now, updated_at=now,
        ))
        await db_session.commit()

        await client.post(
            f"/api/v1/projects/{project.id}/trigger", headers=_h(operator_token),
        )
        ctx = broker.sent[0]["kwargs"]["job_context_dict"]
        assert "learning_outcomes" not in ctx

    def test_the_gate_regeneration_path_carries_them_too(self):
        """The storyboard gate's `regenerate` re-runs Stage 2 through
        `project_facts`, so a re-run must see what the first run saw."""
        from app.services.regeneration import project_facts

        class _P:
            name = "p"
            description = "d"
            target_audience = "general"
            language_code = "en-US"
            max_runtime_seconds = 300
            learning_outcomes = OUTCOMES

        assert project_facts(_P())["learning_outcomes"] == OUTCOMES

    def test_project_facts_omits_a_blank(self):
        from app.services.regeneration import project_facts

        class _P:
            name = "p"
            description = "d"
            target_audience = "general"
            language_code = "en-US"
            max_runtime_seconds = 300
            learning_outcomes = "   "

        assert "learning_outcomes" not in project_facts(_P())


# ---------------------------------------------------------------------------
# Task 6(c) — the carrier, and the delimiter that must not drift
# ---------------------------------------------------------------------------


class TestTheCarrierAndItsDelimiter:
    """The orchestrator is worker-side; this reads it as text rather than
    importing it, because the API test tree has no worker imports and the
    property being gated is that two FILES agree."""

    @pytest.fixture(scope="class")
    def orchestrator(self) -> str:
        return ORCHESTRATOR.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_the_outcomes_reach_the_model_through_the_system_prompt(self):
        """THE ONE WAY THIS FEATURE FAILS SILENTLY, AT THE NEW PATH.

        RE-AIMED BY WP-IVGS-12. It used to be a delimiter drift: the orchestrator
        wrote the outcomes between two lines and RULE 0 told the model to look
        for them, so if the two copies diverged the model was handed a block it
        was never told to read — no error, no log line, outcomes ignored,
        everything green.

        The same risk exists at the new path in a different shape: the SYSTEM
        template could stop interpolating the variable, and the outcomes would
        simply not be in the prompt while every test about dispatch still
        passed. So this asserts the whole way through — the variable is in the
        template, and a rendered prompt CONTAINS the outcomes given to it and
        does NOT contain outcomes that were not.
        """
        from jinja2 import BaseLoader, Environment

        system = (
            REPO / "ivgs-api" / "seed" / "default_prompts"
            / "storyboard_design_system.j2"
        ).read_text(encoding="utf-8")
        assert "{{ learning_outcomes }}" in system, (
            "the system prompt no longer interpolates the outcomes; they would "
            "vanish from the model's view with nothing failing"
        )
        env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
        with_them = env.from_string(system).render(learning_outcomes=OUTCOMES)
        without = env.from_string(system).render(learning_outcomes="")
        assert OUTCOMES in with_them
        assert OUTCOMES not in without
        assert "NO LEARNING OUTCOMES WERE STATED" in without

    def test_the_fold_is_retired_and_nothing_calls_it(self, orchestrator):
        """P2.66 CLOSED. The function is KEPT as the record of what the
        fallback was — deleting it would delete the explanation of why the
        ledger row sat open for three packages — but it must have no call site,
        or the outcomes would arrive twice and by two different routes."""
        assert orchestrator.count("_description_with_outcomes(") == 1, (
            "the definition and NOTHING else; a call site means the retired "
            "fold is still folding"
        )
        storyboard_branch = orchestrator[
            orchestrator.index("elif stage == PipelineStage.STORYBOARD_GENERATION.value:"):
            orchestrator.index("elif stage == PipelineStage.COMPOSITION_MANIFEST.value:")
        ]
        assert "_description_with_outcomes(" not in storyboard_branch
        assert "storyboard_generation_system" in storyboard_branch, (
            "the storyboard branch must resolve the versioned system prompt"
        )

    def test_the_delimiters_are_kept_identical_for_the_record(
        self, orchestrator,
    ):
        """The constants stay, byte-identical to what they always were.

        Nothing reads them any more, and that is exactly why they are pinned:
        a half-removed carrier — constants gone, a stale block still being
        written somewhere — is worse than either state.
        """
        assert 'OUTCOMES_OPEN = "=== LEARNING OUTCOMES (authored by the course owner) ==="' in orchestrator
        assert 'OUTCOMES_CLOSE = "=== END LEARNING OUTCOMES ==="' in orchestrator

    def test_the_frozen_render_call_is_untouched(self):
        """AD-05 section 8. The nine names are still the nine names; if a tenth
        appears here, someone edited a frozen stage body and this package's
        whole fallback was unnecessary — which is a thing to notice, loudly."""
        body = (
            REPO / "ivgs-workers" / "tasks" / "stage2_storyboard.py"
        ).read_text(encoding="utf-8")
        start = body.index("        return template.render(")
        end = body.index("        )", start)
        call = body[start:end]
        assert "learning_outcomes" not in call
        assert "project_description=context.get" in call


# ---------------------------------------------------------------------------
# Task 6(d) — RULE 0 degrades silently
# ---------------------------------------------------------------------------


class TestRule0DegradesSilently:
    """RE-AIMED BY WP-IVGS-12. v8's RULE 0 is unconditional — the outcomes are
    in the system prompt now, so the user template no longer guards RULE 0
    behind `{% if project_description %}` and no longer looks for a block."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_the_brief_block_disappears_without_a_description(self, template):
        from jinja2 import Template

        rendered = Template(template).render(
            project_title="p", project_description="",
            max_duration_seconds=300, combined_transcript="t",
        )
        assert "PROJECT BRIEF:" not in rendered
        # ...and the rest of the prompt is intact.
        assert "EVERY VISUAL MUST DEPICT ITS OWN SCENE'S STEP" in rendered
        assert "CHOOSE media_type DELIBERATELY" in rendered

    def test_no_delimited_block_is_looked_for_any_more(self, template):
        """The two delimiter lines are GONE from the template, deliberately.
        Nothing writes them, and a prompt still hunting for a block nobody
        writes would read its absence as 'the outcomes were not stated'."""
        assert "=== LEARNING OUTCOMES (authored by the course owner) ===" not in template
        assert "=== END LEARNING OUTCOMES ===" not in template
        assert "There is\nno delimited block to look for any more." in template

    def test_rule_0_still_forbids_inventing_outcomes(self, template):
        from jinja2 import Template

        rendered = Template(template).render(
            project_title="p",
            project_description="A short lesson on long multiplication.",
            max_duration_seconds=300, combined_transcript="t",
        )
        assert "RULE 0 —" in rendered
        assert "THE LEARNING OUTCOMES ARE IN YOUR SYSTEM INSTRUCTIONS" in rendered
        assert "DO NOT invent outcomes" in rendered
